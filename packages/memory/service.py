# RAPTOR — Memory service (yaşam döngüsü: CANDIDATE -> ... -> ACTIVE/SUPERSEDED)
# Model doğrudan kalıcı gerçek yazamaz; run sonunda memory candidate üretir.
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from observability.models import MemoryItem, MemoryRelation, MemoryStatus


class MemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_candidate(
        self,
        *,
        content: str,
        source: str,
        confidence: float = 0.5,
        ttl_seconds: int | None = None,
        category: str | None = None,
        observed_at: datetime | None = None,
    ) -> MemoryItem:
        item = MemoryItem(
            content=content,
            source=source,
            confidence=max(0.0, min(1.0, confidence)),
            ttl=ttl_seconds,
            status=MemoryStatus.CANDIDATE.value,
            verification_status="unverified",
            observed_at=observed_at or datetime.now(timezone.utc),
            category=category,
            expires_at=(
                datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
                if ttl_seconds else None
            ),
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def approve(self, memory_id: uuid.UUID, auto: bool = False) -> MemoryItem | None:
        item = await self.session.get(MemoryItem, memory_id)
        if item is None:
            return None
        item.status = MemoryStatus.AUTO_APPROVED.value if auto else MemoryStatus.APPROVED.value
        item.verification_status = "verified"
        await self.session.flush()
        return item

    async def reject(self, memory_id: uuid.UUID) -> None:
        item = await self.session.get(MemoryItem, memory_id)
        if item:
            item.status = MemoryStatus.REJECTED.value

    async def mark_active(self, memory_id: uuid.UUID) -> None:
        item = await self.session.get(MemoryItem, memory_id)
        if item:
            item.status = MemoryStatus.ACTIVE.value

    async def supersede(self, old_id: uuid.UUID, new_id: uuid.UUID) -> None:
        self.session.add(
            MemoryRelation(
                from_memory_id=new_id,
                to_memory_id=old_id,
                relation_type="supersedes",
            )
        )
        old = await self.session.get(MemoryItem, old_id)
        if old:
            old.status = MemoryStatus.SUPERSEDED.value

    async def link_contradiction(self, a_id: uuid.UUID, b_id: uuid.UUID) -> None:
        self.session.add(MemoryRelation(from_memory_id=a_id, to_memory_id=b_id, relation_type="contradicts"))

    async def search(self, q: str, status: str | None = None, limit: int = 20) -> list[MemoryItem]:
        stmt = select(MemoryItem).where(MemoryItem.content.ilike(f"%{q}%"))
        if status:
            stmt = stmt.where(MemoryItem.status == status)
        stmt = stmt.order_by(MemoryItem.confidence.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_status(self, status: str, limit: int = 50) -> list[MemoryItem]:
        res = await self.session.execute(
            select(MemoryItem).where(MemoryItem.status == status).order_by(MemoryItem.created_at.desc()).limit(limit)
        )
        return list(res.scalars().all())