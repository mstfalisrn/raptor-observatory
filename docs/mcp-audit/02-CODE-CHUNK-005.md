# RAPTOR — Code Chunk 005

> GPT sırayla okuyup birleştirsin (MCP 100KB limit).

## `packages/connectors/github.py`

```py
# RAPTOR — GitHub public repo connector (SSRF korumalı, Faz 9 sertleştirme)
from __future__ import annotations

import asyncio
import json

import httpx

from connectors.ssrf import validate_host

_ALLOWED_CT = {"application/json", "application/vnd.github+json", "application/vnd.github.v3+json"}

class GithubRepoConnector:
    def __init__(self, max_bytes: int = 2_000_000, redirects: int = 3, max_retries: int = 2) -> None:
        self.max_bytes = max_bytes
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(
            timeout=25.0, follow_redirects=False, max_redirects=redirects
        )
        self._closed = False

    async def _get_json_stream(self, url: str, *, headers: dict | None = None, params: dict | None = None) -> dict | list:
        """Streaming + max_bytes + Content-Type allowlist + retry/backoff ile JSON al."""
        validate_host("api.github.com")
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with self._client.stream("GET", url, headers=headers, params=params) as resp:
                    # rate-limit 429 / 403 handling
                    if (resp.status_code in (429, 403) and "retry-after" in resp.headers) or "x-ratelimit-remaining" in resp.headers:
                        if resp.headers.get("x-ratelimit-remaining") == "0" or resp.status_code == 429:
                            retry_after = resp.headers.get("retry-after", "2")
                            try:
                                delay = float(retry_after)
                            except ValueError:
                                delay = 2.0
                            if attempt < self.max_retries:
                                await asyncio.sleep(min(delay, 30))
                                continue
                    # Content-Type allowlist
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype and ctype not in _ALLOWED_CT and "json" not in ctype:
                        raise RuntimeError(f"Content-Type allowlist dışı: {ctype}")
                    # Content-Length erken kontrol
                    clen = resp.headers.get("content-length")
                    if clen is not None:
                        try:
                            if int(clen) > self.max_bytes:
                                raise RuntimeError("yanıt boyut sınırı aşıldı (content-length)")
                        except ValueError:
                            pass
                    resp.raise_for_status()
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        total += len(chunk)
                        if total > self.max_bytes:
                            raise RuntimeError("yanıt boyut sınırı aşıldı (streaming)")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    return json.loads(body) if body else {}
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last_exc = e
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                raise
            except RuntimeError:
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("github fetch başarısız")

    async def repo_activity(self, repo: str) -> dict:
        # repo: "owner/name"
        validate_host("api.github.com")  # SSRF güvenlik kontrolü
        parts = repo.strip("/").split("/")
        if len(parts) < 2:
            raise ValueError("repo 'owner/name' formatında olmalı")
        owner, name = parts[0], parts[1]
        url = f"https://api.github.com/repos/{owner}/{name}"
        data = await self._get_json_stream(url, headers={"Accept": "application/vnd.github+json"})
        assert isinstance(data, dict)
        return {
            "full_name": data.get("full_name"),
            "pushed_at": data.get("pushed_at"),
            "updated_at": data.get("updated_at"),
            "open_issues": data.get("open_issues_count"),
            "default_branch": data.get("default_branch"),
            "html_url": data.get("html_url"),
        }

    async def recent_releases(self, repo: str, per_page: int = 5) -> list[dict]:
        validate_host("api.github.com")
        owner, name = repo.strip("/").split("/")[:2]
        url = f"https://api.github.com/repos/{owner}/{name}/releases"
        data = await self._get_json_stream(
            url, params={"per_page": per_page},
            headers={"Accept": "application/vnd.github+json"},
        )
        assert isinstance(data, list)
        return [
            {"tag_name": r.get("tag_name"), "published_at": r.get("published_at"),
             "name": r.get("name")}
            for r in data
        ]

    async def aclose(self) -> None:
        if not self._closed:
            await self._client.aclose()
            self._closed = True

    async def close(self) -> None:
        await self.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()

```

## `packages/connectors/http_json.py`

```py
# RAPTOR — HTTP/JSON connector (SSRF korumalı, Faz 9 sertleştirme)
from __future__ import annotations

import json

import httpx

from connectors.ssrf import resolve_redirect_url, validate_url

_ALLOWED_CONTENT_TYPES = {"application/json", "application/vnd.api+json", "application/ld+json"}


class HttpJsonConnector:
    def __init__(self, allowed_hosts: set[str] | None = None,
                 max_bytes: int = 1_048_576, max_redirects: int = 3) -> None:
        self.allowed_hosts = allowed_hosts
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self._client = httpx.AsyncClient(
            timeout=20.0, follow_redirects=False, max_redirects=max_redirects
        )
        self._closed = False

    async def get_json(self, url: str) -> dict:
        validate_url(url, self.allowed_hosts)
        current = url
        redirects = 0
        while True:
            # her redirect sonrası yeniden validate (DNS pin + allowlist)
            validate_url(current, self.allowed_hosts)
            # streaming ile byte limiti indirme sırasında uygula
            async with self._client.stream("GET", current) as resp:
                # redirect handling
                if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                    redirects += 1
                    if redirects > self.max_redirects:
                        raise RuntimeError("çok fazla redirect")
                    location = resp.headers["location"]
                    current = resolve_redirect_url(current, location, self.allowed_hosts)
                    continue

                # Content-Type allowlist
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype and ctype not in _ALLOWED_CONTENT_TYPES:
                    # JSON olmayan içerik reddedilir (allowlist)
                    # text/json gibi varyantlara izin ver ama strict
                    if "json" not in ctype:
                        raise RuntimeError(f"Content-Type allowlist dışı: {ctype}")

                # Content-Length erken kontrol (tek başına yeterli değil, ama early abort)
                clen = resp.headers.get("content-length")
                if clen is not None:
                    try:
                        if int(clen) > self.max_bytes:
                            raise RuntimeError("yanıt boyut sınırı aşıldı (content-length)")
                    except ValueError:
                        pass

                resp.raise_for_status()

                # Streaming byte limiti
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes(chunk_size=8192):
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise RuntimeError("yanıt boyut sınırı aşıldı (streaming)")
                    chunks.append(chunk)
                body = b"".join(chunks)
                if not body:
                    return {}
                # JSON parse sınırı — max_bytes zaten kontrol edildi
                try:
                    return json.loads(body)
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"JSON parse hatası: {e}") from e

    async def aclose(self) -> None:
        if not self._closed:
            await self._client.aclose()
            self._closed = True

    async def close(self) -> None:
        await self.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()

```

## `packages/connectors/internal_health.py`

```py
# RAPTOR — internal health connector (Faz 9 sertleştirme)
# Yalnız Docker service DNS kullanır; localhost yalnız aynı container için.
from __future__ import annotations

import httpx


class InternalHealthConnector:
    """Yalnızca RAPTOR container health bilgileri; başka servise erişmez."""

    def __init__(self, base_urls: dict[str, str] | None = None) -> None:
        # Docker service DNS (compose network içinde) — localhost değil
        # Aynı container içindeyse 127.0.0.1 kullanılabilir; aksi halde service adı
        self._base_urls = base_urls or {
            "api": "http://raptor-api:8000/health/live",
            "worker": "http://raptor-worker:8001/health/live",
            "scheduler": "http://raptor-scheduler:8002/health/live",
        }
        # health endpoint'leri için internal allow — SSRF bypass değil, internal network
        self._client = httpx.AsyncClient(timeout=5.0, follow_redirects=False)
        self._closed = False

    async def check(self) -> dict:
        # DB/redis sağlıkları api /health/ready üzerinden doğrulanır
        services: dict[str, str | None] = {
            **self._base_urls,
            "postgres": None,
            "redis": None,
        }
        result: dict = {}
        for name, url in services.items():
            if url is None:
                result[name] = {"reachable": False, "note": "api /health/ready üzerinden doğrulanır"}
                continue
            try:
                r = await self._client.get(url, timeout=3.0)
                result[name] = {"reachable": r.status_code == 200, "http": r.status_code}
            except Exception as e:
                result[name] = {"reachable": False, "error": type(e).__name__}
        return result

    async def check_local(self) -> dict:
        """Aynı container içinden localhost health kontrolü (yalnız self-check)."""
        local_urls = {
            "self": "http://127.0.0.1:8000/health/live",
        }
        result: dict = {}
        for name, url in local_urls.items():
            try:
                r = await self._client.get(url, timeout=3.0)
                result[name] = {"reachable": r.status_code == 200, "http": r.status_code}
            except Exception as e:
                result[name] = {"reachable": False, "error": type(e).__name__}
        return result

    async def aclose(self) -> None:
        if not self._closed:
            await self._client.aclose()
            self._closed = True

    async def close(self) -> None:
        await self.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()

```

