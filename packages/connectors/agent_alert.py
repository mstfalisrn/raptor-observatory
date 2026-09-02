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

    # Telegram'a göndermeyi dene
    try:
        from agent_core.telegram import get_service  # type: ignore
        svc = get_service()
        # preferred API — send_to_allowed
        if hasattr(svc, "send_to_allowed"):
            try:
                ok = await svc.send_to_allowed(msg)
                if ok:
                    log.info("risk alert gönderildi: tier=%s room=%s", tier, getattr(evaluation, "room", evaluation.get("room") if isinstance(evaluation, dict) else "?"))
                    return True
                log.warning("risk alert send_to_allowed False döndü: %s", msg[:200])
                return False
            except Exception as e:
                log.warning("risk alert send_to_allowed hata: %s", e)
                # fallback: logla
                log.warning("RISK ALERT (fallback log) %s", msg)
                return False
        # fallback: send logic yoksa log
        log.warning("TelegramService.send_to_allowed yok — fallback log: %s", msg)
        return False
    except Exception as e:
        # import veya service hatası -> fallback log (import hatasız kontrata uyar)
        log.warning("risk alert Telegram erişilemedi (%s) — fallback log: %s", type(e).__name__, msg)
        try:
            # still try to keep visible
            log.warning("RISK ALERT (fallback) %s", msg)
        except Exception:
            pass
        return False
