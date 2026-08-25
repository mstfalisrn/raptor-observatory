# RAPTOR — Worker
# Redis Streams consumer group + ACK/lease, outbox uyumlu
from __future__ import annotations

import asyncio
import json
import os
import uuid

from fastapi import FastAPI
from sqlalchemy import select, text

from observability.config import settings
from observability.db import async_session_factory
from observability import models
from observability.queue import ensure_stream_group, read_group, ack, claim_pending, STREAM, GROUP

from agent_core.coordinator import RunCoordinator, RunBudget
from agent_core.llm import build_provider
from agent_core.planner import Planner
from agent_core.executor import ToolExecutor, build_default_registry
from agent_core.verifier import DefaultVerifier
from context_engine.assembler import ContextAssembler
from policy.engine import PolicyEngine

app = FastAPI(title="RAPTOR Worker", version="1.0.0")
_worker: "WorkerLoop | None" = None


@app.get("/health/live")
async def health_live():
    return {"status": "live"}


class WorkerLoop:
    def __init__(self) -> None:
        import redis as redis_lib
        self.redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        self.consumer_name = f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.registry = build_default_registry(
            http_hosts=set(filter(None, settings.CONNECTOR_ALLOWED_HOSTS.split(","))) if settings.CONNECTOR_ALLOWED_HOSTS else None,
            technocore_key_path=settings.TECHNOCORE_ED25519_KEY_PATH or "/root/secrets/raptor-observatory/did.ed25519",
            technocore_base_url=settings.TECHNOCORE_BASE_URL,
        )
        self.provider = build_provider()
        self.planner = Planner(provider=self.provider)
        self.policy = PolicyEngine()
        self.verifier = DefaultVerifier()
        # ensure consumer group exists (idempotent)
        try:
            ensure_stream_group(self.redis)
        except Exception:
            pass
        self._lease_ms = 30000  # pending reclaim after 30s
        self._heartbeat_interval_s = 5  # run boyunca lease yenileme

    async def _handle_entry(self, entry_id: str, fields: dict) -> bool:
        # fields: {"data": json, "idempotency_key": ...} (decode_responses=True)
        raw = fields.get("data") or fields.get(b"data")
        if raw is None:
            # malformed -> ack to avoid poison
            try:
                ack(self.redis, entry_id)
            except Exception:
                pass
            return True
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            payload = json.loads(raw)
        except Exception:
            try:
                ack(self.redis, entry_id)
            except Exception:
                pass
            return True
        run_id = payload.get("run_id")
        if not run_id:
            try:
                ack(self.redis, entry_id)
            except Exception:
                pass
            return True
        # fallback for old rpop style: if payload came as legacy list entry without data field
        ok = await self._process_run(run_id)
        # always ACK after processing attempt (at-least-once semantics; failure handled via run status)
        try:
            ack(self.redis, entry_id)
        except Exception:
            pass
        return ok

    async def _process_run(self, run_id: str) -> bool:
        async with async_session_factory() as s:
            # idempotency: if run already terminal, skip execution
            run = await s.get(models.Run, uuid.UUID(run_id))
            if run is None:
                return True
            if run.status in (models.RunStatus.COMPLETED.value, models.RunStatus.FAILED.value, models.RunStatus.CANCELLED.value):
                return True
            task = await s.get(models.Task, run.task_id)
            if task is None:
                run.status = models.RunStatus.FAILED.value
                run.error = "task_not_found"
                await s.commit()
                return True
            # lease acquisition: ATOMİK claim (yalnız QUEUED veya lease'i dolmuş EXECUTING)
            import datetime as _dt
            now = _dt.datetime.now(_dt.timezone.utc)
            lease = now + _dt.timedelta(milliseconds=self._lease_ms)
            res = await s.execute(
                text("""
                    UPDATE runs SET status='EXECUTING', worker_id=:w, heartbeat_at=:now,
                           lease_expires_at=:lease, started_at=COALESCE(started_at, :now)
                    WHERE id=:id AND (
                        status='QUEUED'
                        OR (status='EXECUTING' AND (lease_expires_at IS NULL OR lease_expires_at < :now))
                    )
                """),
                {"w": self.consumer_name, "now": now, "lease": lease, "id": str(uuid.UUID(run_id))}
            )
            await s.commit()
            if res.rowcount != 1:
                # başka worker claim etti ya da terminal — bu mesajı atla (dedup)
                return True
            # need fresh session for execution? reuse s after commit
            task_dict = {"prompt": task.prompt, "scope": task.scope}
            executor = ToolExecutor(self.registry, task=task_dict)
            coordinator = RunCoordinator(
                run_id=run_id,
                budget=RunBudget(),
                allowlist_tools=set(),
            )
            coordinator.status = models.RunStatus.EXECUTING
            assembler = ContextAssembler(max_tokens=rum_budget(run))
            assembler.add("task_goal", task.prompt, title=task.title, relevance=1.0)
            # AŞAMA 8: task başında aktif + verified memory retrieval (context'e ekle)
            try:
                from memory.service import MemoryService
                mem = MemoryService(s)
                mem_items = await mem.retrieve_for_context(task.prompt, limit=10)
                for _m in mem_items:
                    assembler.add("memory", _m.content, title=f"memory:{_m.category or 'genel'}",
                                  relevance=max(0.0, min(1.0, _m.confidence or 0.5)))
            except Exception:
                pass

            from observability.security import redact as _redact

            async def _sink(run_id: str, etype: str, payload: dict) -> None:
                # run SIRASINDA Plan/ToolCall tablolarına yaz (canlı gözlem + crash güvenliği)
                try:
                    rid = uuid.UUID(run_id)
                except Exception:
                    return
                try:
                    async with async_session_factory() as s2:
                        if etype == "PLAN":
                            s2.add(models.Plan(run_id=rid, plan_json=payload.get("plan", {}),
                                               expected_evidence={}, status="active"))
                        elif etype == "TOOL_CALL":
                            args_j = json.dumps(payload.get("arguments", {}), default=str)
                            s2.add(models.ToolCall(
                                run_id=rid, tool_name=payload.get("tool", ""),
                                input_summary=args_j[:500],
                                input_redacted=_redact(args_j)[:500],
                                result_summary=json.dumps(payload.get("result", ""), default=str)[:500],
                                action_class="READ_ONLY", policy_decision="ALLOW",
                            ))
                        elif etype == "AWAITING_APPROVAL":
                            from policy.approval import ApprovalService
                            svc = ApprovalService(s2)
                            await svc.create(
                                run_id=run_id,
                                action_id=payload.get("action_id", ""),
                                tool=payload.get("tool", ""),
                                arguments=payload.get("arguments", {}),
                                action_class=payload.get("action_class", "PUBLIC_WRITE"),
                                target=json.dumps(payload.get("arguments", {}), default=str)[:200],
                                impact_summary=f"tool {payload.get('tool','')} onay bekliyor",
                            )
                        await s2.commit()
                except Exception:
                    pass

            async def _pause_check() -> bool:
                try:
                    async with async_session_factory() as s3:
                        r = await s3.get(models.Run, uuid.UUID(run_id))
                        return bool(r and r.control_request == "pause")
                except Exception:
                    return False

            async def _stop_check() -> bool:
                try:
                    async with async_session_factory() as s3:
                        r = await s3.get(models.Run, uuid.UUID(run_id))
                        return bool(r and r.control_request == "stop")
                except Exception:
                    return False

            # heartbeat: run boyunca lease'i düzenli yenile (uzun run stuck sayılmaz)
            hb_stop = asyncio.Event()

            async def _heartbeat_loop():
                while not hb_stop.is_set():
                    try:
                        async with async_session_factory() as s_hb:
                            hb_now = _dt.datetime.now(_dt.timezone.utc)
                            await s_hb.execute(
                                text("UPDATE runs SET heartbeat_at=:now, lease_expires_at=:lease WHERE id=:id AND worker_id=:w"),
                                {"now": hb_now, "lease": hb_now + _dt.timedelta(milliseconds=self._lease_ms),
                                 "id": str(uuid.UUID(run_id)), "w": self.consumer_name},
                            )
                            await s_hb.commit()
                    except Exception:
                        pass
                    try:
                        await asyncio.wait_for(hb_stop.wait(), timeout=self._heartbeat_interval_s)
                    except asyncio.TimeoutError:
                        pass

            hb_task = asyncio.create_task(_heartbeat_loop())
            try:
                status, executed, events = await coordinator.run(executor, self.planner,
                                                                 assembler, self.policy,
                                                                 self.provider, self.verifier,
                                                                 event_sink=_sink,
                                                                 pause_check=_pause_check,
                                                                 stop_check=_stop_check)
            except Exception as exc:
                status = models.RunStatus.FAILED.value
                events = [{"event_type": "FATAL", "payload": {"error": type(exc).__name__}, "seq": 0}]
            finally:
                hb_stop.set()
                hb_task.cancel()
            # reload run for update (avoid stale)
            run2 = await s.get(models.Run, uuid.UUID(run_id))
            if run2 is None:
                return True
            run2.status = status
            run2.iteration = coordinator.iteration
            run2.token_used = coordinator.tokens_used
            run2.cost_used = coordinator.cost_used
            run2.finished_at = _dt.datetime.now(_dt.timezone.utc) if status in (models.RunStatus.COMPLETED.value, models.RunStatus.FAILED.value, models.RunStatus.CANCELLED.value) else run2.finished_at
            if status == models.RunStatus.FAILED.value:
                run2.error = run2.error or "worker_yurutme_hatasi"
            run2.heartbeat_at = _dt.datetime.now(_dt.timezone.utc)
            # event kaydı — unique (run_id,seq) ile idempotent insert
            for ev in events:
                s.add(models.RunEvent(run_id=run2.id, seq=ev["seq"], event_type=ev["event_type"], payload=ev.get("payload", {})))
            # commit with integrity handling for duplicate seq (append-only)
            try:
                await s.commit()
            except Exception as e:
                await s.rollback()
                # if duplicate seq constraint, re-fetch and skip duplicates
                if "uq_run_events_run_seq" in str(e) or "UniqueViolation" in str(type(e).__name__):
                    # fallback: insert one-by-one ignoring duplicates
                    for ev in events:
                        try:
                            async with async_session_factory() as s2:
                                s2.add(models.RunEvent(run_id=run2.id, seq=ev["seq"], event_type=ev["event_type"], payload=ev.get("payload", {})))
                                await s2.commit()
                        except Exception:
                            try:
                                await s2.rollback()
                            except Exception:
                                pass
                    # finally update run status if not yet
                    async with async_session_factory() as s3:
                        r3 = await s3.get(models.Run, uuid.UUID(run_id))
                        if r3 and r3.status != status:
                            r3.status = status
                            r3.iteration = coordinator.iteration
                            await s3.commit()
                else:
                    raise
        return True

    async def _fallback_legacy_queue(self) -> bool:
        """Consume legacy list raptor:queue for backward compatibility during rollout."""
        try:
            raw = self.redis.rpop("raptor:queue")
        except Exception:
            return False
        if not raw:
            return False
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            payload = json.loads(raw)
            run_id = payload.get("run_id")
        except Exception:
            return True
        if run_id:
            await self._process_run(run_id)
        return True

    async def process_one(self) -> bool:
        # 1) try stream read (non-blocking first, then block)
        try:
            entries = read_group(self.redis, self.consumer_name, count=1, block_ms=2000)
            if entries:
                for _stream, msgs in entries:
                    for entry_id, fields in msgs:
                        await self._handle_entry(entry_id, fields)
                        return True
            # 2) reclaim pending that exceeded lease (stuck consumer)
            pending = claim_pending(self.redis, self.consumer_name, min_idle_ms=self._lease_ms, count=1)
            if pending:
                for entry_id, fields in pending:
                    await self._handle_entry(entry_id, fields)
                    return True
            # 3) fallback legacy queue
            return await self._fallback_legacy_queue()
        except Exception:
            # on redis error, still try legacy
            try:
                return await self._fallback_legacy_queue()
            except Exception:
                return False

    async def run(self) -> None:
        while True:
            try:
                processed = await self.process_one()
                if not processed:
                    await asyncio.sleep(0.5)
            except Exception:
                await asyncio.sleep(2.0)


def rum_budget(run) -> int:
    try:
        return int(run.token_budget)
    except Exception:
        return settings.RUN_MAX_TOKEN_BUDGET


@app.on_event("startup")
async def _start():
    global _worker
    _worker = WorkerLoop()
    asyncio.create_task(_worker.run())
