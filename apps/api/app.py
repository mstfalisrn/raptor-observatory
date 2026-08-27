# RAPTOR — FastAPI uygulaması
# Endpoint grupları: /health, /api/v1/*, /webhooks/telegram/<opaque_path>, /events/stream (SSE)
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text

from memory.service import MemoryService
from observability import __version__, models
from observability.config import settings
from observability.db import async_session_factory
from observability.security import redact

log = logging.getLogger("raptor.api")


# --- Lifespan: admin kullanıcısını seed et ---
from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    if settings.ADMIN_PASSWORD_HASH:
        async with async_session_factory() as s:
            res = await s.execute(select(models.User).where(models.User.username == settings.ADMIN_EMAIL))
            u = res.scalar_one_or_none()
            if u is None:
                s.add(models.User(username=settings.ADMIN_EMAIL, display_name="Admin",
                                  role="admin", is_active=True, password_hash=settings.ADMIN_PASSWORD_HASH))
                await s.commit()
                log.info("admin kullanıcı seed edildi: %s", settings.ADMIN_EMAIL)
            elif u.password_hash != settings.ADMIN_PASSWORD_HASH:
                u.password_hash = settings.ADMIN_PASSWORD_HASH
                await s.commit()
    # Telegram Application singleton: build+initialize+start BİR KEZ (webhook için)
    _tg = None
    if settings.TELEGRAM_BOT_TOKEN:
        try:
            from agent_core.telegram import get_service
            _tg = get_service()
            await _tg.initialize()
            log.info("Telegram Application initialized")
        except Exception as e:
            log.warning("Telegram initialize atlandı (dev): %s", type(e).__name__)
    yield
    if _tg is not None:
        await _tg.shutdown()


app = FastAPI(title="RAPTOR Agentic Observatory", version=__version__, lifespan=_lifespan)

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
        "https://raptor.your-domain.example",
        "http://127.0.0.1:3525",
        "http://localhost:3525",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Cf-Access-Jwt-Assertion", "X-Telegram-Bot-Api-Secret-Token"],
)

# --- Local auth (CF Access kullanılmıyor) + rate limit + body size ---
from observability.auth import (
    create_session_token,
    get_current_user,
    rate_limiter,
    require_role,
    verify_password,
)

_PUBLIC_PATHS = {"/health/live", "/health/ready", "/api/health/live", "/api/health/ready", "/api/v1/auth/login", "/api/v1/auth/status"}


@app.middleware("http")
async def _guard(request: Request, call_next):
    path = request.url.path
    # Telegram webhook + health + login muaf (webhook secret header ile korunur)
    if path.startswith("/webhooks/telegram/") or path in _PUBLIC_PATHS:
        return await call_next(request)
    # Body boyut limiti (Content-Length + streaming guard)
    cl = request.headers.get("content-length", "")
    if cl.isdigit() and int(cl) > settings.MAX_REQUEST_BODY_BYTES:
        return JSONResponse({"detail": "request body çok büyük"}, status_code=413)
    # Global rate limit — gerçek istemci IP'si (Cloudflare Tunnel arkasında request.client.host=127.0.0.1 olur)
    cf_ip = request.headers.get("CF-Connecting-IP", "").strip()
    xff = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    ip = cf_ip or xff or (request.client.host if request.client else "unknown")
    if not await rate_limiter.check(f"rl:global:{ip}", settings.RATE_LIMIT_PER_MINUTE, 60):
        return JSONResponse({"detail": "rate limit aşıldı"}, status_code=429)
    return await call_next(request)


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


class RunControl(BaseModel):
    action: str  # pause | resume | stop


def _tg_allowed() -> bool:
    return bool(settings.allowed_user_ids)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health/live")
async def health_live():
    return {"status": "live", "time": datetime.now(UTC).isoformat()}


@app.get("/health/ready")
async def health_ready():
    async with async_session_factory() as s:
        await s.execute(text("SELECT 1"))
    return {"status": "ready", "db": True}


@app.get("/api/health/live")
async def api_health_live():
    return {"status": "live", "time": datetime.now(UTC).isoformat()}


@app.get("/api/health/ready")
async def api_health_ready():
    async with async_session_factory() as s:
        await s.execute(text("SELECT 1"))
    return {"status": "ready", "db": True}


# ---------------------------------------------------------------------------
# Auth (local session)
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/v1/auth/login")
async def login(req: LoginRequest):
    async with async_session_factory() as s:
        res = await s.execute(select(models.User).where(models.User.username == req.email))
        u = res.scalar_one_or_none()
        if u is None or not u.is_active or not u.password_hash or not verify_password(req.password, u.password_hash):
            raise HTTPException(401, "geçersiz email veya parola")
        token = create_session_token(str(u.id), u.role, settings.SESSION_TTL_SECONDS)
        return {"token": token, "role": u.role, "email": u.username, "display_name": u.display_name}


