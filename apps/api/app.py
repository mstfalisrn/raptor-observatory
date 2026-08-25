# RAPTOR — FastAPI uygulaması
# Endpoint grupları: /health, /api/v1/*, /webhooks/telegram/<opaque_path>, /events/stream (SSE)
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from observability.config import settings
from observability.db import async_session_factory
from observability import models
from observability.security import redact
from sqlalchemy import text, select

from agent_core.coordinator import RunCoordinator, RunBudget
from agent_core.llm import LLMMessage
from context_engine.assembler import ContextAssembler
from memory.service import MemoryService
from policy.engine import PolicyEngine, action_hash, build_approval_token

app = FastAPI(title="RAPTOR Agentic Observatory", version="1.0.0")

# --- Fail-fast: production'da eksik/placeholder secret ile boot etme (P58) ---
import os as _os
if _os.getenv("APP_ENV") == "production":
    _missing = []
    for _k in ("JWT_SECRET", "SESSION_ENCRYPTION_MASTER_KEY", "TELEGRAM_WEBHOOK_SECRET"):
        _v = getattr(settings, _k.lower(), "") or _os.getenv(_k, "")
        if not _v or _v in ("CHANGE_ME", "dev-only-change-me") or len(str(_v)) < 16:
            _missing.append(_k)
    if _missing:
        raise RuntimeError(f"RAPTOR fail-fast: eksik/placeholder secret: {', '.join(_missing)}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # UI aynı origin üzerinden; production'da dış origin yok
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic şemalar — secret alanları response modellerinde YOK
# ---------------------------------------------------------------------------
class TaskCreate(BaseModel):
    title: str
    prompt: str
    scope: dict = {}
    budget: dict = {}
    idempotency_key: str | None = None


class ApprovalDecision(BaseModel):
    decision: str  # approve | reject
    approval_id: str


def _tg_allowed() -> bool:
    return bool(settings.allowed_user_ids)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health/live")
async def health_live():
    return {"status": "live", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/health/ready")
async def health_ready():
    async with async_session_factory() as s:
        await s.execute(text("SELECT 1"))
    return {"status": "ready", "db": True}


# ---------------------------------------------------------------------------
# Tasks / Runs
# ---------------------------------------------------------------------------
@app.post("/api/v1/tasks", status_code=201)
async def create_task(t: TaskCreate):
    async with async_session_factory() as s:
        # idempotency
        if t.idempotency_key:
            existing = await s.execute(
                select(models.Task).where(models.Task.idempotency_key == t.idempotency_key)
            )
            if existing.scalar_one_or_none() is not None:
                raise HTTPException(409, "idempotency key zaten kullanıldı")
        task = models.Task(
            title=t.title, prompt=t.prompt, scope=t.scope, budget=t.budget,
            idempotency_key=t.idempotency_key,
        )
        s.add(task)
        await s.flush()
        run = models.Run(task_id=task.id, status=models.RunStatus.QUEUED.value,
                         token_budget=settings.RUN_MAX_TOKEN_BUDGET,
                         cost_budget=settings.RUN_MAX_COST_BUDGET)
        s.add(run)
        await s.commit()
        # Redis kuyruğuna koy (worker)
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL)
        r.lpush("raptor:queue", json.dumps({"run_id": str(run.id)}))
        return {"task_id": str(task.id), "run_id": str(run.id), "status": run.status}


@app.get("/api/v1/runs")
async def list_runs(limit: int = 20, offset: int = 0):
    async with async_session_factory() as s:
        res = await s.execute(
            select(models.Run).order_by(models.Run.created_at.desc()).limit(limit).offset(offset)
        )
        runs = res.scalars().all()
        return [{"id": str(r.id), "status": r.status, "iteration": r.iteration,
                 "created_at": r.created_at.isoformat(), "error": r.error} for r in runs]


@app.get("/api/v1/runs/{run_id}/events")
async def run_events(run_id: str):
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(400, "run_id geçersiz")
    async with async_session_factory() as s:
        res = await s.execute(
            select(models.RunEvent).where(models.RunEvent.run_id == uid).order_by(models.RunEvent.seq)
        )
        return [{"seq": e.seq, "event_type": e.event_type, "payload": e.payload, "ts": e.ts.isoformat()}
                for e in res.scalars().all()]


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------
@app.get("/api/v1/approvals")
async def list_approvals(limit: int = 20):
    async with async_session_factory() as s:
        res = await s.execute(
            select(models.Approval).order_by(models.Approval.created_at.desc()).limit(limit)
        )
        return [{"id": str(a.id), "action_class": a.action_class, "target": redact(a.target),
                 "status": a.status, "impact_summary": a.impact_summary,
                 "expires_at": a.expires_at.isoformat() if a.expires_at else None}
                for a in res.scalars().all()]


@app.post("/api/v1/approvals/{approval_id}/decision")
async def decide_approval(approval_id: str, d: ApprovalDecision):
    try:
        uid = uuid.UUID(approval_id)
    except ValueError:
        raise HTTPException(400, "approval_id geçersiz")
    if d.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision approve|reject olmalı")
    async with async_session_factory() as s:
        a = await s.get(models.Approval, uid)
        if a is None:
            raise HTTPException(404, "onay yok")
        if a.status != models.ApprovalStatus.PENDING.value:
            raise HTTPException(409, "zaten karara bağlanmış (idempotent)")
        a.status = (models.ApprovalStatus.APPROVED if d.decision == "approve"
                    else models.ApprovalStatus.REJECTED).value
        a.decision = d.decision
        a.decided_by_user_id = None  # UI'dan; user auth eklenince doldurulur
        await s.commit()
        return {"id": str(a.id), "status": a.status}


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------
class MemoryCreate(BaseModel):
    content: str
    source: str = ""
    confidence: float = 0.5
    category: str | None = None
    ttl_seconds: int | None = None


@app.get("/api/v1/memory")
async def list_memory(status: str | None = None, q: str | None = None, limit: int = 50):
    async with async_session_factory() as s:
        msvc = MemoryService(s)
        items = (await msvc.search(q, status, limit)) if q else (await msvc.list_status(status or "candidate", limit))
        return [{"id": str(i.id), "content": redact(i.content), "status": i.status,
                 "confidence": i.confidence, "source": i.source, "category": i.category,
                 "expires_at": i.expires_at.isoformat() if i.expires_at else None,
                 "created_at": i.created_at.isoformat()} for i in items]


@app.post("/api/v1/memory", status_code=201)
async def create_memory_candidate(m: MemoryCreate):
    async with async_session_factory() as s:
        msvc = MemoryService(s)
        item = await msvc.create_candidate(
            content=m.content, source=m.source, confidence=m.confidence,
            category=m.category, ttl_seconds=m.ttl_seconds,
        )
        await s.commit()
        return {"id": str(item.id), "status": item.status}


@app.post("/api/v1/memory/{memory_id}/decision")
async def decide_memory(memory_id: str, d: dict):
    try:
        uid = uuid.UUID(memory_id)
    except ValueError:
        raise HTTPException(400, "memory id geçersiz")
    action = d.get("decision")  # approve | reject | activate | supersede
    async with async_session_factory() as s:
        msvc = MemoryService(s)
        item = await s.get(models.MemoryItem, uid)
        if item is None:
            raise HTTPException(404, "kayıt yok")
        if action in ("approve", "activate"):
            await msvc.mark_active(uid)
        elif action == "reject":
            await msvc.reject(uid)
        else:
            raise HTTPException(400, "bilinmeyen decision")
        await s.commit()
        return {"id": memory_id, "status": action}


# ---------------------------------------------------------------------------
# Sources / Reports / Technocore
# ---------------------------------------------------------------------------
@app.get("/api/v1/sources")
async def list_sources():
    async with async_session_factory() as s:
        res = await s.execute(select(models.Source).order_by(models.Source.name))
        return [{"id": str(x.id), "name": x.name, "source_type": x.source_type,
                 "is_enabled": x.is_enabled, "last_accessed_at": x.last_accessed_at.isoformat() if x.last_accessed_at else None,
                 "error_series_len": len(x.error_series)} for x in res.scalars().all()]


@app.get("/api/v1/reports")
async def list_reports(limit: int = 20):
    async with async_session_factory() as s:
        res = await s.execute(select(models.Report).order_by(models.Report.created_at.desc()).limit(limit))
        return [{"id": str(r.id), "report_type": r.report_type, "subject": r.subject,
                 "confidence": r.confidence, "created_at": r.created_at.isoformat(),
                 "summary": r.summary} for r in res.scalars().all()]


@app.get("/api/v1/technocore")
async def technocore_status():
    return {"base_url": settings.TECHNOCORE_BASE_URL,
            "room_claim": settings.TECHNOCORE_ROOM_CLAIM, "registered": False}


@app.get("/api/v1/settings/non-secret")
async def settings_non_secret():
    return {
        "app_env": settings.APP_ENV,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "llm_base_url": settings.LLM_BASE_URL,
        "telegram_allowed_user_ids_count": len(settings.allowed_user_ids),
        "telegram_group_enabled": settings.TELEGRAM_GROUP_ENABLED,
        "technocore_base_url": settings.TECHNOCORE_BASE_URL,
        "run_max_iterations": settings.RUN_MAX_ITERATIONS,
        "run_max_wall_seconds": settings.RUN_MAX_WALL_SECONDS,
        # secret DEĞERLERİ asla dönmez; yalnız configured/valid durumu:
        "telegram_token_configured": bool(settings.TELEGRAM_BOT_TOKEN),
        "llm_key_configured": bool(settings.LLM_API_KEY),
    }


# ---------------------------------------------------------------------------
# SSE — gerçek zamanlı event stream
# ---------------------------------------------------------------------------
@app.get("/api/v1/events/stream")
async def events_stream():
    async def gen():
        # Basit canlı stream: son 30 sn içinde run event'lerini yayınla
        import asyncio as _a
        try:
            while True:
                async with async_session_factory() as s:
                    res = await s.execute(
                        select(models.RunEvent).order_by(models.RunEvent.ts.desc()).limit(5)
                    )
                    events = [{"seq": e.seq, "event_type": e.event_type, "ts": e.ts.isoformat()}
                              for e in res.scalars().all()]
                yield f"data: {json.dumps({'events': events}, default=str)}\n\n"
                await _a.sleep(3)
        except asyncio.CancelledError:
            return
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------------------
# Telegram webhook (opaque path ile)
# ---------------------------------------------------------------------------
@app.post("/webhooks/telegram/{opaque_path}")
async def telegram_webhook(opaque_path: str, request: Request):
    # secret header doğrulaması
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret and settings.TELEGRAM_WEBHOOK_SECRET and secret != settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(403, "invalid webhook secret")
    body = await request.json()
    # idempotency update_id: opsiyonel — bu MVP'de basitçe 200 dön (polling handle eder)
    return {"ok": True, "update_id": body.get("update_id")}


# ---------------------------------------------------------------------------
# Root / UI
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    # UI build varsa onu servis et; yoksa basit durum sayfası
    import os as _os
    dist_index = "/srv/raptor/apps/web/dist/index.html"
    candidate = "apps/web/dist/index.html"
    built = _os.path.exists(dist_index) or _os.path.exists(candidate)
    if built:
        try:
            # dist'i api container'ın çalışma dizininden bul
            from pathlib import Path
            txt = (Path(candidate).read_text() if Path(candidate).exists() else Path(dist_index).read_text())
            return HTMLResponse(txt)
        except Exception:
            pass
    return HTMLResponse("""
    <html><head><title>RAPTOR Agentic Observatory</title></head>
    <body style="font-family:sans-serif;background:#0d1421;color:#e8eefc;display:flex;align-items:center;justify-content:center;height:100vh">
      <div style="text-align:center">
        <h1>🐦 RAPTOR Agentic Observatory</h1>
        <p>API çalışıyor. UI build'i dist'te değil.</p>
        <p><code>/health/live</code> · <code>/health/ready</code> · <code>/docs</code></p>
      </div>
    </body></html>
    """)


@app.get("/assets/{path:path}")
async def assets(path: str):
    from fastapi.responses import FileResponse
    import os as _os
    for base in ("apps/web/dist", "/srv/raptor/apps/web/dist"):
        p = f"{base}/assets/{path}"
        if _os.path.exists(p):
            return FileResponse(p)
    raise HTTPException(404)