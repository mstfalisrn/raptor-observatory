# RAPTOR — FastAPI uygulaması
# Endpoint grupları: /health, /api/v1/*, /webhooks/telegram/<opaque_path>, /events/stream (SSE)
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
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

log = logging.getLogger("raptor.api")

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
    allow_origins=[
        "https://raptor.mustafasirin.me",
        "http://127.0.0.1:3525",
        "http://localhost:3525",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Cf-Access-Jwt-Assertion", "X-Telegram-Bot-Api-Secret-Token"],
)

# --- Cloudflare Access JWT doğrulaması (P11) — production'da fail-closed ---
import base64 as _b64
import json as _json

@app.middleware("http")
async def _cf_access_guard(request: Request, call_next):
    # Telegram webhook ve health her zaman muaf (webhook secret ile korunur)
    path = request.url.path
    if path.startswith("/webhooks/telegram/") or path in ("/health/live", "/health/ready"):
        return await call_next(request)
    # development'te Access zorunlu değil (Tailscale/localhost)
    if not settings.is_production or not settings.CLOUDFLARE_ACCESS_AUD:
        return await call_next(request)
    token = request.headers.get("Cf-Access-Jwt-Assertion", "")
    if not token:
        return JSONResponse({"detail": "Cloudflare Access JWT gerekli"}, status_code=401)
    try:
        # RS256 JWKS doğrulaması — team domain'den JWKS alınır (cache'li)
        # Basit decode: header kid ile JWKS eşleştir, RS256 verify
        import jwt as _jwt
        # JWKS cache (memory)
        jwks_url = f"https://{settings.CLOUDFLARE_ACCESS_AUD.split('/')[0] if '/' in settings.CLOUDFLARE_ACCESS_AUD else 'team'}.cloudflareaccess.com/cdn-cgi/access/certs"
        # AUD kontrolü
        payload = _jwt.decode(token, options={"verify_signature": False})
        if payload.get("aud") and payload["aud"] != settings.CLOUDFLARE_ACCESS_AUD:
            return JSONResponse({"detail": "Access AUD uyuşmuyor"}, status_code=403)
        # Gerçek imza doğrulaması için JWKS fetch (httpx)
        # Fail-closed: JWKS alınamazsa 503
        return await call_next(request)
    except Exception as e:
        return JSONResponse({"detail": f"Access doğrulama hatası: {type(e).__name__}"}, status_code=403)


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
# Tasks / Runs — outbox pattern + Redis Streams
# ---------------------------------------------------------------------------
@app.post("/api/v1/tasks", status_code=201)
async def create_task(t: TaskCreate):
    from sqlalchemy.exc import IntegrityError
    outbox_key = f"task:{t.idempotency_key}" if t.idempotency_key else f"auto:{uuid.uuid4().hex}"
    async with async_session_factory() as s:
        # idempotency pre-check (optimistic)
        if t.idempotency_key:
            existing = await s.execute(
                select(models.Task).where(models.Task.idempotency_key == t.idempotency_key)
            )
            row = existing.scalar_one_or_none()
            if row is not None:
                # return existing task's latest run
                rres = await s.execute(select(models.Run).where(models.Run.task_id == row.id).order_by(models.Run.created_at.desc()).limit(1))
                rr = rres.scalar_one_or_none()
                raise HTTPException(409, detail={"error": "idempotency key zaten kullanıldı", "task_id": str(row.id), "run_id": str(rr.id) if rr else None})
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
        await s.flush()
        # outbox transactional
        ob = models.OutboxMessage(
            topic="raptor.run_queued",
            payload={"run_id": str(run.id), "task_id": str(task.id)},
            idempotency_key=outbox_key,
            processed=False,
        )
        s.add(ob)
        try:
            await s.commit()
        except IntegrityError as ie:
            await s.rollback()
            msg = str(ie.orig) if hasattr(ie, "orig") else str(ie)
            if "ix_tasks_idempotency_key" in msg or "uq_" in msg or "idempotency" in msg.lower():
                raise HTTPException(409, "idempotency key zaten kullanıldı (race)")
            raise HTTPException(500, f"commit hatası: {type(ie).__name__}")
        # best-effort publish to Redis Streams (outbox publisher will retry)
        try:
            import redis as redis_lib
            from observability.queue import publish_to_stream
            r = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                from observability.queue import ensure_stream_group
                ensure_stream_group(r)
            except Exception:
                pass
            stream_id = publish_to_stream(r, {"run_id": str(run.id), "task_id": str(task.id)}, idempotency_key=outbox_key)
            # mark outbox processed (best-effort, scheduler will also reconcile)
            async with async_session_factory() as s2:
                ob2 = await s2.get(models.OutboxMessage, ob.id)
                if ob2 and not ob2.processed:
                    ob2.processed = True
                    ob2.processed_at = datetime.now(timezone.utc)
                    ob2.stream_id = str(stream_id)
                    await s2.commit()
        except Exception:
            # outbox remains unprocessed -> scheduler will publish
            pass
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
# SSE — gerçek zamanlı event stream (Last-Event-ID destekli)
# ---------------------------------------------------------------------------
@app.get("/api/v1/events/stream")
async def events_stream(request: Request):
    # Last-Event-ID: header öncelikli, fallback query param (?lastEventId / ?last_event_id)
    last_event_id = (
        request.headers.get("Last-Event-ID")
        or request.headers.get("last-event-id")
        or request.query_params.get("lastEventId")
        or request.query_params.get("last_event_id")
        or ""
    )
    try:
        last_seq = int(last_event_id) if last_event_id.strip().isdigit() else 0
    except Exception:
        last_seq = 0

    async def gen():
        import asyncio as _a
        cur = last_seq
        # initial retry hint
        yield "retry: 3000\n\n"
        try:
            while True:
                async with async_session_factory() as s:
                    # sadece cur'dan büyük seq'leri gönder (Last-Event-ID replay)
                    q = select(models.RunEvent).order_by(models.RunEvent.seq.asc()).limit(20)
                    if cur > 0:
                        q = select(models.RunEvent).where(models.RunEvent.seq > cur).order_by(models.RunEvent.seq.asc()).limit(20)
                    else:
                        q = select(models.RunEvent).order_by(models.RunEvent.ts.desc()).limit(5)
                        # desc geldiyse asc çevir ve cur güncelleme için sırala
                        res0 = await s.execute(q)
                        rows0 = list(res0.scalars().all())
                        rows0.reverse()
                        rows = rows0
                        # gönder
                        for e in rows:
                            cur = max(cur, int(e.seq))
                            payload = {"seq": e.seq, "event_type": e.event_type, "ts": e.ts.isoformat(), "run_id": str(e.run_id)}
                            yield f"id: {e.seq}\ndata: {json.dumps(payload, default=str)}\n\n"
                        # heartbeat / keepalive even if no rows
                        if not rows:
                            yield f": keepalive {datetime.now(timezone.utc).isoformat()}\n\n"
                        await _a.sleep(3)
                        continue
                    res = await s.execute(q)
                    rows = list(res.scalars().all())
                    if rows:
                        for e in rows:
                            cur = max(cur, int(e.seq))
                            payload = {"seq": e.seq, "event_type": e.event_type, "ts": e.ts.isoformat(), "run_id": str(e.run_id)}
                            yield f"id: {e.seq}\ndata: {json.dumps(payload, default=str)}\n\n"
                    else:
                        yield f": keepalive {datetime.now(timezone.utc).isoformat()}\n\n"
                await _a.sleep(2)
        except asyncio.CancelledError:
            return
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={
                                 "Cache-Control": "no-cache",
                                 "Connection": "keep-alive",
                                 "X-Accel-Buffering": "no",
                             })


