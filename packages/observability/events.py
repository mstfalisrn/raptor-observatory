# LUMI — RunEvent tek yazma yolu
# Tüm production RunEvent insertleri bu modül üzerinden gitmeli.
# - PostgreSQL: pg_advisory_xact_lock(727271) ZORUNLU (commit order serialization)
# - Run satırı FOR UPDATE
# - max seq -1 bazlı (ilk event seq 0)
# - global_seq Identity (PG) / MAX+1 (SQLite test fallback)
# Lock/dialect hatası yutulmaz.
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

import observability.db as db_mod
from observability import models


class CriticalEventPersistenceError(RuntimeError):
    """Typed critical persistence failure — PLAN/TOOL_CALL/AWAITING_APPROVAL için _handle_entry ACK'e gitmez."""


async def append_run_event_in_session(session, run_id: uuid.UUID, etype: str, payload: dict) -> models.RunEvent:
    """Verilmiş session/transaction içinde RunEvent ekle. Commit yapmaz, flush eder.

    Session zaten bir transaction içinde olmalı (async with session.begin() veya dış transaction).
    PG'de advisory lock ZORUNLU; hata yutulmaz. Run FOR UPDATE kilitlenir, seq -1 tabanlı üretilir.
    """
    bind = session.get_bind()
    dialect = ""
    try:
        dialect = bind.dialect.name if bind is not None else ""  # type: ignore
    except Exception:
        dialect = ""
    dialect = dialect.lower().strip()
    if "sqlite" in dialect:
        # sqlite test fallback
        pass
    elif "postgresql" in dialect or "postgres" in dialect or dialect.startswith("pg"):
        await session.execute(text("SELECT pg_advisory_xact_lock(727271)"))
    else:
        raise RuntimeError(f"unsupported dialect for RunEvent append: {dialect!r}")
    # per-run seq serialization
    await session.execute(select(models.Run).where(models.Run.id == run_id).with_for_update())
    max_res = await session.execute(
        select(func.coalesce(func.max(models.RunEvent.seq), -1)).where(models.RunEvent.run_id == run_id)
    )
    raw = max_res.scalar()
    max_seq = int(raw) if raw is not None else -1
    nxt = max_seq + 1
    if "sqlite" in dialect:
        max_g_res = await session.execute(select(func.coalesce(func.max(models.RunEvent.global_seq), 0)))
        max_g = int(max_g_res.scalar() or 0)
        ev = models.RunEvent(run_id=run_id, seq=nxt, global_seq=max_g + 1, event_type=etype, payload=payload or {})
    else:
        ev = models.RunEvent(run_id=run_id, seq=nxt, event_type=etype, payload=payload or {})
    session.add(ev)
    await session.flush()
    return ev


async def append_run_event_safe(run_id: uuid.UUID, etype: str, payload: dict, max_retries: int = 5) -> None:
    """Kendi transaction'ını açan wrapper — IntegrityError (seq/global_seq uniq) retry."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with db_mod.async_session_factory() as s:
                async with s.begin():
                    await append_run_event_in_session(s, run_id, etype, payload or {})
            return
        except IntegrityError as e:
            last_exc = e
            await asyncio.sleep(0.05 * (attempt + 1))
            continue
        except Exception as e:
            last_exc = e
            # kritik final hatası raise; retry sadece IntegrityError için
            if attempt == max_retries - 1:
                raise
            # non-integrity hatası da logla ama sadece son attempt raise — burada direkt raise et
            raise
    if last_exc is not None:
        raise last_exc