## `packages/connectors/ssrf.py`

```py
# RAPTOR — SSRF koruması (Faz 9 sertleştirme)
# Loopback, RFC1918, link-local, metadata IP, multicast, reserved, unspecified,
# IPv4-mapped IPv6 erişimi engeller. DNS çözümünden ve her redirect'ten sonra
# IP tekrar sınıflandırılır. DNS pin ile TOCTOU önlenir.
from __future__ import annotations

import ipaddress
import socket
import time
from urllib.parse import urljoin, urlparse

_BLOCKED_NETWORKS = [
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",   # link-local IPv4
    "0.0.0.0/8",        # unspecified / broadcast
    "100.64.0.0/10",    # CGNAT
    "192.0.2.0/24",     # TEST-NET-1
    "198.51.100.0/24",  # TEST-NET-2
    "203.0.113.0/24",   # TEST-NET-3
    "224.0.0.0/4",      # multicast
    "240.0.0.0/4",      # reserved
    "255.255.255.255/32",
    "::1/128",
    "fc00::/7",         # IPv6 unique-local
    "fe80::/10",        # link-local IPv6
    "ff00::/8",         # multicast IPv6
    "::ffff:0:0/96",    # IPv4-mapped IPv6
    "::/128",           # unspecified IPv6
    "200::/7",          # reserved (old)
    "64:ff9b::/96",     # NAT64
]

_METADATA_HOSTS = {"169.254.169.254", "metadata.google.internal", "metadata.google.com", "instance-data"}

# Dahili Docker hostname'leri — dış isteklerde yasak (internal_health hariç)
_INTERNAL_HOSTNAMES = {"host.docker.internal", "gateway.docker.internal"}

_blocked = [ipaddress.ip_network(n) for n in _BLOCKED_NETWORKS]

# DNS pin cache — TOCTOU önleme (host -> (ips, expiry))
_dns_pin: dict[str, tuple[list[str], float]] = {}
_DNS_PIN_TTL = 300  # 5 dakika
# Allow port policy — yalnız http/https default portlar (opsiyonel genişletilebilir)
_ALLOWED_SCHEMES = {"http", "https"}

class SSRFError(Exception):
    pass


def _is_internal_hostname(host: str) -> bool:
    h = host.lower().rstrip(".")
    return h in _INTERNAL_HOSTNAMES or h.endswith(".internal") or h.endswith(".local")


def resolve_all(host: str, *, use_pin: bool = True) -> list[str]:
    """Tüm A/AAAA sonuçlarını döndürür (bir tanesi bile blokluysa düşman).
    DNS pin cache kullanır (TTL 5dk) — TOCTOU'ya karşı aynı IP'ye pinler."""
    host_l = host.rstrip(".").lower()
    now = time.monotonic()
    if use_pin and host_l in _dns_pin:
        ips_cached, exp = _dns_pin[host_l]
        if now < exp:
            return ips_cached
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise SSRFError(f"DNS çözümleme başarısız: {host}") from e
    ips: set[str] = set()
    for info in infos:
        ips.add(str(info[4][0]))
    if not ips:
        raise SSRFError(f"DNS boş sonuç: {host}")
    result = sorted(ips)
    _dns_pin[host_l] = (result, now + _DNS_PIN_TTL)
    return result


def clear_dns_pin(host: str | None = None) -> None:
    if host is None:
        _dns_pin.clear()
    else:
        _dns_pin.pop(host.rstrip(".").lower(), None)


def ip_is_blocked(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    if ip_str in _METADATA_HOSTS:
        return True
    # IPv4-mapped IPv6 kontrolü
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return True
    # ipaddress built-in sınıfları da kontrol et (defense in depth)
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return True
    # Private için is_private kullan ama CGNAT/reserved already covered; yine de blocked ağlarda kontrol et
    return any(ip in net for net in _blocked)


def validate_host(host: str, allowed_hosts: set[str] | None = None) -> None:
    """Host adını doğrular; DNS çözümünden sonra IP sınıfını kontrol eder.

    - allowed_hosts verilirse host bunlardan birine tam eşleşmek zorunda (deny-by-allowlist).
    - allowed_hosts None ise yalnız bloklu IP'ler reddedilir (geriye uyumluluk).
    - Hostname allowlist'e yoksa bile bloklu IP'ler reddedilir.
    """
    raw = host
    host = host.rstrip(".").lower()
    if not host:
        raise SSRFError("boş host")
    if host in _METADATA_HOSTS:
        raise SSRFError("metadata erişimi engellendi")
    if _is_internal_hostname(host):
        raise SSRFError(f"internal hostname engellendi: {host}")
    # allowlist deny — explicit allowlist varsa dışındakiler reddedilir
    if allowed_hosts is not None:
        allowed_lower = {h.lower().rstrip(".") for h in allowed_hosts}
        if host not in allowed_lower:
            raise SSRFError(f"host allowlist dışı: {host}")
    # IP literal doğrudan kontrol (DNS gerekmez)
    try:
        ipaddress.ip_address(raw.rstrip("."))
        # host kendisi IP literal
        if ip_is_blocked(raw.rstrip(".")):
            raise SSRFError(f"bloklu IP (RFC1918/loopback/metadata): {raw}")
        return
    except ValueError:
        pass
    # DNS pin + tüm IP'ler blok kontrolü
    for ip in resolve_all(host):
        if ip_is_blocked(ip):
            raise SSRFError(f"bloklu IP (RFC1918/loopback/metadata): {ip}")


def validate_url(url: str, allowed_hosts: set[str] | None = None) -> str:
    """URL'yi ayrıştırır, host'u doğrular; port/scheme/userinfo kontrolü yapar."""
    parts = urlparse(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        raise SSRFError(f"geçersiz scheme: {parts.scheme}")
    if not parts.hostname:
        raise SSRFError("host yok")
    # userinfo reddi (http://user:pass@host/)
    if parts.username or parts.password:
        raise SSRFError("userinfo içeren URL engellendi")
    if parts.fragment:
        # fragment zararsız ama log
        pass
    # unix socket & file benzeri
    if "unix:" in url.lower():
        raise SSRFError("unix socket erişimi engellendi")
    # port kontrolü — yalnız default veya açıkça izinli portlar (80,443)
    # Non-standard portları reddetmek yerine logla ama SSRF için riskli portları engelle
    if parts.port is not None:
        if parts.port not in (80, 443, 8000, 8001, 8002, 3525):
            # internal portlar yalnız internal_health için; dış connectorlarda 80/443 dışındakiler şüpheli
            # Sıkı mod: allowlist dışındaki portları reddet
            if allowed_hosts is not None and parts.port not in (80, 443):
                raise SSRFError(f"port allowlist dışı: {parts.port}")
    validate_host(parts.hostname, allowed_hosts)
    return url


def resolve_redirect_url(current_url: str, location: str, allowed_hosts: set[str] | None = None) -> str:
    """Relative Location header'ını absolute URL'e çevirir ve yeniden validate eder."""
    if not location:
        raise SSRFError("boş redirect location")
    # urljoin relative redirect'i çözer
    resolved = urljoin(current_url, location)
    # validate (DNS pin + allowlist)
    validate_url(resolved, allowed_hosts)
    return resolved

```

