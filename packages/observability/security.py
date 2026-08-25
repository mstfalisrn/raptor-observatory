# RAPTOR — gizlilik/redaction yardımcıları
# Sırlar, token, authorization header, cookie, token pattern ve env değerleri
# modele/semantic memory'ye girmeden önce redakte edilir.
from __future__ import annotations

import os
import re

_PATTERNS: list = [
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

# Harici girdilerden redakte edilecek genel sihirbaz regex'ler
_SECRET_VALUE_PATTERNS = [
    re.compile(r"\b[0-9A-Fa-f]{32,}\b"),          # hex 32+
    re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b"),   # base64-ish
]

_loaded_env_secrets: set[str] = set()


def load_secrets_from_env(environ: dict[str, str] | None = None) -> None:
    """Mevcut ortam değerlerini redaksiyon setine ekle (değerleri saklamadan pattern üretir)."""
    env = environ or dict(os.environ)
    for _k, v in env.items():
        if v and len(v) >= 12 and not v.startswith("/"):
            # uzun secret değerlerini regex'e çevir; sadece hash değil, gerçek değeri tutma
            _SECRET_VALUE_PATTERNS.append(re.compile(re.escape(v)))
    # canlı regex'e ekle
    for pat in _SECRET_VALUE_PATTERNS:
        _PATTERNS.append((pat, "<ENV_REDACTED>"))


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
        self._extra: list = []

    def add_literal(self, value: str) -> None:
        if value and len(value) >= 4:
            self._extra.append((re.compile(re.escape(value)), "<SECRET_REDACTED>"))

    def scrub(self, text: str) -> str:
        out = redact(text)
        for pat, repl in self._extra:
            out = pat.sub(repl, out)
        return out