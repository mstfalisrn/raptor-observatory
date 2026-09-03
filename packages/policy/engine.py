# LUMI — politika + onay motoru
# Her tool call: ALLOW | REQUIRE_APPROVAL | DENY
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json

from observability.config import settings
from observability.models import ActionClass


@dataclasses.dataclass
class PolicyDecision:
    action_class: str
    decision: str  # ALLOW | REQUIRE_APPROVAL | DENY
    reason: str = ""
    requires_faz_approval: bool = False


# Varsayılan araç -> eylem sınıfı haritası (kayıtlı/şemalı araçlar)
TOOL_TO_ACTION = {
    # Connectors
    "technocore_read": ActionClass.READ_ONLY.value,
    "github_repo_read": ActionClass.READ_ONLY.value,
    "http_json_read": ActionClass.READ_ONLY.value,
    "internal_health": ActionClass.READ_ONLY.value,
    # Yazma
    "technocore_signed_write": ActionClass.PUBLIC_WRITE.value,
    "db_self_write": ActionClass.SAFE_WRITE.value,   # yalnız LUMI'un kendi DB'si
    # Politika / yetki
    "apply_privileged": ActionClass.PRIVILEGED_HOST.value,
    "destructive_op": ActionClass.DESTRUCTIVE.value,
}

# Faz onayı gerektiren aşamalar (public write, privileged host, destructive)
_GATED = {
    ActionClass.PUBLIC_WRITE.value,
    ActionClass.PRIVILEGED_HOST.value,
    ActionClass.DESTRUCTIVE.value,
}


class PolicyEngine:
    def __init__(self) -> None:
        self._overrides: dict[str, str] = {}

    def set_override(self, tool: str, decision: str) -> None:
        self._overrides[tool] = decision

    def set_auto_approve_classes(self, classes: set[str]) -> None:
        self._auto = set(classes)

    def decide(self, tool: str) -> PolicyDecision:
        if tool in self._overrides:
            return PolicyDecision(ActionClass.READ_ONLY.value, self._overrides[tool], "override")
        if tool not in TOOL_TO_ACTION:
            return PolicyDecision(ActionClass.DESTRUCTIVE.value, "DENY", f"bilinmeyen araç: {tool}")
        action_class = TOOL_TO_ACTION[tool]
        if action_class == ActionClass.DESTRUCTIVE.value:
            return PolicyDecision(action_class, "DENY", "destructive yalnız fasıl onayı")
        if action_class == ActionClass.PRIVILEGED_HOST.value:
            return PolicyDecision(action_class, "REQUIRE_APPROVAL", "host değişikliği insan onayı")
        if action_class in _GATED:
            return PolicyDecision(action_class, "REQUIRE_APPROVAL", "public write onayı")
        if action_class == ActionClass.SAFE_WRITE.value:
            return PolicyDecision(action_class, "ALLOW", "audit log'lu kendi DB yazımı")
        return PolicyDecision(action_class, "ALLOW", f"otomatik ({action_class})")


def canonical_json(payload: dict) -> str:
    """Sıralı, kompakt canonical JSON — hash bağlaması için deterministik."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def action_hash(action_class: str, target: str, payload: dict) -> str:
    """Tek kullanımlık onay eylemine bağlı hash — onay başka içeriğe taşınamaz."""
    material = canonical_json({"action_class": action_class, "target": target, "payload": payload})
    return hashlib.sha256(material.encode()).hexdigest()


def build_approval_token(approval_id: str, action_hash: str, user_id: str, expiry: int) -> str:
    """Callback/onay kaydı: HMAC-SHA256 (düz SHA-256 değil) — JWT_SECRET anahtarlı."""
    raw = f"{approval_id}:{action_hash}:{user_id}:{expiry}"
    return hmac.new(settings.JWT_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()