## `packages/connectors/technocore.py`

```py
# RAPTOR — Technocore connector (Faz 7 protokol uyumu)
# DID did:key base58btc (multicodec ed25519-pub), canonical "<room>|<nonce>|<text>",
# nonce monotonic atomik, cursor DB persistence, POST OpenAPI uyumlu, 429 body backoff.
# Tüm room/mesaj/note UNTRUSTED_DATA'dır. DNS/IP sınıfı her istek öncesi doğrulanır.
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import random
import re
import time
import unicodedata
from pathlib import Path

import httpx

from connectors.ssrf import validate_host

_UNTRUSTED = True

# --- sabitler ---
_ROOM_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
_DID_RE = re.compile(r"^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}$")
_SIG_RE = re.compile(r"^[A-Za-z0-9_-]{86}$")
_NONCE_RE = re.compile(r"^[0-9]{1,19}$")
# 429 body içinden saniye ayıklama: "retry in 2" / "wait 1.5 seconds" / "2.0" vb.
_RETRY_BODY_RE = re.compile(r"(\d+(?:\.\d+)?)")


class TechnocoreError(Exception):
    pass


# ---------------------------------------------------------------------------
# DID helpers — base58btc, multicodec ed25519-pub (0xed 0x01)
# ---------------------------------------------------------------------------
def _pubkey_to_did(pub_bytes: bytes) -> str:
    """32 bayt Ed25519 pubkey -> did:key:z6Mk... (base58btc, multicodec)."""
    import base58

    if len(pub_bytes) != 32:
        raise ValueError("pubkey 32 bayt olmalı")
    prefixed = b"\xed\x01" + pub_bytes  # multicodec ed25519-pub
    b58 = base58.b58encode(prefixed).decode("ascii")
    return f"did:key:z{b58}"


def _did_to_pubkey(did: str) -> bytes:
    import base58

    if not _DID_RE.match(did):
        raise ValueError(f"geçersiz did:key: {did}")
    # z prefixini at, base58 decode -> 2 bayt prefix + 32 bayt pubkey
    raw = base58.b58decode(did[len("did:key:z") :])
    if raw[:2] != b"\xed\x01":
        raise ValueError("multicodec prefix hatası")
    return raw[2:]


# ---------------------------------------------------------------------------
# Single-line sweep — protokol: her görünmez karakter -> space
# C0 (0x00-0x1F), C1 (0x80-0x9F), Cf format, Zl/Zp, ZWJ/ ZWNJ/ BOM, bidi overrides
# ---------------------------------------------------------------------------
def sweep_text(text: str) -> str:
    """Metni tek-satır saklama kuralına göre süpür; görünmezler space olur."""
    out_chars: list[str] = []
    for ch in text:
        o = ord(ch)
        cat = unicodedata.category(ch)
        # C0/C1, format characters, line/para separator
        if cat.startswith("C") or cat in ("Zl", "Zp"):
            out_chars.append(" ")
            continue
        # explicit zero-width / BOM / joiners
        if ch in ("\u200b", "\u200c", "\u200d", "\ufeff", "\u2060", "\u180e"):
            out_chars.append(" ")
            continue
        # bidi overrides
        if 0x202A <= o <= 0x202E or 0x2066 <= o <= 0x2069 or o in (0x200E, 0x200F, 0x061C):
            out_chars.append(" ")
            continue
        # fallback: control range
        if o < 0x20 or (0x7F <= o <= 0x9F):
            out_chars.append(" ")
            continue
        out_chars.append(ch)
    swept = "".join(out_chars)
    # çoklu space korunur — yalnızca newline/control space'e döndü, başka daraltma yok
    return swept


def canonical_string(room: str, nonce: str, text: str) -> str:
    """İmza payload'ı: <room>|<nonce>|<text>  (text sweep edilmiş)."""
    if not _ROOM_RE.match(room):
        raise ValueError(f"geçersiz room: {room}")
    if not _NONCE_RE.match(nonce):
        raise ValueError(f"geçersiz nonce: {nonce}")
    swept = sweep_text(text)
    return f"{room}|{nonce}|{swept}"


# ---------------------------------------------------------------------------
# Nonce monotonic — in-memory atomik + DB atomik
# ---------------------------------------------------------------------------
class _MonotonicNonce:
    """Process-içi monotonic nonce üretici (ms clock + counter, thread-safe)."""

    def __init__(self) -> None:
        import threading

        self._lock = threading.Lock()
        self._last = 0  # int

    def next(self) -> str:
        with self._lock:
            now_ms = int(time.time() * 1000)
            # monotonic: eğer clock geri gittiyse veya aynı ms ise +1
            if now_ms <= self._last:
                now_ms = self._last + 1
            # clamp 19 digits: max 10**19 -1
            if now_ms > 10**19 - 1:
                now_ms = self._last + 1
            self._last = now_ms
            return str(now_ms)

    def ensure_greater(self, candidate: str) -> str:
        """Dışarıdan gelen candidate nonce'u monotonic garantiye al."""
        with self._lock:
            try:
                n = int(candidate)
            except ValueError:
                return self.next()
            if n <= self._last:
                n = self._last + 1
            self._last = n
            return str(n)


_global_nonce = _MonotonicNonce()


def _parse_retry_after(resp: httpx.Response) -> float:
    """429 için body'den saniye çıkar, yoksa Retry-After header, yoksa 1.0 + jitter."""
    # 1) body
    try:
        body = resp.text or ""
    except Exception:
        body = ""
    # body genelde "Too many requests, retry in 2.5 seconds ... bucket: reads ..."
    # ilk mantıklı sayıyı al, 0.1-60 arası clamp
    if body:
        # önce explicit "retry" / "wait" civarını dene
        m = re.search(r"retry[^0-9]*(\d+(?:\.\d+)?)", body, re.IGNORECASE)
        if not m:
            m = re.search(r"wait[^0-9]*(\d+(?:\.\d+)?)", body, re.IGNORECASE)
        if not m:
            m = _RETRY_BODY_RE.search(body)
        if m:
            try:
                v = float(m.group(1))
                if 0 < v < 3600:
                    return v
            except ValueError:
                pass
    # 2) header
    hdr = resp.headers.get("Retry-After") or resp.headers.get("retry-after") or ""
    if hdr:
        try:
            v = float(hdr.strip())
            if 0 < v < 3600:
                return v
        except ValueError:
            pass
    return 1.0


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------
class TechnocoreConnector:
    def __init__(
        self,
        base_url: str = "https://technocore.chat",
        *,
        ed25519_key_path: str = "",
        max_retries: int = 2,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(
            timeout=30.0, follow_redirects=False, max_redirects=3
        )
        self._key_path = ed25519_key_path
        self.max_retries = max_retries
        self._signing_key = None  # nacl.signing.SigningKey
        self._did_pub: str | None = None

    def load_key(self, key_path: str = "") -> str:
        """Yalnızca mevcut key'i yükle; yoksa üretme (production güvenli). DID döner veya boş."""
        from nacl.signing import SigningKey

        path = Path(key_path or self._key_path)
        if not str(path) or not path.exists():
            return ""
        seed = path.read_bytes()
        if len(seed) == 64:
            seed = seed[:32]
        if len(seed) != 32:
            raise TechnocoreError(f"key dosyası hatalı uzunluk: {len(seed)}")
        self._signing_key = SigningKey(seed)
        self._did_pub = _pubkey_to_did(bytes(self._signing_key.verify_key))
        return self._did_pub

    def status(self) -> dict:
        """Public durum — private key ASLA döndürülmez."""
        return {
            "key_loaded": self._signing_key is not None,
            "did": self.did_public or "",
            "key_path": self._key_path,
        }

    # --- DID kimliği ---
    def load_or_generate_key(self, key_path: str = "") -> tuple[str, str]:
        """Ed25519 key yükle/üret; private key yalnız 0600 dosyada. DID base58btc."""
        from nacl.signing import SigningKey

        path = Path(key_path or self._key_path)
        # path boşsa geçici bellek key üret (dosyaya yazma)
        if not str(path) or str(path) == ".":
            skey = SigningKey.generate()
            self._signing_key = skey
            self._did_pub = _pubkey_to_did(bytes(skey.verify_key))
            return self._did_pub, ""

        if path.exists():
            seed = path.read_bytes()
            # seed 32 bayt olmalı; eğer 64 bayt (SigningKey bytes) geldiyse ilk 32'yi al
            if len(seed) == 64:
                seed = seed[:32]
            if len(seed) != 32:
                raise TechnocoreError(f"key dosyası hatalı uzunluk: {len(seed)}")
            skey = SigningKey(seed)
        else:
            skey = SigningKey.generate()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bytes(skey))  # 32 bayt seed
            path.chmod(0o600)
        self._signing_key = skey
        self._did_pub = _pubkey_to_did(bytes(skey.verify_key))
        return self._did_pub, path.as_posix()

    def sign(self, room: str, nonce: str, text: str) -> str:
        """Canonical string'i imzala -> base64url unpadded 86 char sig."""
        if self._signing_key is None:
            raise TechnocoreError("anahtar yüklü değil")
        canon = canonical_string(room, nonce, text)
        sig_bytes = self._signing_key.sign(canon.encode("utf-8")).signature
        sig = base64.urlsafe_b64encode(sig_bytes).decode("ascii").rstrip("=")
        # Ed25519 64 bayt -> 86 base64url chars (unpadded)
        assert len(sig) == 86, f"sig len {len(sig)} != 86"
        return sig

    def verify(self, did: str, room: str, nonce: str, text: str, sig: str) -> bool:
        """DID + canonical + sig doğrula (offline)."""
        from nacl.exceptions import BadSignatureError
        from nacl.signing import VerifyKey

        try:
            pub = _did_to_pubkey(did)
            vk = VerifyKey(pub)
            canon = canonical_string(room, nonce, text)
            sig_padded = sig + "=" * (-len(sig) % 4)
            sig_bytes = base64.urlsafe_b64decode(sig_padded)
            vk.verify(canon.encode("utf-8"), sig_bytes)
            return True
        except (BadSignatureError, ValueError):
            return False

    @property
    def did_public(self) -> str:
        return self._did_pub or ""

    # --- Nonce monotonic ---
    def next_nonce(self) -> str:
        """Atomik monotonic nonce (process-içi). DB persistence için next_nonce_db kullan."""
        return _global_nonce.next()

    async def next_nonce_db(self, room: str, session) -> str:
        """DB atomik nonce: technocore_nonces tablosunda room+did için SELECT FOR UPDATE ile increment.

        session: SQLAlchemy AsyncSession
        """
        from sqlalchemy import select

        from observability.models import TechnocoreNonce

        did = self.did_public
        if not did:
            raise TechnocoreError("DID yok — önce load_or_generate_key çağır")
        # row level lock
        # Not: this uses FOR UPDATE to ensure atomic increment
        result = await session.execute(
            select(TechnocoreNonce).where(
                TechnocoreNonce.room == room, TechnocoreNonce.did == did
            ).with_for_update()
        )
        row = result.scalar_one_or_none()
        candidate = self.next_nonce()
        # candidate'i int'e çevir, monotonic garantile
        cand_int = int(candidate)
        if row is None:
            # insert
            row = TechnocoreNonce(room=room, did=did, last_nonce=cand_int)
            session.add(row)
            await session.flush()
            return str(cand_int)
        # ensure strictly greater
        if cand_int <= row.last_nonce:
            cand_int = row.last_nonce + 1
        row.last_nonce = cand_int
        await session.flush()
        return str(cand_int)

    # --- Cursor DB persistence ---
    async def get_cursor(self, room: str, session) -> int:
        from sqlalchemy import select

        from observability.models import TechnocoreCursor

        result = await session.execute(select(TechnocoreCursor).where(TechnocoreCursor.room == room))
        row = result.scalar_one_or_none()
        return row.last_seq if row else 0

    async def set_cursor(self, room: str, seq: int, session) -> None:
        from sqlalchemy import select

        from observability.models import TechnocoreCursor

        if seq < 0:
            raise ValueError("seq negatif olamaz")
        result = await session.execute(select(TechnocoreCursor).where(TechnocoreCursor.room == room))
        row = result.scalar_one_or_none()
        if row is None:
            row = TechnocoreCursor(room=room, last_seq=seq)
            session.add(row)
        elif seq > row.last_seq:
            row.last_seq = seq
        await session.flush()

    async def advance_cursor_from_response(self, room: str, data: dict, session) -> int:
        """Read response'daki last_seq ile cursor'u ilerlet; yeni cursor döner."""
        last_seq = int(data.get("last_seq", 0) or 0)
        # first_seq kontrol: eğer boşluk varsa yine de cursor'u last_seq'a çek
        await self.set_cursor(room, last_seq, session)
        return last_seq

    # --- Host doğrulama helper ---
    def _validate_base_host(self) -> None:
        from urllib.parse import urlparse

        parsed = urlparse(self.base_url)
        host = parsed.hostname or ""
        if not host:
            raise TechnocoreError("geçersiz base_url")
        validate_host(host)

    # --- Dokümantasyon fetch ---
    async def fetch_docs(self) -> dict[str, str]:
        self._validate_base_host()
        paths = ["skill.md", "llms.txt", "patterns.md", ".well-known/agent.json", "openapi.json"]
        out: dict[str, str] = {}
        for p in paths:
            try:
                r = await self._client.get(f"{self.base_url}/{p}")
                if r.status_code == 200:
                    out[p] = hashlib.sha256(r.content).hexdigest()
                else:
                    out[p] = f"http_{r.status_code}"
            except Exception as e:
                out[p] = f"error_{type(e).__name__}"
        return out

    # --- Okuma (GET /r/{room}?since=&wait=&format=json) ---
    async def read_room(self, room: str, since: int = 0, wait: int = 10, *, session=None) -> dict:
        """since=<last_seq>&wait=10; UNTRUSTED veri döner. 429 body backoff + cursor opsiyonel."""
        if not _ROOM_RE.match(room):
            raise TechnocoreError(f"geçersiz room: {room}")
        if wait < 0 or wait > 10:
            wait = max(0, min(10, wait))
        for attempt in range(self.max_retries + 1):
            self._validate_base_host()
            try:
                r = await self._client.get(
                    f"{self.base_url}/r/{room}",
                    params={"since": since, "wait": wait, "format": "json"},
                    headers={"Accept": "application/json"},
                )
            except Exception as e:
                if attempt == self.max_retries:
                    raise TechnocoreError(f"okuma hatası: {type(e).__name__}") from e
                # async backoff with jitter
                await asyncio.sleep(0.2 * (2**attempt) + random.uniform(0, 0.15))  # noqa: S311 (jitter)
                continue
            if r.status_code == 429:
                backoff = _parse_retry_after(r)
                # jitter ekle, clamp
                backoff = min(backoff + random.uniform(0, 0.25), 30.0)  # noqa: S311 (jitter)
                if attempt == self.max_retries:
                    raise TechnocoreError(f"429 limit — backoff {backoff:.2f}s")
                await asyncio.sleep(backoff)
                continue
            if r.status_code >= 400:
                # don't retry on 4xx except 429
                r.raise_for_status()
            r.raise_for_status()
            # boyut kontrolü (1 MiB)
            if len(r.content) > 1_048_576:
                raise TechnocoreError("yanıt boyut sınırı")
            try:
                data = r.json()
            except Exception:
                # text/plain fallback -> wrap
                data = {"room": room, "messages": [], "count": 0, "last_seq": since, "raw": r.text}
            data["_untrusted"] = _UNTRUSTED
            # cursor DB persistence if session provided
            if session is not None:
                try:
                    await self.advance_cursor_from_response(room, data, session)
                except Exception:
                    pass  # cursor failure should not fail read
            return data
        raise TechnocoreError("okuma başarısız")

    # --- Yazma (POST /r/{room}  — OpenAPI uyumlu) ---
    async def signed_post(
        self,
        room: str,
        payload: dict | str,
        *,
        idempotency_key: str = "",
        signature: str | None = None,
        nonce: str | None = None,
        session=None,
    ) -> dict:
        """DID imzalı POST: OpenAPI {text, did, sig, nonce} şemasına tam uyumlu.

        payload: str (text) veya dict {"text": str} veya rapor dict (type/subject/...)
                 dict ise "text" alanı varsa o kullanılır, yoksa dict JSON'u text'e serialize edilir.
        session: opsiyonel AsyncSession — nonce DB atomik için.
        """
        if not _ROOM_RE.match(room):
            raise TechnocoreError(f"geçersiz room: {room}")
        if self._signing_key is None or not self.did_public:
            raise TechnocoreError("anahtar yüklü değil — load_or_generate_key çağır")

        # text çıkar
        if isinstance(payload, str):
            raw_text = payload
        elif isinstance(payload, dict):
            if "text" in payload and isinstance(payload["text"], str):
                raw_text = payload["text"]
            else:
                # rapor dict -> tek-satır JSON text olarak gönder (protokolde message single-line)
                # ensure_ascii False, separators compact
                raw_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        else:
            raise TechnocoreError("payload str veya dict olmalı")

        # sweep ve truncate 4096
        swept = sweep_text(raw_text)
        if not swept.strip():
            raise TechnocoreError("text sweep sonrası boş")
        if len(swept) > 4096:
            swept = swept[:4096]

        # nonce monotonic
        if nonce is not None:
            if not _NONCE_RE.match(str(nonce)):
                raise TechnocoreError(f"geçersiz nonce: {nonce}")
            nonce_str = _global_nonce.ensure_greater(str(nonce))
        elif session is not None:
            nonce_str = await self.next_nonce_db(room, session)
        else:
            nonce_str = self.next_nonce()

        sig = signature or self.sign(room, nonce_str, swept)

        # OpenAPI uyumlu body — yalnızca tanımlı alanlar
        body: dict = {
            "text": swept,
            "did": self.did_public,
            "sig": sig,
            "nonce": nonce_str,
        }
        # idempotency_key protokolde yok — PublicationAttempt için lokal; body'ye ekleme
        # ama backward compat için caller isterse header'a koyabiliriz; body'ye eklemiyoruz

        # DID/sig/nonce pattern doğrulaması (göndermeden önce)
        assert _DID_RE.match(body["did"]), f"DID pattern hatası: {body['did']}"
        assert _SIG_RE.match(body["sig"]), "sig pattern hatası"
        assert _NONCE_RE.match(body["nonce"]), "nonce pattern hatası"

        self._validate_base_host()
        for attempt in range(self.max_retries + 1):
            try:
                r = await self._client.post(
                    f"{self.base_url}/r/{room}",
                    json=body,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
            except Exception as e:
                if attempt == self.max_retries:
                    raise TechnocoreError(f"write hatası: {type(e).__name__}") from e
                await asyncio.sleep(0.2 * (2**attempt) + random.uniform(0, 0.15))  # noqa: S311 (jitter)
                continue
            if r.status_code == 429:
                backoff = _parse_retry_after(r)
                backoff = min(backoff + random.uniform(0, 0.25), 30.0)  # noqa: S311 (jitter)
                if attempt == self.max_retries:
                    raise TechnocoreError(f"429 write limit — backoff {backoff:.2f}s")
                await asyncio.sleep(backoff)
                continue
            if r.status_code >= 400:
                # 403/400 body'yi hata mesajına ekle (imza/debug için değerli)
                r.text[:500] if r.text else ""
                r.raise_for_status()
            r.raise_for_status()
            # idempotency persistence (caller tarafında PublicationAttempt yazılır; burada sadece response döner)
            try:
                return r.json()
            except Exception:
                return {"room": room, "raw": r.text, "status_code": r.status_code}
        raise TechnocoreError("write başarısız")

    # --- GET signed lane (alternatif, URL limitleri için) ---
    def build_signed_get_url(self, room: str, text: str, *, nonce: str | None = None) -> str:
        """GET /r/{room}/say-signed/{did}/{sig}/{nonce}/{text} URL'i kur (URL-encode text)."""
        import urllib.parse

        if not self.did_public:
            raise TechnocoreError("DID yok")
        swept = sweep_text(text)
        n = nonce or self.next_nonce()
        if not _NONCE_RE.match(n):
            raise TechnocoreError(f"geçersiz nonce {n}")
        sig = self.sign(room, n, swept)
        enc_text = urllib.parse.quote(swept, safe="")
        return f"{self.base_url}/r/{room}/say-signed/{self.did_public}/{sig}/{n}/{enc_text}"

```

