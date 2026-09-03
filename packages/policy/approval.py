# LUMI — ApprovalService (onay kaydı oluşturma + atomik karar + consume + replay koruması + continuation + idempotent execution)
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
        res = await self.s.execute(
            select(models.Approval).where(models.Approval.id == uid).with_for_update()
        )
        a = res.scalar_one_or_none()
        if a is None:
            raise ValueError("onay bulunamadı")
        if a.status != models.ApprovalStatus.PENDING.value:
            raise ValueError(f"zaten karara bağlanmış: {a.status}")
        # expiry: aware/naive karşılaştırma için naive ise UTC aware yap
        expires = a.expires_at
        if expires is not None:
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires < datetime.now(UTC):
                a.status = models.ApprovalStatus.EXPIRED.value
                await self.s.flush()
                raise ValueError("onay süresi dolmuş")
        if decision not in ("approve", "reject"):
            raise ValueError("decision approve|reject olmalı")
        a.status = models.ApprovalStatus.APPROVED.value if decision == "approve" else models.ApprovalStatus.REJECTED.value
        a.decision = decision
        a.decided_by_user_id = uuid.UUID(user_id) if user_id else None
        await self.s.flush()
        return a

    async def decide_with_continuation(
        self, approval_id: str, decision: str, user_id: str
    ) -> models.Approval:
        """Web+Telegram ortak atomik continuation: approve+Run transition+outbox aynı transaction'da.

        - PENDING -> APPROVED/REJECTED
        - run WAITING_APPROVAL -> QUEUED (approve) veya FAILED (reject) atomik
        - outbox lumi.run_queued idempotent (approve:{id}) aynı transaction içinde
        """
        a = await self.decide(approval_id, decision, user_id)
        # atomik run transition + outbox — aynı session transaction içinde
        if a.run_id:
            # run'ı da kilitle
            run = await self.s.get(models.Run, a.run_id, with_for_update=True)  # type: ignore[call-arg]
            # fallback: with_for_update get yoksa select for update
            if run is None:
                res = await self.s.execute(
                    select(models.Run).where(models.Run.id == a.run_id).with_for_update()
                )
                run = res.scalar_one_or_none()
            if run is not None:
                if decision == "approve":
                    if run.status == models.RunStatus.WAITING_APPROVAL.value:
                        run.status = models.RunStatus.QUEUED.value
                        run.control_request = None
                    # outbox atomik — aynı transaction; failure flush'ta raise eder, yutulmaz
                    self.s.add(
                        models.OutboxMessage(
                            topic="lumi.run_queued",
                            payload={"run_id": str(run.id), "approval_id": str(a.id)},
                            idempotency_key=f"approve:{a.id}",
                            processed=False,
                        )
                    )
                else:  # reject
                    if run.status == models.RunStatus.WAITING_APPROVAL.value:
                        run.status = models.RunStatus.FAILED.value
                        run.error = "approval_rejected"
                        run.finished_at = datetime.now(UTC)
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
            return False  # only APPROVED can be consumed; CONSUMED/PENDING are rejected
        a.status = models.ApprovalStatus.CONSUMED.value
        await self.s.flush()
        return True

    async def consume_and_record(
        self, approval_id: str, run_id: str
    ) -> tuple[bool, models.Approval | None, models.ActionExecution | None]:
        """Crash-safe consume + idempotent execution kaydı atomik.

        - APPROVED -> CONSUMED tek sefer (FOR UPDATE)
        - ActionExecution(approval_id unique) PENDING olarak eklenir; aynı approval ikinci consume
          UniqueViolation ile engellenir.
        - consume-sonra-crash durumunda approval CONSUMED + execution PENDING kalır; recovery
          FAIL-CLOSED: public write tekrar çalıştırılmaz, AMBIGUOUS işaretlenir.
        Returns: (consumed, approval, execution)
        """
        try:
            aid = uuid.UUID(approval_id)
            rid = uuid.UUID(run_id)
        except ValueError:
            return False, None, None
        res = await self.s.execute(
            select(models.Approval).where(models.Approval.id == aid).with_for_update()
        )
        a = res.scalar_one_or_none()
        if a is None:
            return False, None, None
        # expiry aware/naive
        if a.expires_at is not None:
            exp = a.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if exp < datetime.now(UTC):
                if a.status == models.ApprovalStatus.PENDING.value:
                    a.status = models.ApprovalStatus.EXPIRED.value
                    await self.s.flush()
                return False, a, None
        if a.status == models.ApprovalStatus.CONSUMED.value:
            ex_res = await self.s.execute(
                select(models.ActionExecution).where(models.ActionExecution.approval_id == aid)
            )
            ex = ex_res.scalar_one_or_none()
            return False, a, ex
        if a.status != models.ApprovalStatus.APPROVED.value:
            return False, a, None
        a.status = models.ApprovalStatus.CONSUMED.value
        payload = a.payload or {}
        action_id = payload.get("action_id") or str(a.id)
        tool = payload.get("tool") or ""
        ex = models.ActionExecution(
            approval_id=aid,
            run_id=rid,
            action_id=action_id,
            tool=tool,
            status="PENDING",
            result={},
        )
        self.s.add(ex)
        await self.s.flush()
        return True, a, ex

    async def mark_execution_result(
        self, approval_id: str, status: str, result: dict | None = None
    ) -> None:
        try:
            aid = uuid.UUID(approval_id)
        except ValueError:
            return
        res = await self.s.execute(
            select(models.ActionExecution).where(models.ActionExecution.approval_id == aid)
        )
        ex = res.scalar_one_or_none()
        if ex is not None:
            ex.status = status
            if result is not None:
                ex.result = result
            await self.s.flush()
