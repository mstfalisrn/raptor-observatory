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