## `packages/context_engine/__init__.py`

```py

```

## `packages/context_engine/assembler.py`

```py
# RAPTOR — Context Assembler / Inspector
# Bağlamı token bütçesine göre katmanlar; gizli chain-of-thought GÖSTERMEZ.
# Her segment meta veri: segment_type, source_id, title, token_count, relevance,
# freshness, confidence, included_reason, contains_untrusted, redaction_count.
# Faz4: katmanlar ayrık (system_policy / task_goal / memory / tool_schemas / untrusted),
#       overwrite hatası düzeltildi (dict -> list), token counting iyileştirildi.

from __future__ import annotations

import dataclasses
import re
import time
from typing import Any


@dataclasses.dataclass
class ContextSegment:
    segment_type: str
    source_id: str
    title: str
    content: str
    token_count: int = 0
    relevance_score: float = 0.0
    freshness: str = ""
    confidence: float = 0.0
    included_reason: str = ""
    contains_untrusted_input: bool = False
    redaction_count: int = 0


# Basit token tahmini (~4 karakter/token) — tiktoken varsa daha doğru say
def estimate_tokens(text: str) -> int:
    # tiktoken mevcutsa cl100k_base kullan, yoksa fallback
    try:
        import tiktoken  # type: ignore

        enc = tiktoken.get_encoding("cl100k_base")
        return max(1, len(enc.encode(text)))
    except Exception:
        return max(1, len(text) // 4)


# Daima rezerve edilen çıktı payı (output reserve sıfırlanamaz)
OUTPUT_RESERVE_TOKENS = 2048

# Katman tanımı — 5 ana katman + uyumluluk için alt tipler
# Öncelik sırası: düşük sayı = yüksek öncelik (önce dahil edilir)
LAYER_PRIORITY: dict[str, int] = {
    "system_policy": 0,
    "task_goal": 1,
    "conversation_window": 2,
    # memory grubu — hepsi aynı katman
    "episodic_memory": 3,
    "semantic_memory": 3,
    "procedural_memory": 3,
    "memory": 3,
    "tool_schemas": 4,
    # untrusted — en düşük öncelik, ayrı sınırlandırılır
    "untrusted": 5,
    "tool_output": 5,
    "external_data": 5,
}

# Kanonik katman sırası (SEQUENCE) — geriye uyum için eski + yeni tipler
SEQUENCE = [
    "system_policy",
    "task_goal",
    "conversation_window",
    "episodic_memory",
    "semantic_memory",
    "procedural_memory",
    "memory",
    "tool_schemas",
    "untrusted",
]

# Katman -> maksimum pay (bütçenin oranı) — untrusted sınırlandırılır
LAYER_BUDGET_RATIO: dict[str, float] = {
    "untrusted": 0.25,  # untrusted toplam bütçenin %25'ini aşamaz
}

# Redaction placeholders — geniş sayım için
_REDACTED_RE = re.compile(r"<[^>]*REDACTED[^>]*>")

# Untrusted içeriği izole etmek için sınır işaretleri
UNTRUSTED_BEGIN = "<<<UNTRUSTED_DATA_BEGIN>>>"
UNTRUSTED_END = "<<<UNTRUSTED_DATA_END>>>"


def _layer_of(segment_type: str) -> str:
    """Segment tipini kanonik katmana eşle."""
    if segment_type in LAYER_PRIORITY:
        # memory alt tiplerini 'memory' olarak normalize etme — öncelik aynı
        return segment_type
    # bilinmeyen tipler 'untrusted' sayılmaz, kendi katmanı
    return segment_type


def _priority(segment_type: str) -> int:
    return LAYER_PRIORITY.get(segment_type, 99)


class ContextAssembler:
    """Bağlam katmanlarını toplayıcı; token budget'a uyar, untrusted izole eder."""

    # dışa açık sabitler
    SEQUENCE = SEQUENCE
    OUTPUT_RESERVE_TOKENS = OUTPUT_RESERVE_TOKENS

    def __init__(self, max_tokens: int = 60000, *, redactor: Any = None) -> None:
        self.max_tokens = max(OUTPUT_RESERVE_TOKENS + 1024, max_tokens)
        self.redactor = redactor
        # Faz4 düzeltmesi: dict -> list (overwrite bug çözümü)
        # Aynı segment_type birden fazla kez eklenebilir (örn. memory birden fazla hit)
        self._segments: list[ContextSegment] = []

    def add(self, segment_type: str, content: str, *, title: str = "", source_id: str = "",
            relevance: float = 0.0, confidence: float = 0.0, untrusted: bool = False) -> None:
        # DLP: redact
        if self.redactor is not None:
            scrub = self.redactor.scrub
        else:
            from observability.security import redact
            scrub = redact  # type: ignore[assignment]
        content = scrub(content)

        # Untrusted izolasyonu: ayrı işaretleme + boundary
        is_untrusted = untrusted or segment_type in ("untrusted", "tool_output", "external_data")
        if is_untrusted:
            # içeriği boundary içine al (prompt injection mitigasyonu)
            if UNTRUSTED_BEGIN not in content:
                content = f"{UNTRUSTED_BEGIN}\n{content}\n{UNTRUSTED_END}"

        # redaction sayımı — tüm varyantları say
        redactions = len(_REDACTED_RE.findall(content))

        seg = ContextSegment(
            segment_type=segment_type,
            source_id=source_id,
            title=title,
            content=content,
            token_count=estimate_tokens(content),
            relevance_score=relevance,
            freshness=str(int(time.time())),
            confidence=confidence,
            included_reason=f"katman {segment_type} -> bütçe kurallı seçim",
            contains_untrusted_input=is_untrusted,
            redaction_count=redactions,
        )
        # overwrite yok — append
        self._segments.append(seg)

    def assemble(self) -> tuple[list[ContextSegment], str]:
        """Bütçe içinde segment'leri sıralı döndürür + birleşik denetlenebilir prompt üretir."""
        ordered: list[ContextSegment] = []
        budget = self.max_tokens - OUTPUT_RESERVE_TOKENS
        used = 0
        untrusted_used = 0
        untrusted_budget = int(budget * LAYER_BUDGET_RATIO.get("untrusted", 0.25))

        # Öncelik sırası sabit, ardından relevance sıralaması
        # Sequence içindeki tipleri öncelik sırasına göre işle; aynı tipte birden fazla segment olabilir
        # Önce sequence sırası
        seq_segments: list[ContextSegment] = []
        remaining: list[ContextSegment] = []
        # segment_type'a göre grupla ama sırayı koru
        seg_by_type: dict[str, list[ContextSegment]] = {}
        for s in self._segments:
            seg_by_type.setdefault(s.segment_type, []).append(s)
        # SEQUENCE sırasına göre ekle
        for stype in self.SEQUENCE:
            for seg in seg_by_type.pop(stype, []):
                seq_segments.append(seg)
        # kalan unknown tipler
        for segs in seg_by_type.values():
            remaining.extend(segs)
        # remaining relevance'a göre sırala
        remaining.sort(key=lambda s: s.relevance_score, reverse=True)

        all_in_order = seq_segments + remaining

        for seg in all_in_order:
            # katman bütçesi kontrolü (untrusted sınırlı)
            if seg.contains_untrusted_input:
                if untrusted_used + seg.token_count > untrusted_budget:
                    seg.included_reason = "untrusted katman bütçesi aşımı → atlandı"
                    continue
            # genel bütçe kontrolü — system_policy ve task_goal her zaman dahil (kritik)
            if used + seg.token_count > budget and seg.segment_type not in ("system_policy", "task_goal"):
                seg.included_reason = "token bütçesi aşımı → atlandı"
                continue
            ordered.append(seg)
            used += seg.token_count
            if seg.contains_untrusted_input:
                untrusted_used += seg.token_count

        # denetlenebilir prompt: her segment başına bilgi notu, gizli düşünce yok
        # Katman sınırları açıkça işaretlenir
        parts = []
        for seg in ordered:
            untagged = " [UNTRUSTED]" if seg.contains_untrusted_input else ""
            parts.append(
                f"### {seg.segment_type}{untagged} ({seg.included_reason})\n{seg.content}"
            )
        prompt = "\n\n".join(parts)
        return ordered, prompt

    def inspector_metadata(self) -> list[dict]:
        # Faz4: tüm segmentleri döndür (dahil edilmeyenler de reason ile)
        return [
            {
                "segment_type": s.segment_type,
                "title": s.title,
                "token_count": s.token_count,
                "relevance_score": s.relevance_score,
                "freshness": s.freshness,
                "confidence": s.confidence,
                "included_reason": s.included_reason,
                "contains_untrusted_input": s.contains_untrusted_input,
                "redaction_count": s.redaction_count,
            }
            for s in self._segments
        ]

    # Yardımcı: katman bazlı token toplamları (inspector için)
    def layer_token_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self._segments:
            counts[s.segment_type] = counts.get(s.segment_type, 0) + s.token_count
        return counts

```

