# RAPTOR — gizlilik/redaction yardımcıları
# Sırlar, token, authorization header, cookie, token pattern ve runtime env değerleri
# modele/semantic memory'ye girmeden önce redakte edilir.
# Faz4: DLP katılaştırıldı — private key, AWS, yüksek entropi, env literal bloklama
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
    # Private key
    (re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"), "<PRIVATE_KEY_REDACTED>"),
    # AWS Access Key / Secret
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<AWS_KEY_REDACTED>"),
    (re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*(\S+)"), r"aws_secret_access_key=<REDACTED>"),
    # Generic high-entropy password assignment
    (re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\";]{8,})['\"]?"), r"\1=<REDACTED>"),
    # Database URL with password
    (re.compile(r"(?i)(postgresql|postgres|mysql|mongodb)(://[^:]+:)([^@]+)(@)"), r"\1\2<REDACTED>\4"),
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
    # ekstra: yüksek entropi patternleri ikinci tur
    for pat in _SECRET_VALUE_PATTERNS:
        try:
            # hex/base64 benzeri uzun stringleri ENV_REDACTED zaten kapsar; burada generic
            # Not: sadece hex 32+ zaten _PATTERNS'te yok, o yüzden burada uygula
            # Literal env değerleri zaten _PATTERNS'te, tekrar etme
            if pat.pattern.startswith("\\b[0-9A-Fa-f]") or pat.pattern.startswith("\\b[A-Za-z0-9+/]"):
                out = pat.sub("<SECRET_REDACTED>", out)
        except Exception:
            continue
    return out


def contains_secret(text: str) -> bool:
    """DLP: metin gizli değer içeriyor mu? (block/flag için hızlı kontrol)."""
    if not text:
        return False
    # redacted versiyon farklıysa secret vardı
    return redact(text) != text


def scrub_and_flag(text: str) -> tuple[str, bool]:
    """DLP helper: redact et ve secret var mıydı döndür."""
    if not text:
        return text, False
    scrubbed = redact(text)
    had_secret = scrubbed != text
    return scrubbed, had_secret


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

    def contains_secret(self, text: str) -> bool:
        return contains_secret(text) or any(pat.search(text) for pat, _ in self._extra)

    def scrub_and_flag(self, text: str) -> tuple[str, bool]:
        scrubbed = self.scrub(text)
        return scrubbed, scrubbed != text
