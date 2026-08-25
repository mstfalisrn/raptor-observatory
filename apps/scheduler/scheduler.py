# RAPTOR — Scheduler
# Periyodik görev/takip planlarını Redis kuyruğuna iter (worker'lar çeker).
from __future__ import annotations

import asyncio

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
        self.redis = redis_lib.from_url(settings.REDIS_URL)
        self.interval = interval_seconds

    async def check_sources(self) -> int:
        """Etkin kaynakları tara; değişiklik varsa göreve geçirir (MVP: sağlık kontrolü)."""
        async with async_session_factory() as s:
            res = await s.execute(select(models.Source).where(models.Source.is_enabled.is_(True)))
            sources = res.scalars().all()
        return len(sources)

    async def run(self) -> None:
        while True:
            try:
                n = await self.check_sources()
                if n:
                    # MVP: kaynak bazlı görevi kuyruğa atma işlemi (opsiyonel, guardrail'li)
                    pass
            except Exception:
                pass
            await asyncio.sleep(self.interval)


@app.on_event("startup")
async def _start():
    loop = SchedulerLoop(interval_seconds=60)
    asyncio.create_task(loop.run())