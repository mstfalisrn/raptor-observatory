# RAPTOR — gizlilik/redaction yardımcıları
# Sırlar, token, authorization header, cookie, token pattern ve runtime env değerleri
# modele/semantic memory'ye girmeden önce redakte edilir.
from __future__ import annotations

import os
import re

# ——— Statik kalıplar ———
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Authorization / Bearer / api-key
    (re.compile(r"(?i)(authorization|bearer|api[_-]?key)\s*[:=]\s*(bearer\s+)?(\S+)"), r"\1=<REDACTED>"),
    # Telegram bot token: <digits>:<hex>
    (re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"), "<TG_TOKEN_REDACTED>"),
    # JWT
    (re.compile(r"\bey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "<JWT_REDACTED>"),
    # Genel secret uzun token
    (re.compile(r"\b(sk|pk|ghp|gho)_[A-Za-z0-9]{20,}\b"), "<SECRET_REDACTED>"),
    # --set env / ENV=
    (re.compile(r"(?i)(TELEGRAM_BOT_TOKEN|LLM_API_KEY|JWT_SECRET|[A-Z_]*PASSWORD)=(\S+)"), r"\1=<REDACTED>"),
]

# Harici girdilerden redakte edilecek genel regex'ler (hex/base64-ish)
_SECRET_VALUE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b[0-9A-Fa-f]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b"),
]

# Runtime env değerleri buraya eklenir — yalnızca bir kez
_loaded_env_secrets: set[str] = set()
# Hangi env anahtarlarının secret olduğu (dar liste — fail-closed değil, false positive azaltır)
_SECRET_KEY_HINTS = ("PASSWORD", "SECRET", "TOKEN", "API_KEY", "ENCRYPTION", "MASTER_KEY")
_PLACEHOLDERS = {"CHANGE_ME", "REPLACE_ME", "dev-only-change-me", "dev-webhook-secret", "dev-only-32-byte-master-key-0000000000", ""}


def _is_secret_key(key: str) -> bool:
    k = key.upper()
    return any(h in k for h in _SECRET_KEY_HINTS)


def load_secrets_from_env(environ: dict[str, str] | None = None) -> int:
    """Mevcut ortam değerlerini redaksiyon setine ekle. Dönüş: eklenen yeni değer sayısı.

    - Yalnızca secret-hint anahtarları ve uzun (>=12) ve filesystem path'i olmayan değerler.
    - Placeholder/CHANGE_ME değerleri atlanır.
    - Aynı değer ikinci kez eklenmez (idempotent).
    - Thread-unsafe ama idempotent; startup'ta bir kez çağrılması yeterli.
    """
    env = environ if environ is not None else dict(os.environ)
    added = 0
    for k, v in env.items():
        if not v or not isinstance(v, str):
            continue
        if v in _PLACEHOLDERS:
            continue
        if len(v) < 12:
            continue
        if v.startswith("/"):
            continue
        if not _is_secret_key(k):
            continue
        # placeholder alt-string içeriyorsa atla
        if "CHANGE_ME" in v or "REPLACE_ME" in v:
            continue
        if v in _loaded_env_secrets:
            continue
        # değeri literal olarak redakte et
        try:
            pat = re.compile(re.escape(v))
        except re.error:
            continue
        _loaded_env_secrets.add(v)
        _SECRET_VALUE_PATTERNS.append(pat)
        _PATTERNS.append((pat, "<ENV_REDACTED>"))
        added += 1
    return added


# Modül import'unda mevcut env'yi bir kez yükle (runtime secret'leri hemen redakte edilsin)
# Başarısız olursa sessiz geç — testlerde environ mock edilebilir
try:
    load_secrets_from_env()
except Exception:
    pass


def redact(text: str) -> str:
    """Belirgin secret/token/header kalıplarını maskeler."""
    if not text:
        return text
    out = text
    for pattern, repl in _PATTERNS:
        try:
            out = pattern.sub(repl, out)
        except Exception:
            continue
    return out


class Redactor:
    def __init__(self) -> None:
        self._extra: list[tuple[re.Pattern, str]] = []

    def add_literal(self, value: str) -> None:
        if value and len(value) >= 4:
            self._extra.append((re.compile(re.escape(value)), "<SECRET_REDACTED>"))

    def scrub(self, text: str) -> str:
        out = redact(text)
        for pat, repl in self._extra:
            out = pat.sub(repl, out)
        return out