@app.get("/api/v1/auth/status")
async def auth_status():
    return {"auth": "local", "admin_email": settings.ADMIN_EMAIL,
            "roles": ["admin", "operator", "viewer"],
            "session_ttl_seconds": settings.SESSION_TTL_SECONDS}


@app.get("/api/v1/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    async with async_session_factory() as s:
        res = await s.execute(select(models.User).where(models.User.id == user["user_id"]))
        u = res.scalar_one_or_none()
    if u is None:
        raise HTTPException(404, "kullanıcı yok")
    return {"user_id": str(u.id), "username": u.username, "role": u.role,
            "display_name": u.display_name, "is_active": u.is_active}


# ---------------------------------------------------------------------------
# Tasks / Runs — outbox pattern + Redis Streams
# ---------------------------------------------------------------------------
@app.post("/api/v1/tasks", status_code=201)
async def create_task(t: TaskCreate, user: dict = Depends(require_role("operator"))):
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
                raise HTTPException(409, "idempotency key zaten kullanıldı (race)") from ie
            raise HTTPException(500, f"commit hatası: {type(ie).__name__}") from ie
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
                    ob2.processed_at = datetime.now(UTC)
                    ob2.stream_id = str(stream_id)
                    await s2.commit()
        except Exception:
            # outbox remains unprocessed -> scheduler will publish
            pass
        return {"task_id": str(task.id), "run_id": str(run.id), "status": run.status}


@app.get("/api/v1/runs")
async def list_runs(limit: int = 20, offset: int = 0, user: dict = Depends(get_current_user)):
    async with async_session_factory() as s:
        res = await s.execute(
            select(models.Run).order_by(models.Run.created_at.desc()).limit(limit).offset(offset)
        )
        runs = res.scalars().all()
        return [{"id": str(r.id), "status": r.status, "iteration": r.iteration,
                 "created_at": r.created_at.isoformat(), "error": r.error} for r in runs]


@app.get("/api/v1/runs/{run_id}/events")
async def run_events(run_id: str, user: dict = Depends(get_current_user)):
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(400, "run_id geçersiz") from None
    async with async_session_factory() as s:
        res = await s.execute(
            select(models.RunEvent).where(models.RunEvent.run_id == uid).order_by(models.RunEvent.seq)
        )
        return [{"seq": e.seq, "event_type": e.event_type, "payload": e.payload, "ts": e.ts.isoformat()}
                for e in res.scalars().all()]


@app.get("/api/v1/runs/{run_id}")
async def get_run(run_id: str, user: dict = Depends(get_current_user)):
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(400, "run_id geçersiz") from None
    async with async_session_factory() as s:
        run = await s.get(models.Run, uid)
        if run is None:
            raise HTTPException(404, "run bulunamadı")
        return {"id": str(run.id), "task_id": str(run.task_id), "status": run.status,
                "iteration": run.iteration, "token_used": run.token_used, "cost_used": run.cost_used,
                "worker_id": run.worker_id, "control_request": run.control_request,
                "error": run.error, "created_at": run.created_at.isoformat(),
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                # geriye uyum için deprecated alias
                "completed_at": run.finished_at.isoformat() if run.finished_at else None}


@app.post("/api/v1/runs/{run_id}/control")
async def control_run(run_id: str, c: RunControl, user: dict = Depends(require_role("operator"))):
    if c.action not in ("pause", "resume", "stop"):
        raise HTTPException(400, "action pause|resume|stop olmalı")
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(400, "run_id geçersiz") from None
    async with async_session_factory() as s:
        run = await s.get(models.Run, uid)
        if run is None:
            raise HTTPException(404, "run bulunamadı")
        if run.status not in (models.RunStatus.EXECUTING.value, models.RunStatus.QUEUED.value):
            raise HTTPException(409, f"run terminal durumda ({run.status}), kontrol edilemez")
        run.control_request = c.action if c.action != "resume" else None
        await s.commit()
        return {"ok": True, "run_id": str(run.id), "control_request": run.control_request}


@app.post("/api/v1/runs/{run_id}/retry")
async def retry_run(run_id: str, user: dict = Depends(require_role("operator"))):
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(400, "run_id geçersiz") from None
    async with async_session_factory() as s:
        run = await s.get(models.Run, uid)
        if run is None:
            raise HTTPException(404, "run bulunamadı")
        if run.status not in (models.RunStatus.FAILED.value, models.RunStatus.COMPLETED.value,
                              models.RunStatus.CANCELLED.value):
            raise HTTPException(409, f"run terminal değil ({run.status}), retry edilemez")
        # Retry aynı Run'ı reuse edip seq çakıştırmasın: aynı Task altında YENİ Run
        new_run = models.Run(
            task_id=run.task_id,
            status=models.RunStatus.QUEUED.value,
            retry_count=(run.retry_count or 0) + 1,
            token_budget=run.token_budget,
            cost_budget=run.cost_budget,
        )
        s.add(new_run)
        await s.flush()
        # outbox ile atomik enqueue (idempotent)
        try:
            out = models.OutboxMessage(
                topic="raptor.run_queued",
                payload={"run_id": str(new_run.id), "source_run_id": str(run.id)},
                idempotency_key=f"retry:{run.id}:{new_run.id}",
            )
            s.add(out)
        except Exception:
            pass
        await s.commit()
        # best-effort doğrudan stream'e de bas (outbox publisher yoksa)
        try:
            import redis as redis_lib

            from observability.queue import publish_to_stream
            r = redis_lib.from_url(settings.REDIS_URL)
            publish_to_stream(r, {"run_id": str(new_run.id)}, idempotency_key=f"retry:{run.id}:{new_run.id}")
        except Exception:
            pass
        return {"ok": True, "run_id": str(new_run.id), "source_run_id": str(run.id), "retry_count": new_run.retry_count}


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------
@app.get("/api/v1/approvals")
async def list_approvals(limit: int = 20, user: dict = Depends(get_current_user)):
    async with async_session_factory() as s:
        res = await s.execute(
            select(models.Approval).order_by(models.Approval.created_at.desc()).limit(limit)
        )
        return [{"id": str(a.id), "action_class": a.action_class, "target": redact(a.target),
                 "status": a.status, "impact_summary": a.impact_summary,
                 "expires_at": a.expires_at.isoformat() if a.expires_at else None}
                for a in res.scalars().all()]


@app.post("/api/v1/approvals/{approval_id}/decision")
async def decide_approval(approval_id: str, d: ApprovalDecision, user: dict = Depends(require_role("operator"))):
    # path approval_id ile body approval_id aynı olmalı
    if d.approval_id != approval_id:
        raise HTTPException(400, "path approval_id ile body approval_id uyuşmuyor")
    from policy.approval import ApprovalService
    try:
        async with async_session_factory() as s:
            svc = ApprovalService(s)
            a = await svc.decide(approval_id, d.decision, user.get("user_id"))
            # atomik: approve ise run resume outbox ile enqueue, reject ise run'ı terminale çek
            if d.decision == "approve" and a.run_id:
                # idempotent enqueue — aynı approval_id ikinci kez approve edilemez (decide zaten 409), fakat outbox da unique
                try:
                    s.add(models.OutboxMessage(
                        topic="raptor.run_queued",
                        payload={"run_id": str(a.run_id), "approval_id": str(a.id)},
                        idempotency_key=f"approve:{a.id}",
                    ))
                except Exception:
                    pass
            elif d.decision == "reject" and a.run_id:
                try:
                    r = await s.get(models.Run, a.run_id)
                    if r and r.status == models.RunStatus.WAITING_APPROVAL.value:
                        r.status = models.RunStatus.FAILED.value
                        r.error = "approval_rejected"
                except Exception:
                    pass
            await s.commit()
            # best-effort doğrudan stream'e de bas (outbox publisher yoksa düşmez)
            if d.decision == "approve" and a.run_id:
                try:
                    import redis as redis_lib

                    from observability.queue import publish_to_stream
                    rr = redis_lib.from_url(settings.REDIS_URL)
                    publish_to_stream(rr, {"run_id": str(a.run_id), "approval_id": str(a.id)}, idempotency_key=f"approve:{a.id}")
                except Exception:
                    pass
            return {"id": str(a.id), "status": a.status, "decision": a.decision}
    except ValueError as e:
        msg = str(e)
        if "süresi dolmuş" in msg or "EXPIRED" in msg:
            raise HTTPException(410, msg) from None
        if "bulunamadı" in msg:
            raise HTTPException(404, msg) from None
        if "zaten" in msg:
            raise HTTPException(409, msg) from None
        raise HTTPException(400, msg) from None


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
async def list_memory(status: str | None = None, q: str | None = None, limit: int = 50, user: dict = Depends(get_current_user)):
    async with async_session_factory() as s:
        msvc = MemoryService(s)
        items = (await msvc.search(q, status, limit)) if q else (await msvc.list_status(status or "candidate", limit))
        return [{"id": str(i.id), "content": redact(i.content), "status": i.status,
                 "confidence": i.confidence, "source": i.source, "category": i.category,
                 "expires_at": i.expires_at.isoformat() if i.expires_at else None,
                 "created_at": i.created_at.isoformat()} for i in items]


@app.post("/api/v1/memory", status_code=201)
async def create_memory_candidate(m: MemoryCreate, user: dict = Depends(require_role("operator"))):
    async with async_session_factory() as s:
        msvc = MemoryService(s)
        item = await msvc.create_candidate(
            content=m.content, source=m.source, confidence=m.confidence,
            category=m.category, ttl_seconds=m.ttl_seconds,
        )
        await s.commit()
        return {"id": str(item.id), "status": item.status}


@app.post("/api/v1/memory/{memory_id}/decision")
async def decide_memory(memory_id: str, d: dict, user: dict = Depends(require_role("admin"))):
    try:
        uid = uuid.UUID(memory_id)
    except ValueError:
        raise HTTPException(400, "memory id geçersiz") from None
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
async def settings_non_secret(user: dict = Depends(get_current_user)):
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
        cur = last_seq  # global_seq cursor (global monoton, run içi seq değil)
        yield "retry: 3000\n\n"
        try:
            while True:
                async with async_session_factory() as s:
                    q = (select(models.RunEvent)
                         .where(models.RunEvent.global_seq > cur)
                         .order_by(models.RunEvent.global_seq.asc())
                         .limit(50))
                    res = await s.execute(q)
                    rows = list(res.scalars().all())
                    if rows:
                        for e in rows:
                            cur = max(cur, int(e.global_seq))
                            payload = {"global_seq": e.global_seq, "seq": e.seq,
                                       "event_type": e.event_type, "ts": e.ts.isoformat(),
                                       "run_id": str(e.run_id)}
                            yield f"id: {e.global_seq}\ndata: {json.dumps(payload, default=str)}\n\n"
                    else:
                        yield f": keepalive {datetime.now(UTC).isoformat()}\n\n"
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
        raise HTTPException(400, "geçersiz JSON") from None

    update_id = body.get("update_id")
    rec_id = int(update_id) if isinstance(update_id, int) else None
    # BIGINT durable inbox: PENDING kaydı (dedup + retry için)
    if rec_id is not None:
        try:
            async with async_session_factory() as s:
                existing = await s.get(models.TelegramUpdate, rec_id)
                if existing is not None and existing.status == "PROCESSED":
                    return {"ok": True, "dedup": True, "update_id": update_id}
                if existing is None:
                    payload_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:64]
                    s.add(models.TelegramUpdate(update_id=rec_id, payload_hash=payload_hash, status="PENDING"))
                    await s.commit()
        except Exception as e:
            if "uq_tg_update_id" in str(e) or "UniqueViolation" in str(e) or "duplicate" in str(e).lower():
                return {"ok": True, "dedup": True, "update_id": update_id}
            log.warning("telegram dedup DB hata: %s", redact(str(e)))

    # gerçekten işle (singleton) — işlenmeden PROCESSED sayılmaz
    from agent_core.telegram import get_service
    tg = get_service()
    try:
        await tg.handle_raw_update(body)
    except Exception as e:
        log.warning("telegram handle hata: %s", redact(str(e)))
        if rec_id is not None:
            try:
                async with async_session_factory() as s:
                    r2 = await s.get(models.TelegramUpdate, rec_id)
                    if r2 is not None:
                        r2.status = "FAILED"
                        r2.attempt_count = (r2.attempt_count or 0) + 1
                        await s.commit()
            except Exception:
                pass
        # 500 dön ki Telegram retry etsin
        return JSONResponse({"ok": False, "error": "processing_failed"}, status_code=500)

    # başarılı → PROCESSED
    if rec_id is not None:
        try:
            async with async_session_factory() as s:
                r2 = await s.get(models.TelegramUpdate, rec_id)
                if r2 is not None:
                    r2.status = "PROCESSED"
                    r2.attempt_count = (r2.attempt_count or 0) + 1
                    r2.processed_at = datetime.now(UTC)
                    await s.commit()
        except Exception:
            pass

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
    import os as _os

    from fastapi.responses import FileResponse
    for base in ("apps/web/dist", "/srv/raptor/apps/web/dist"):
        p = f"{base}/assets/{path}"
        if _os.path.exists(p):
            return FileResponse(p)
    raise HTTPException(404)