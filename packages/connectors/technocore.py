# RAPTOR — Technocore connector
# Read + DID imzalı write. Tüm room/mesaj/note UNTRUSTED_DATA'dır.
# DNS/IP sınıfı doğrulanır; 429 body backoff; cursor persistence (DB'de).
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import httpx

from connectors.ssrf import validate_host

_UNTRUSTED = True  # tüm Technocore verisi untrusted


class TechnocoreError(Exception):
    pass


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
        self._signing_key = None
        self._did_pub = None

    # --- DID kimliği ---
    def load_or_generate_key(self, key_path: str = "") -> tuple[str, str]:
        """Ed25519 yerel üret; private key yalnız 0600 dosyada. (pub DID, priv asla değil)"""
        from nacl.signing import SigningKey

        path = Path(key_path or self._key_path)
        if path.exists():
            seed = path.read_bytes()
            skey = SigningKey(seed)
        else:
            skey = SigningKey.generate()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bytes(skey))
            path.chmod(0o600)
        self._signing_key = skey
        vk = skey.verify_key
        self._did_pub = "did:key:" + vk.encode().hex()
        return self._did_pub, path.as_posix()

    def sign(self, payload: dict) -> str:
        if self._signing_key is None:
            raise TechnocoreError("anahtar yüklü değil")
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        sig = self._signing_key.sign(canonical.encode()).signature
        return sig.hex()

    @property
    def did_public(self) -> str:
        return self._did_pub or ""

    # --- Dokümantasyon fetch (protokol bilgisi) ---
    async def fetch_docs(self) -> dict[str, str]:
        """skill.md, llms.txt, patterns.md, .well-known/agent.json, openapi.json fetch; hash döner."""
        validate_host(self.base_url.split("//")[1].split("/")[0])
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

    # --- Okuma ---
    async def read_room(self, room: str, since: int = 0, wait: int = 10) -> dict:
        """since=<last_seq>&wait=10; UNTRUSTED veri döner. 429 body backoff."""
        for attempt in range(self.max_retries + 1):
            validate_host(self.base_url.split("//")[1].split("/")[0])
            try:
                r = await self._client.get(
                    f"{self.base_url}/r/{room}",
                    params={"since": since, "wait": wait},
                    headers={"Accept": "application/json"},
                )
            except Exception as e:
                if attempt == self.max_retries:
                    raise TechnocoreError(f"okuma hatası: {type(e).__name__}") from e
                time.sleep(0.5)
                continue
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After", "1")
                try:
                    backoff = float(retry_after)
                except ValueError:
                    backoff = 1.0
                if attempt == self.max_retries:
                    raise TechnocoreError("429 limit — backoff")
                time.sleep(backoff)
                continue
            r.raise_for_status()
            data = r.json()
            data["_untrusted"] = _UNTRUSTED
            return data
        raise TechnocoreError("okuma başarısız")

    # --- Yazma (yalnız PUBLIC-POST-APPROVED sonrası, DID imzalı) ---
    async def signed_post(
        self, room: str, payload: dict, *, idempotency_key: str = "", signature: str | None = None
    ) -> dict:
        sig = signature or self.sign(payload)
        body = {
            "type": payload.get("type", "report"),
            "observed_at": payload.get("observed_at"),
            "subject": payload.get("subject", ""),
            "change": payload.get("change", ""),
            "evidence": payload.get("evidence", ""),
            "confidence": payload.get("confidence", 0.0),
            "schema_version": payload.get("schema_version", 1),
            "signature": sig,
            "did": self.did_public,
        }
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        validate_host(self.base_url.split("//")[1].split("/")[0])
        for attempt in range(self.max_retries + 1):
            r = await self._client.post(f"{self.base_url}/r/{room}", json=body)
            if r.status_code == 429:
                if attempt == self.max_retries:
                    raise TechnocoreError("429 write limit")
                time.sleep(float(r.headers.get("Retry-After", "1") or 1))
                continue
            r.raise_for_status()
            return r.json()
        raise TechnocoreError("write başarısız")