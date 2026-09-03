# RAPTOR — Agent risk alert -> Telegram (M4)
# RISKY / DANGEROUS tier için format: room, nick/did, skor, neden, link
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("raptor.agent_alert")

# tiers that trigger alert
_ALERT_TIERS = {"RISKY", "DANGEROUS"}


def _format_msg(ev: Any) -> str:
    """Evaluation (ORM or dict) -> Telegram mesajı."""
    # duck-typing: ev may be AgentEvaluation ORM or dict
    def _get(k: str, default: Any = "") -> Any:
        if isinstance(ev, dict):
            return ev.get(k, default)
        return getattr(ev, k, default)

    room = str(_get("room", "-") or "-")
    nick = str(_get("nick", "") or "")
    did = str(_get("did", "") or "")
    who = nick or did or "unknown"
    # did varsa nick/did formatla
    if nick and did:
        who = f"{nick} ({did[:16]}…)" if len(did) > 16 else f"{nick} ({did})"
    elif did:
        who = did

    score = _get("score", _get("skor", "-"))
    tier = str(_get("tier", "UNKNOWN") or "UNKNOWN").upper()
    reason = str(_get("reason", _get("neden", "")) or "").strip()
    if len(reason) > 400:
        reason = reason[:400] + "…"

    link = f"https://technocore.chat/r/{room}" if room and room != "-" else "https://technocore.chat"
    # emoji by tier
    icon = "🔴" if tier == "DANGEROUS" else "🟠" if tier == "RISKY" else "⚪"

    msg = (
        f"{icon} *RAPTOR risk alert — {tier}*\n"
        f"• *room*: `{room}`\n"
        f"• *agent*: `{who}`\n"
        f"• *skor*: `{score}`\n"
        f"• *neden*: {reason or '-'}\n"
        f"• *link*: {link}"
    )
    return msg


async def send_risk_alert(evaluation: Any) -> bool:
    """RISKY/DANGEROUS evaluation için Telegram'a alert gönder.

    - evaluation: AgentEvaluation ORM veya dict (room, nick, did, score, tier, reason)
    - SAFE/UNKNOWN tier ise sessizce False döner (alert yok).
    - TelegramService.get_service().send_to_allowed(msg) varsa onu kullanır,
      yoksa fallback olarak log.warning ile kaydeder (import hatasız).
    - Başarıda True, atlanırsa/bağlantı yoksa False.
    """
    try:
        tier = ""
        if isinstance(evaluation, dict):
            tier = str(evaluation.get("tier", "")).upper()
        else:
            tier = str(getattr(evaluation, "tier", "") or "").upper()
    except Exception:
        tier = ""

    if tier not in _ALERT_TIERS:
        log.debug("risk alert atlandı: tier=%s", tier)
        return False

    msg = _format_msg(evaluation)

    # Telegram'a göndermeyi dene — scheduler'da `telegram` paketi yok, direkt Bot API kullan
    try:
        from observability.config import settings as _settings
        from observability.db import async_session_factory as _session_factory
        from observability import models as _models
        token = getattr(_settings, "TELEGRAM_BOT_TOKEN", "") or ""
        if token:
            recipients: set[int] = set()
            try:
                recipients.update(int(x) for x in getattr(_settings, "allowed_user_ids", []) or [])
            except Exception:
                pass
            try:
                async with _session_factory() as _s:
                    from sqlalchemy import select as _select
                    res = await _s.execute(_select(_models.TelegramIdentity.telegram_user_id).where(_models.TelegramIdentity.is_allowed == True))  # noqa: E712
                    for row in res.scalars().all():
                        try:
                            recipients.add(int(row))
                        except Exception:
                            pass
            except Exception:
                pass
            if recipients:
                import httpx as _httpx
                ok_any = False
                for uid in recipients:
                    try:
                        async with _httpx.AsyncClient(timeout=10) as _client:
                            r = await _client.post(
                                f"https://api.telegram.org/bot{token}/sendMessage",
                                json={"chat_id": uid, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True},
                            )
                            if r.status_code == 200 and r.json().get("ok"):
                                ok_any = True
                            else:
                                log.warning("risk alert http %s: %s", r.status_code, r.text[:200])
                    except Exception as e:
                        log.warning("risk alert http hata uid=%s: %s", uid, type(e).__name__)
                if ok_any:
                    log.info("risk alert gönderildi (httpx): tier=%s room=%s", tier, getattr(evaluation, "room", evaluation.get("room") if isinstance(evaluation, dict) else "?"))
                    return True
                log.warning("risk alert httpx alıcılara ulaşamadı")
            else:
                log.warning("risk alert: alıcı yok (allowlist boş) — fallback log")
        else:
            log.debug("risk alert: TELEGRAM_BOT_TOKEN boş — fallback log")
    except Exception as e:
        log.warning("risk alert httpx yol hata (%s): %s", type(e).__name__, e)
    # fallback: agent_core.telegram varsa dene (api container'da)
    try:
        from agent_core.telegram import get_service  # type: ignore
        svc = get_service()
        if hasattr(svc, "send_to_allowed"):
            try:
                ok = await svc.send_to_allowed(msg)
                if ok:
                    log.info("risk alert gönderildi (agent_core): tier=%s room=%s", tier, getattr(evaluation, "room", evaluation.get("room") if isinstance(evaluation, dict) else "?"))
                    return True
                log.warning("risk alert send_to_allowed False: %s", msg[:200])
                return False
            except Exception as e:
                log.warning("risk alert send_to_allowed hata: %s", e)
                log.warning("RISK ALERT (fallback log) %s", msg)
                return False
        log.warning("TelegramService.send_to_allowed yok — fallback log: %s", msg)
        return False
    except Exception as e:
        log.warning("risk alert Telegram erişilemedi (%s) — fallback log: %s", type(e).__name__, msg)
        try:
            log.warning("RISK ALERT (fallback) %s", msg)
        except Exception:
            pass
        return False