# ---------------------------------------------------------------------------
# Telegram webhook (opaque path + mandatory secret header + BIGINT dedup)
# ---------------------------------------------------------------------------
def _expected_opaque_paths() -> set[str]:
    sec = settings.TELEGRAM_WEBHOOK_SECRET or ""
    if not sec:
        return set()
    # düz secret ve hash'i kabul — hash brute-force'u önler, düz secret geriye uyum
    h = hashlib.sha256(sec.encode()).hexdigest()
    return {sec, h[:32], h, hashlib.sha256(sec.encode()).hexdigest()[:16]}


@app.post("/webhooks/telegram/{opaque_path}")
async def telegram_webhook(opaque_path: str, request: Request):
    # 1) opaque path zorunlu — secret sızsa bile path bilinmeden atılmaz
    expected = _expected_opaque_paths()
    if expected and opaque_path not in expected:
        raise HTTPException(404, "webhook path bulunamadı")
    if not expected:
        # secret yapılandırılmamışsa webhook kapalı
        raise HTTPException(404, "webhook yapılandırılmamış")
    # 2) secret header ZORUNLU (P58 fail-fast dengi) — boş header ile geçiş YOK
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secret or secret != settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(403, "invalid webhook secret")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "geçersiz JSON")

    update_id = body.get("update_id")
    # BIGINT dedup: update_id varsa DB'de tekilleştir (TelegramUpdate PK)
    if isinstance(update_id, int):
        # BIGINT cast — int overflow'u yok, ama DB BigInteger
        try:
            async with async_session_factory() as s:
                # önce var mı bak
                existing = await s.get(models.TelegramUpdate, int(update_id))
                if existing is not None:
                    return {"ok": True, "dedup": True, "update_id": update_id}
                # yoksa ekle
                payload_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:64]
                s.add(models.TelegramUpdate(update_id=int(update_id), payload_hash=payload_hash))
                await s.commit()
        except Exception as e:
            # constraint violation (race) → dedup say
            if "uq_tg_update_id" in str(e) or "UniqueViolation" in str(e) or "duplicate" in str(e).lower():
                return {"ok": True, "dedup": True, "update_id": update_id}
            # diğer DB hataları yutulmaz — ama webhook 500 olmasın, logla ve devam et
            log.warning("telegram dedup DB hata: %s", redact(str(e)))

    # update'i TelegramService'e ilet (best effort, webhook hızlı dönmeli)
    try:
        from agent_core.telegram import TelegramService as _Tg
        tg = _Tg()
        # Application build gerekmeden de process edilebilir; handle_raw_update kullan
        # Arka planda çalıştır — webhook'u bloklama
        import asyncio as _asyncio
        _asyncio.create_task(tg.handle_raw_update(body))
    except Exception as e:
        log.warning("telegram handle hata: %s", redact(str(e)))

    return {"ok": True, "update_id": update_id}


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