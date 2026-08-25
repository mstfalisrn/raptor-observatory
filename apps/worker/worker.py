# RAPTOR — Worker
# Redis kuyruğundan run alır, RunCoordinator ile yürütür, sonucu DB'ye yazar.
# Agent'a keyfi shell/docker YOK; yalnız kayıtlı şemalı araçlar.
from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import FastAPI
from sqlalchemy import select

from observability.config import settings
from observability.db import async_session_factory
from observability import models

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
        self.redis = redis_lib.from_url(settings.REDIS_URL)
        self.registry = build_default_registry(
            http_hosts=set(filter(None, settings.CONNECTOR_ALLOWED_HOSTS.split(","))) if settings.CONNECTOR_ALLOWED_HOSTS else None,
            technocore_key_path=settings.TECHNOCORE_ED25519_KEY_PATH or "/root/secrets/raptor-observatory/did.ed25519",
            technocore_base_url=settings.TECHNOCORE_BASE_URL,
        )
        self.provider = build_provider()
        self.planner = Planner()
        self.policy = PolicyEngine()
        self.verifier = DefaultVerifier()

    async def process_one(self) -> bool:
        raw = self.redis.rpop("raptor:queue")
        if not raw:
            return False
        payload = json.loads(raw)
        run_id = payload["run_id"]
        async with async_session_factory() as s:
            run = await s.get(models.Run, uuid.UUID(run_id))
            if run is None:
                return True
            task = await s.get(models.Task, run.task_id)
            task_dict = {"prompt": task.prompt, "scope": task.scope}
            executor = ToolExecutor(self.registry, task=task_dict)
            coordinator = RunCoordinator(
                run_id=run_id,
                budget=RunBudget(),
                allowlist_tools=set(),
            )
            coordinator.status = models.RunStatus.EXECUTING
            assembler = ContextAssembler(max_tokens=rum_budget(run))
            # descriptor: bağlam
            assembler.add("task_goal", task.prompt, title=task.title, relevance=1.0)
            try:
                status, executed, events = await coordinator.run(executor, self.planner,
                                                                 assembler, self.policy,
                                                                 self.provider, self.verifier)
            except Exception as exc:
                status = models.RunStatus.FAILED.value
                events = [{"event_type": "FATAL", "payload": {"error": type(exc).__name__}, "seq": 0}]
            run.status = status
            run.iteration = coordinator.iteration
            import datetime as _dt
            run.finished_at = _dt.datetime.now(_dt.timezone.utc)
            if status == models.RunStatus.FAILED.value:
                run.error = "worker_yurutme_hatasi"
            # event kaydı
            for ev in events:
                s.add(models.RunEvent(run_id=run.id, seq=ev["seq"], event_type=ev["event_type"], payload=ev.get("payload", {})))
            await s.commit()
        return True

    async def run(self) -> None:
        while True:
            try:
                processed = await self.process_one()
                if not processed:
                    await asyncio.sleep(1.0)
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