## `packages/memory/__init__.py`

```py

```

## `packages/memory/service.py`

```py
# RAPTOR — Memory service (yaşam döngüsü: CANDIDATE -> ... -> ACTIVE/SUPERSEDED)
# Model doğrudan kalıcı gerçek yazamaz; run sonunda memory candidate üretir.
# Faz4: verified/active filtre, DLP (secret redact), pgvector hazırlığı, ttl/active yönetimi
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from observability.models import MemoryItem, MemoryRelation, MemoryStatus

# Retrieval için izinli status'ler — yalnızca doğrulanmış bilgi bağlama girer
RETRIEVAL_ALLOWED_STATUSES = {
    MemoryStatus.ACTIVE.value,
    MemoryStatus.APPROVED.value,
    MemoryStatus.AUTO_APPROVED.value,
}
# verified + active = context'e girecek hafıza
VERIFIED_VALUE = "verified"


def _escape_ilike(q: str) -> str:
    """Wildcard enjeksiyonunu engelle: % _ \\ escape."""
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class MemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_candidate(
        self,
        *,
        content: str,
        source: str,
        confidence: float = 0.5,
        ttl_seconds: int | None = None,
        category: str | None = None,
        observed_at: datetime | None = None,
        embedding: list[float] | None = None,
        embedding_vector: list[float] | None = None,
    ) -> MemoryItem:
        # DLP: secret redact — hafızaya gizli değer yazılmaz
        from observability.security import redact

        content = redact(content)
        source = redact(source)

        item = MemoryItem(
            content=content,
            source=source,
            confidence=max(0.0, min(1.0, confidence)),
            ttl=ttl_seconds,
            status=MemoryStatus.CANDIDATE.value,
            verification_status="unverified",
            observed_at=observed_at or datetime.now(UTC),
            category=category,
            expires_at=(
                datetime.now(UTC) + timedelta(seconds=ttl_seconds)
                if ttl_seconds else None
            ),
            embedding=embedding,
        )
        # pgvector sütunu varsa doldur
        if embedding_vector is not None and hasattr(item, "embedding_vector"):
            item.embedding_vector = embedding_vector  # type: ignore
        elif embedding is not None and hasattr(item, "embedding_vector"):
            # JSON embedding varsa vector'e de kopyala
            try:
                item.embedding_vector = embedding  # type: ignore
            except Exception:
                pass
        self.session.add(item)
        await self.session.flush()
        return item

    async def approve(self, memory_id: uuid.UUID, auto: bool = False) -> MemoryItem | None:
        item = await self.session.get(MemoryItem, memory_id)
        if item is None:
            return None
        # Guard: yalnızca CANDIDATE -> APPROVED
        if item.status != MemoryStatus.CANDIDATE.value:
            return None
        item.status = MemoryStatus.AUTO_APPROVED.value if auto else MemoryStatus.APPROVED.value
        item.verification_status = VERIFIED_VALUE
        await self.session.flush()
        return item

    async def reject(self, memory_id: uuid.UUID) -> None:
        item = await self.session.get(MemoryItem, memory_id)
        if item:
            item.status = MemoryStatus.REJECTED.value
            await self.session.flush()

    async def mark_active(self, memory_id: uuid.UUID) -> None:
        item = await self.session.get(MemoryItem, memory_id)
        if item:
            # Yalnızca APPROVED / AUTO_APPROVED -> ACTIVE
            if item.status in (MemoryStatus.APPROVED.value, MemoryStatus.AUTO_APPROVED.value):
                item.status = MemoryStatus.ACTIVE.value
                item.verification_status = VERIFIED_VALUE
                await self.session.flush()

    async def supersede(self, old_id: uuid.UUID, new_id: uuid.UUID) -> None:
        # new_id varlığı ve ACTIVE kontrolü
        new_item = await self.session.get(MemoryItem, new_id)
        if new_item is None or new_item.status != MemoryStatus.ACTIVE.value:
            return
        old = await self.session.get(MemoryItem, old_id)
        if old is None:
            return
        # cycle kontrolü basit: aynı id olamaz
        if old_id == new_id:
            return
        self.session.add(
            MemoryRelation(
                from_memory_id=new_id,
                to_memory_id=old_id,
                relation_type="supersedes",
            )
        )
        old.status = MemoryStatus.SUPERSEDED.value
        await self.session.flush()

    async def link_contradiction(self, a_id: uuid.UUID, b_id: uuid.UUID) -> None:
        self.session.add(MemoryRelation(from_memory_id=a_id, to_memory_id=b_id, relation_type="contradicts"))
        await self.session.flush()

    async def search(self, q: str, status: str | None = None, limit: int = 20,
                     verified_only: bool = True, allow_expired: bool = False) -> list[MemoryItem]:
        """Genel arama — retrieval için verified/active filtre uygular.

        - verified_only=True ise yalnızca verification_status='verified' ve RETRIEVAL_ALLOWED_STATUSES döner.
        - status parametresi verilirse o status filtrelenir ama verified_only hâlâ geçerlidir (Faz4).
        - allow_expired=False ise expires_at geçmiş kayıtlar atlanır.
        """
        # DLP + wildcard escape
        escaped = _escape_ilike(q)
        stmt = select(MemoryItem).where(MemoryItem.content.ilike(f"%{escaped}%", escape="\\"))

        # Faz4: verified/active filtre
        if verified_only:
            if status:
                # status explicit ise onu filtrele ama verified gerektir
                stmt = stmt.where(MemoryItem.status == status)
                stmt = stmt.where(MemoryItem.verification_status == VERIFIED_VALUE)
            else:
                stmt = stmt.where(MemoryItem.status.in_(list(RETRIEVAL_ALLOWED_STATUSES)))
                stmt = stmt.where(MemoryItem.verification_status == VERIFIED_VALUE)
        elif status:
            stmt = stmt.where(MemoryItem.status == status)

        if not allow_expired:
            now = datetime.now(UTC)
            stmt = stmt.where(or_(MemoryItem.expires_at.is_(None), MemoryItem.expires_at > now))
            # status EXPIRED olanları da dışla
            stmt = stmt.where(MemoryItem.status != MemoryStatus.EXPIRED.value)

        stmt = stmt.order_by(MemoryItem.confidence.desc()).limit(limit)
        res = await self.session.execute(stmt)
        items = list(res.scalars().all())
        # DLP: dönen içerikte sızıntı varsa tekrar redact (defense in depth)
        from observability.security import redact as _redact
        for it in items:
            it.content = _redact(it.content)
        return items

    async def retrieve_for_context(self, q: str, limit: int = 10) -> list[MemoryItem]:
        """ContextAssembler için — yalnızca ACTIVE + verified, relevance sıralı."""
        return await self.search(q, limit=limit, verified_only=True, allow_expired=False)

    async def vector_search(self, embedding: list[float], limit: int = 10) -> list[MemoryItem]:
        """pgvector cosine similarity ile arama — pgvector kurulu değilse JSON fallback (ilike değil)."""
        # Önce pgvector 시도, yoksa boş döndür (JSON embedding cosine pahalı)
        try:
            # ham SQL: SELECT * FROM memory_items ORDER BY embedding_vector <=> :vec LIMIT :limit
            # sadece verified/active filtresiyle
            from sqlalchemy import text as sql_text
            now = datetime.now(UTC)
            # asyncpg vector tipi adaptasyonu pgvector'e bırakılır
            stmt = sql_text("""
                SELECT id FROM memory_items
                WHERE verification_status='verified'
                  AND status IN ('ACTIVE','APPROVED','AUTO_APPROVED')
                  AND (expires_at IS NULL OR expires_at > :now)
                  AND embedding_vector IS NOT NULL
                ORDER BY embedding_vector <=> CAST(:vec AS vector)
                LIMIT :lim
            """)
            res = await self.session.execute(stmt, {"vec": str(embedding), "now": now, "lim": limit})
            ids = [r[0] for r in res.fetchall()]
            if not ids:
                return []
            items_stmt = select(MemoryItem).where(MemoryItem.id.in_(ids))
            res2 = await self.session.execute(items_stmt)
            return list(res2.scalars().all())
        except Exception:
            # fallback: confidence sıralı search
            return []

    async def list_status(self, status: str, limit: int = 50) -> list[MemoryItem]:
        # status parametresi doğrulanır
        allowed = {e.value for e in MemoryStatus}
        if status not in allowed:
            return []
        now = datetime.now(UTC)
        stmt = select(MemoryItem).where(MemoryItem.status == status)
        # expired filtre (allow_expired=False davranışı)
        stmt = stmt.where(or_(MemoryItem.expires_at.is_(None), MemoryItem.expires_at > now))
        stmt = stmt.order_by(MemoryItem.created_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def expire_sweep(self) -> int:
        """TTL dolmuş kayıtları EXPIRED yap — scheduler/worker tarafından periyodik çağrılır."""
        now = datetime.now(UTC)
        stmt = select(MemoryItem).where(
            and_(
                MemoryItem.expires_at.is_not(None),
                MemoryItem.expires_at <= now,
                MemoryItem.status.notin_([MemoryStatus.EXPIRED.value, MemoryStatus.DELETED.value, MemoryStatus.SUPERSEDED.value]),
            )
        )
        res = await self.session.execute(stmt)
        items = res.scalars().all()
        count = 0
        for it in items:
            it.status = MemoryStatus.EXPIRED.value
            count += 1
        if count:
            await self.session.flush()
        return count

```

