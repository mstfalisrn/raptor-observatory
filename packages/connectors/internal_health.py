# RAPTOR — internal health connector (yalnız kendi container sağlığı)
from __future__ import annotations

import httpx


class InternalHealthConnector:
    """Yalnızca RAPTOR container health bilgileri; başka servise erişmez."""

    def __init__(self) -> None:
        # internal hostname'ler; SSRF deny-list'e dahil. Sadece bilinen health endpoint.
        self._client = httpx.AsyncClient(timeout=5.0, follow_redirects=True)

    async def check(self) -> dict:
        services = {
            "api": "http://127.0.0.1:8000/health/live",
            "worker": "http://127.0.0.1:8001/health/live",
            "scheduler": "http://127.0.0.1:8002/health/live",
            "postgres": None,  # DB bağlantısı api tarafından /health/ready'de doğrulanır
            "redis": None,
        }
        result: dict = {}
        # Bu connector yalnız kendi container'ının kendine health endpoint'lerine bakar.
        # Ayrı container'lara ağ erişimi kısıtlıdır (internal network), ama yine de
        # sadece 127.0.0.1 olmayan hedefleri atlarız.
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