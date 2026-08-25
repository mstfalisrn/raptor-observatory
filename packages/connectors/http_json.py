# RAPTOR — HTTP/JSON connector (SSRF korumalı)
from __future__ import annotations

import httpx

from connectors.ssrf import validate_url


class HttpJsonConnector:
    def __init__(self, allowed_hosts: set[str] | None = None,
                 max_bytes: int = 1_048_576, max_redirects: int = 3) -> None:
        self.allowed_hosts = allowed_hosts
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self._client = httpx.AsyncClient(
            timeout=20.0, follow_redirects=False, max_redirects=max_redirects
        )

    async def get_json(self, url: str) -> dict:
        from urllib.parse import urlparse

        validate_url(url, self.allowed_hosts)

        current = url
        redirects = 0
        while True:
            parts = urlparse(current)
            validate_url(current, self.allowed_hosts)  # her redirect sonrası
            resp = await self._client.get(current)
            if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                redirects += 1
                if redirects > self.max_redirects:
                    raise RuntimeError("çok fazla redirect")
                # hedef tekrar SSRF doğrulamasından geçirilecek (döngü başı)
                current = str(resp.headers["location"])
                continue
            resp.raise_for_status()
            if len(resp.content) > self.max_bytes:
                raise RuntimeError("yanıt boyut sınırı aşıldı")
            return resp.json()