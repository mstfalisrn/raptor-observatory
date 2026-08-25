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
        m = re.search(r"retry[^0-9]*(\d+(?:\.\d+)?)", body, re.I)
        if not m:
            m = re.search(r"wait[^0-9]*(\d+(?:\.\d+)?)", body, re.I)
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
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError

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
        else:
            if seq > row.last_seq:
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
                await asyncio.sleep(0.2 * (2**attempt) + random.uniform(0, 0.15))
                continue
            if r.status_code == 429:
                backoff = _parse_retry_after(r)
                # jitter ekle, clamp
                backoff = min(backoff + random.uniform(0, 0.25), 30.0)
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
        assert _SIG_RE.match(body["sig"]), f"sig pattern hatası"
        assert _NONCE_RE.match(body["nonce"]), f"nonce pattern hatası"

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
                await asyncio.sleep(0.2 * (2**attempt) + random.uniform(0, 0.15))
                continue
            if r.status_code == 429:
                backoff = _parse_retry_after(r)
                backoff = min(backoff + random.uniform(0, 0.25), 30.0)
                if attempt == self.max_retries:
                    raise TechnocoreError(f"429 write limit — backoff {backoff:.2f}s")
                await asyncio.sleep(backoff)
                continue
            if r.status_code >= 400:
                # 403/400 body'yi hata mesajına ekle (imza/debug için değerli)
                detail = r.text[:500] if r.text else ""
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
