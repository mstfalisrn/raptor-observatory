# RAPTOR — Telegram bot
# Yalnız onaylı numeric user ID'ye yanıt; '*' / allow-all YASAK.
# Polling (ilk kurulum) + webhook (production). update_id ile idempotent.
from __future__ import annotations

import hashlib
import logging
import uuid

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext

from observability.config import settings
from observability.db import async_session_factory
from observability import models
from observability.security import redact

log = logging.getLogger("raptor.telegram")


class TelegramService:
    def __init__(self) -> None:
        self.token = settings.TELEGRAM_BOT_TOKEN
        self._app: Application | None = None

    def allowed(self, user_id: int) -> bool:
        allowed = settings.allowed_user_ids
        return bool(allowed) and user_id in allowed

    # --- handlers ---
    async def _require(self, update: Update, ctx) -> bool:
        uid = update.effective_user.id if update.effective_user else None
        if not uid or not self.allowed(uid):
            try:
                await update.effective_message.reply_text("⛔ Erişimin yok.")
            except Exception:
                pass
            return False
        return True

    async def cmd_start(self, update: Update, context: CallbackContext) -> None:
        await update.effective_message.reply_text(
            "🐦 RAPTOR Observatory /start\n/help /status /ask /task /watch /runs /last /approve /reject /pause /resume /stop /memory"
        )

    async def cmd_help(self, update: Update, context: CallbackContext) -> None:
        await self.cmd_start(update, context)

    async def cmd_status(self, update: Update, context: CallbackContext) -> None:
        if not await self._require(update, context):
            return
        from observability.config import get_settings
        s = get_settings()
        await update.effective_message.reply_text(
            f"ℹ️ RAPTOR durumu\nProvider: {s.LLM_PROVIDER}\n"
            f"LLM: {s.LLM_MODEL or '-'}\nTG allowlist: {len(s.allowed_user_ids)} kullanıcı\n"
            f"Telegram: {'configured' if self.token else 'TOKEN YOK'}"
        )

    async def cmd_runs(self, update: Update, context: CallbackContext) -> None:
        if not await self._require(update, context):
            return
        async with async_session_factory() as s:
            from sqlalchemy import select
            res = await s.execute(select(models.Run).order_by(models.Run.created_at.desc()).limit(8))
            runs = res.scalars().all()
        if not runs:
            await update.effective_message.reply_text("Henüz run yok.")
            return
        lines = [f"{str(r.id)[:8]} · {r.status}" for r in runs]
        await update.effective_message.reply_text("📋 Son run'lar:\n" + "\n".join(lines))

    # --- token asla loglanmaz ---
    def _redact_error(self, exc: Exception) -> str:
        return redact(str(exc))

    async def build(self) -> Application:
        self._app = Application.builder().token(self.token).build()
        self._app.add_handler(CommandHandler("start", self.cmd_start))
        self._app.add_handler(CommandHandler("help", self.cmd_help))
        self._app.add_handler(CommandHandler("status", self.cmd_status))
        self._app.add_handler(CommandHandler("runs", self.cmd_runs))
        return self._app


def ensure_user_id_in_allowlist(user_id: int):
    """Bir Telegram kullanıcısını (onaylı aday) allowlist'e ekler. Uygulama restart'ı ile geçer."""
    from observability.config import get_settings
    s = get_settings()
    current = set(s.allowed_user_ids)
    current.add(int(user_id))
    s.TELEGRAM_ALLOWED_USER_IDS = ",".join(str(x) for x in sorted(current))