# RAPTOR — ApprovalService (onay kaydı oluşturma + atomik karar + consume + replay koruması)
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from observability import models
from policy.engine import action_hash


class ApprovalService:
    """Ortak onay servisi — Telegram ve Web UI aynı yolu kullanır."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def create(
        self,
        *,
        run_id: str,
        action_id: str,
        tool: str,
        arguments: dict,
        action_class: str,
        target: str,
        impact_summary: str = "",
        ttl_seconds: int = 3600,
    ) -> models.Approval:
        payload = {"action_id": action_id, "tool": tool, "arguments": arguments}
        h = action_hash(action_class, target, payload)
        a = models.Approval(
            action_class=action_class,
            action_hash=h,
            target=target,
            impact_summary=impact_summary,
            payload=payload,
            status=models.ApprovalStatus.PENDING.value,
            run_id=uuid.UUID(run_id) if run_id else None,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        self.s.add(a)
        await self.s.flush()
        return a

    async def decide(self, approval_id: str, decision: str, user_id: str) -> models.Approval:
        """Atomik karar: SELECT FOR UPDATE + expiry + status + role (çağıranda) kontrolü."""
        try:
            uid = uuid.UUID(approval_id)
        except ValueError:
            raise ValueError("approval_id geçersiz") from None
        # SELECT ... FOR UPDATE — aynı anda ikinci kararı engeller
        res = await self.s.execute(
            select(models.Approval).where(models.Approval.id == uid).with_for_update()
        )
        a = res.scalar_one_or_none()
        if a is None:
            raise ValueError("onay bulunamadı")
        if a.status != models.ApprovalStatus.PENDING.value:
            raise ValueError(f"zaten karara bağlanmış: {a.status}")
        if a.expires_at and a.expires_at < datetime.now(UTC):
            a.status = models.ApprovalStatus.EXPIRED.value
            raise ValueError("onay süresi dolmuş")
        if decision not in ("approve", "reject"):
            raise ValueError("decision approve|reject olmalı")
        a.status = models.ApprovalStatus.APPROVED.value if decision == "approve" else models.ApprovalStatus.REJECTED.value
        a.decision = decision
        a.decided_by_user_id = uuid.UUID(user_id) if user_id else None
        await self.s.flush()
        return a

    async def get(self, approval_id: str) -> models.Approval | None:
        try:
            uid = uuid.UUID(approval_id)
        except ValueError:
            return None
        return await self.s.get(models.Approval, uid)

    async def consume(self, approval_id: str) -> bool:
        """Onaylandıktan sonra tek kullanımlık işaretle (replay koruması)."""
        try:
            uid = uuid.UUID(approval_id)
        except ValueError:
            return False
        res = await self.s.execute(
            select(models.Approval).where(models.Approval.id == uid).with_for_update()
        )
        a = res.scalar_one_or_none()
        if a is None:
            return False
        if a.status != models.ApprovalStatus.APPROVED.value:
            return False  # yalnız APPROVED tüketilebilir; CONSUMED/PENDING reddedilir
        a.status = models.ApprovalStatus.CONSUMED.value
        await self.s.flush()
        return True
