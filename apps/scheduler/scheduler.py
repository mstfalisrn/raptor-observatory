# RAPTOR — Scheduler
# Gerçek işler: kaynak tarama + görev oluşturma, outbox publisher, stuck-run recovery, heartbeat
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from sqlalchemy import select

from observability.config import settings
from observability.db import async_session_factory
from observability import models

app = FastAPI(title="RAPTOR Scheduler", version="1.0.0")


@app.get("/health/live")
async def health_live():
    return {"status": "live"}


class SchedulerLoop:
    def __init__(self, interval_seconds: int = 60) -> None:
        import redis as redis_lib
        self.redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        self.interval = interval_seconds
        self._stuck_threshold = timedelta(minutes=15)
        self._lease_ms = 30000

    async def publish_outbox(self) -> int:
        """Outbox publisher: unprocessed messages -> Redis Streams (reliable)."""
        published = 0
        async with async_session_factory() as s:
            res = await s.execute(
                select(models.OutboxMessage)
                .where(models.OutboxMessage.processed.is_(False))
                .order_by(models.OutboxMessage.created_at.asc())
                .limit(20)
            )
            msgs = list(res.scalars().all())
            for m in msgs:
                if m.attempts > 10:
                    continue
                try:
                    from observability.queue import publish_to_stream, ensure_stream_group
                    try:
                        ensure_stream_group(self.redis)
                    except Exception:
                        pass
                    stream_id = publish_to_stream(self.redis, m.payload, idempotency_key=m.idempotency_key)
                    m.processed = True
                    m.processed_at = datetime.now(timezone.utc)
                    m.stream_id = str(stream_id)
                    m.attempts += 1
                    published += 1
                except Exception as e:
                    m.attempts += 1
                    m.last_error = f"{type(e).__name__}: {str(e)[:300]}"
            if published or msgs:
                await s.commit()
        return published

    async def recover_stuck_runs(self) -> int:
        """Stuck-run recovery: EXECUTING runs with heartbeat/lease expired -> FAILED + requeue."""
        recovered = 0
        cutoff = datetime.now(timezone.utc) - self._stuck_threshold
        async with async_session_factory() as s:
            # also consider lease_expires_at
            res = await s.execute(
                select(models.Run).where(
                    models.Run.status == models.RunStatus.EXECUTING.value,
                )
            )
            runs = list(res.scalars().all())
            for r in runs:
                heartbeat = r.heartbeat_at or r.updated_at
                lease_expired = r.lease_expires_at and r.lease_expires_at < datetime.now(timezone.utc)
                stuck = (heartbeat and heartbeat < cutoff) or lease_expired
                if not stuck:
                    continue
                # mark failed and emit event, then requeue via outbox if retry budget remains
                r.status = models.RunStatus.FAILED.value
                r.error = "stuck_run_recovered"
                r.finished_at = datetime.now(timezone.utc)
                r.heartbeat_at = datetime.now(timezone.utc)
                seq_max = 0
                try:
                    # get max seq for run
                    from sqlalchemy import func
                    q = await s.execute(select(func.max(models.RunEvent.seq)).where(models.RunEvent.run_id == r.id))
                    seq_max = int(q.scalar() or 0)
                except Exception:
                    seq_max = 0
                s.add(models.RunEvent(run_id=r.id, seq=seq_max + 1, event_type="STUCK_RECOVERED", payload={"reason": "lease_expired", "worker_id": r.worker_id}))
                # retry_count artır + DLQ/requeue kararı
                retry = (r.retry_count or 0) + 1
                r.retry_count = retry
                if retry > 3:
                    # max retry aşıldı → DLQ
                    try:
                        from observability.queue import publish_to_dlq
                        publish_to_dlq(self.redis, {"run_id": str(r.id), "task_id": str(r.task_id), "retry_of": str(r.id)},
                                       reason="max_retries_exceeded")
                        s.add(models.RunEvent(run_id=r.id, seq=seq_max + 2, event_type="DLQ", payload={"retry_count": retry}))
                    except Exception:
                        pass
                else:
                    # exponential backoff ile requeue
                    backoff_sec = 30 * (2 ** (retry - 1))  # 30s, 60s, 120s
                    try:
                        new_run = models.Run(
                            task_id=r.task_id,
                            status=models.RunStatus.QUEUED.value,
                            token_budget=r.token_budget,
                            cost_budget=r.cost_budget,
                            retry_count=retry,
                        )
                        s.add(new_run)
                        await s.flush()
                        ob = models.OutboxMessage(
                            topic="raptor.run_queued",
                            payload={"run_id": str(new_run.id), "task_id": str(new_run.task_id), "retry_of": str(r.id)},
                            idempotency_key=f"retry:{r.id}:{new_run.id}",
                            processed=False,
                        )
                        s.add(ob)
                        s.add(models.RunEvent(run_id=new_run.id, seq=0, event_type="RETRY_QUEUED", payload={"from_run": str(r.id), "backoff_sec": backoff_sec}))
                    except Exception:
                        pass
                recovered += 1
            if recovered:
                await s.commit()
        return recovered

    async def check_sources(self) -> int:
        """Gerçek kaynak işleri: etkin kaynaklar için gözlem oluştur, task/run yarat."""
        published = await self.publish_outbox()
        recovered = await self.recover_stuck_runs()
        async with async_session_factory() as s:
            res = await s.execute(select(models.Source).where(models.Source.is_enabled.is_(True)))
            sources = list(res.scalars().all())
            for src in sources:
                # backoff check
                if src.backoff_until and src.backoff_until > datetime.now(timezone.utc):
                    continue
                # for each enabled source, optionally create a surveillance task if no recent run
                # MVP: create a Task+Run+Outbox per source once per scheduler tick if last_accessed_at stale (>1h)
                stale = not src.last_accessed_at or (datetime.now(timezone.utc) - src.last_accessed_at) > timedelta(hours=1)
                if stale:
                    try:
                        # idempotent per source per hour
                        idem = f"source:{src.id}:{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H')}"
                        # check existing task with same idempotency
                        ex = await s.execute(select(models.Task).where(models.Task.idempotency_key == idem))
                        if ex.scalar_one_or_none() is not None:
                            src.last_accessed_at = datetime.now(timezone.utc)
                            continue
                        task = models.Task(
                            title=f"Kaynak gözetimi: {src.name}",
                            prompt=f"Kaynak {src.name} ({src.source_type}) gözetimi: değişiklikleri tara, kanıt topla, rapor üret.",
                            scope={"source_id": str(src.id), "source_type": src.source_type},
                            budget={"max_iterations": 10},
                            idempotency_key=idem,
                        )
                        s.add(task)
                        await s.flush()
                        run = models.Run(task_id=task.id, status=models.RunStatus.QUEUED.value,
                                         token_budget=settings.RUN_MAX_TOKEN_BUDGET,
                                         cost_budget=settings.RUN_MAX_COST_BUDGET)
                        s.add(run)
                        await s.flush()
                        ob = models.OutboxMessage(
                            topic="raptor.run_queued",
                            payload={"run_id": str(run.id), "task_id": str(task.id), "source_id": str(src.id)},
                            idempotency_key=f"run:{run.id}",
                            processed=False,
                        )
                        s.add(ob)
                        s.add(models.RunEvent(run_id=run.id, seq=0, event_type="QUEUED", payload={"source_id": str(src.id)}))
                        src.last_accessed_at = datetime.now(timezone.utc)
                    except Exception:
                        await s.rollback()
                        continue
            if sources:
                try:
                    await s.commit()
                except Exception:
                    await s.rollback()
        return len(sources)

    async def run(self) -> None:
        while True:
            try:
                n = await self.check_sources()
            except Exception:
                pass
            await asyncio.sleep(self.interval)


@app.on_event("startup")
async def _start():
    loop = SchedulerLoop(interval_seconds=60)
    asyncio.create_task(loop.run())