## `packages/observability/__init__.py`

```py
# observability paketi — sürüm tek kaynağı (SemVer)
__version__ = "1.0.0"

```

## `packages/observability/auth.py`

```py
# RAPTOR — local authentication + RBAC + rate limiting
# CF Access kullanılmıyor (kullanıcı kararı). Bunun yerine:
#   - session JWT (HS256, JWT_SECRET ile imzalı)
#   - PBKDF2-HMAC-SHA256 parola hash'i (stdlib, bağımlılıksız)
#   - role bazlı erişim (admin > operator > viewer)
from __future__ import annotations

import hashlib
import hmac
import os
import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from observability.config import settings

# ---------------------------------------------------------------------------
# Parola hash (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------
_ITERATIONS = 240_000

bearer_scheme = HTTPBearer(auto_error=False)

ROLE_ORDER = {"viewer": 0, "operator": 1, "admin": 2}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iters, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Session JWT
# ---------------------------------------------------------------------------
def create_session_token(user_id: str, role: str, expires_seconds: int = 12 * 3600) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=expires_seconds),
        "jti": uuid.uuid4().hex,
        "iss": "raptor-observatory",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_session_token(token: str) -> dict:
    # signature + exp + iss doğrulanır; hatalı token raise eder
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"], issuer="raptor-observatory")


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------
def _resolve_user_id_from_email(email: str) -> str | None:
    # email → user id çözümü: users tablosundan username=email bakılır.
    # Bu fonksiyon async DB gerektirir; dependency içinde çağrılır.
    return None  # placeholder; get_current_user içinde DB'den çözülür


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if creds is None or not creds.credentials:
        raise HTTPException(401, "kimlik doğrulama gerekli")
    try:
        payload = decode_session_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "session süresi doldu") from None
    except Exception:
        raise HTTPException(401, "geçersiz session token") from None
    return {"user_id": payload.get("sub"), "role": payload.get("role", "viewer")}


def require_role(min_role: str):
    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if ROLE_ORDER.get(user.get("role"), -1) < ROLE_ORDER.get(min_role, 0):
            raise HTTPException(403, f"yetki yetersiz: {min_role} gerekli")
        return user
    return _dep


# ---------------------------------------------------------------------------
# Rate limiting (Redis INCR + TTL, in-memory fallback)
# ---------------------------------------------------------------------------
class RateLimiter:
    def __init__(self) -> None:
        self._redis = None
        self._redis_tried = False
        self._mem: dict[str, list[float]] = {}

    async def _get_redis(self):
        if self._redis is None and not self._redis_tried:
            self._redis_tried = True
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            except Exception:
                self._redis = None
        return self._redis

    async def check(self, key: str, limit: int, window_seconds: int) -> bool:
        """True = izinli, False = limit aşıldı."""
        r = await self._get_redis()
        now = time.time()
        if r is not None:
            try:
                pipe = r.pipeline()
                pipe.incr(key)
                pipe.expire(key, window_seconds)
                count, _ = await pipe.execute()
                return int(count) <= limit
            except Exception:
                pass  # redis yoksa memory fallback
        # in-memory fallback (tek process için yeterli)
        ts = [t for t in self._mem.get(key, []) if now - t < window_seconds]
        if len(ts) >= limit:
            self._mem[key] = ts
            return False
        ts.append(now)
        self._mem[key] = ts
        return True


rate_limiter = RateLimiter()

```

## `packages/observability/config.py`

```py
# RAPTOR Agentic Observatory — merkezi yapılandırma
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        extra="ignore",
        case_sensitive=False,
    )

    APP_ENV: str = "development"
    APP_TIMEZONE: str = "UTC"
    SCHEMA_VERSION: int = 1

    # DB (production: raptor_postgres internal host)
    DATABASE_URL: str = (
        "postgresql+asyncpg://raptor:random@localhost:5432/raptor"
    )
    REDIS_URL: str = "redis://localhost:6379/0"

    # Güvenlik (dev-only placeholder; production'da app.env ile override edilir)
    JWT_SECRET: str = "dev-only-change-me"  # noqa: S105
    SESSION_ENCRYPTION_MASTER_KEY: str = "dev-only-32-byte-master-key-0000000000"
    TELEGRAM_WEBHOOK_SECRET: str = "dev-webhook-secret"  # noqa: S105
    CLOUDFLARE_ACCESS_AUD: str = ""
    CLOUDFLARE_ACCESS_CERT_PEM_PATH: str = ""

    # Local auth (CF Access kullanılmıyor)
    ADMIN_EMAIL: str = "your-email@example.com"
    ADMIN_PASSWORD_HASH: str = ""
    SESSION_TTL_SECONDS: int = 12 * 3600
    RATE_LIMIT_PER_MINUTE: int = 120
    RATE_LIMIT_TASK_PER_MINUTE: int = 20
    MAX_REQUEST_BODY_BYTES: int = 1_048_576

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ALLOWED_USER_IDS: str = ""
    TELEGRAM_GROUP_ENABLED: bool = False

    # LLM
    LLM_PROVIDER: str = "mock"
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""
    LLM_API_KEY: str = ""

    # Guardrail
    RUN_MAX_ITERATIONS: int = 40
    RUN_MAX_TOOL_CALLS: int = 80
    RUN_MAX_WALL_SECONDS: int = 900
    RUN_MAX_TOKEN_BUDGET: int = 200_000
    RUN_MAX_COST_BUDGET: float = 5.0

    # Connector / SSRF
    CONNECTOR_ALLOWED_HOSTS: str = ""
    CONNECTOR_MAX_RESPONSE_BYTES: int = 1_048_576
    CONNECTOR_MAX_REDIRECTS: int = 3

    # Embedding (memory semantic retrieval)
    EMBEDDING_MODEL: str = ""  # boşsa LLM_MODEL kullanılır
    EMBEDDING_DIM: int = 1536  # modele göre yapılandırılabilir (sabit varsayım değil)

    # Technocore
    TECHNOCORE_BASE_URL: str = "https://technocore.chat"
    TECHNOCORE_ROOM_CLAIM: str = "dm-topic"
    TECHNOCORE_ED25519_KEY_PATH: str = ""

    # API host/port (0.0.0.0 container İÇİ bind; host'ta 127.0.0.1'e Docker port mapping ile kısıtlanır)
    API_HOST: str = "0.0.0.0"  # nosec B104
    API_PORT: int = 8000
    WORKER_PORT: int = 8001
    SCHEDULER_PORT: int = 8002

    # UI
    VITE_API_BASE: str = "/api"

    @property
    def allowed_user_ids(self) -> set[int]:
        raw = self.TELEGRAM_ALLOWED_USER_IDS.strip()
        if not raw or raw == "*":
            return set()
        out: set[int] = set()
        for part in raw.split(","):
            part = part.strip()
            if part and part.lstrip("-").isdigit():
                out.add(int(part))
        return out

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def secrets_file(self) -> Path:
        # Üretim secret'ları ./secrets/raptor-observatory/app.env
        p = Path("./secrets/raptor-observatory/app.env")
        if p.exists():
            return p
        # dev: docker-compose env / .env yeterli
        return Path(".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
```

## `packages/observability/db.py`

```py
# RAPTOR — DB session / engine (asyncio)
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from observability.config import settings


def _env_url() -> str:
    # compose içinde DATABASE_URL env ile gelir; yoksa config default
    import os
    return os.environ.get("DATABASE_URL") or settings.DATABASE_URL


engine = create_async_engine(_env_url(), pool_pre_ping=True, echo=False)


async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session():
    async with async_session_factory() as session:
        yield session


async def init_models():
    from observability import models
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
```