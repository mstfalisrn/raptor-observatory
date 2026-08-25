# RAPTOR — Tool executor (yalnız kayıtlı ve şemalı araçları kullanır; keyfi shell/docker yok)
from __future__ import annotations

from typing import Any, Awaitable, Callable

from connectors.github import GithubRepoConnector
from connectors.http_json import HttpJsonConnector
from connectors.internal_health import InternalHealthConnector
from connectors.technocore import TechnocoreConnector


class ToolRegistry:
    def __init__(self) -> None:
        self._fns: dict[str, Callable[..., Awaitable[Any]]] = {}
        self._schemas: dict[str, dict] = {}

    def register(self, name: str, fn, schema: dict) -> None:
        self._fns[name] = fn
        self._schemas[name] = schema

    def has(self, name: str) -> bool:
        return name in self._fns

    def schema(self, name: str) -> dict:
        return self._schemas.get(name, {})

    async def call(self, name: str, **kw) -> Any:
        if name not in self._fns:
            raise KeyError(f"kayıtsız araç: {name}")
        return await self._fns[name](**kw)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, task: dict | None = None) -> None:
        self.registry = registry
        self.task = task or {}

    async def execute(self, tool: str, **kw) -> Any:
        return await self.registry.call(tool, **kw)


def build_default_registry(
    *,
    http_hosts: set[str] | None = None,
    technocore_key_path: str = "",
    technocore_base_url: str = "https://technocore.chat",
) -> ToolRegistry:
    reg = ToolRegistry()
    http = HttpJsonConnector(allowed_hosts=http_hosts)
    gh = GithubRepoConnector()
    health = InternalHealthConnector()
    tc = TechnocoreConnector(technocore_base_url, ed25519_key_path=technocore_key_path)

    reg.register(
        "http_json_read",
        lambda url: http.get_json(url),
        {"name": "http_json_read", "description": "İzinli HTTP/JSON kaynak okur (SSRF korumalı)",
         "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    )
    reg.register(
        "github_repo_read",
        lambda repo: gh.repo_activity(repo),
        {"name": "github_repo_read", "description": "Public GitHub repo etkinliğini okur",
         "parameters": {"type": "object", "properties": {"repo": {"type": "string"}}, "required": ["repo"]}},
    )
    reg.register(
        "internal_health",
        lambda: health.check(),
        {"name": "internal_health", "description": "RAPTOR container sağlık bilgisi",
         "parameters": {"type": "object", "properties": {}}},
    )
    reg.register(
        "technocore_read",
        lambda room="d-raptor-observatory", since=0: tc.read_room(room, since),
        {"name": "technocore_read", "description": "Technocore room/event okur (UNTRUSTED)",
         "parameters": {"type": "object", "properties": {"room": {"type": "string"}, "since": {"type": "integer"}}}},
    )
    reg.register(
        "technocore_signed_write",
        lambda room, payload, idempotency_key: tc.signed_post(room, payload, idempotency_key=idempotency_key),
        {"name": "technocore_signed_write", "description": "DID imzalı Technocore yayını (yalnız onay)",
         "parameters": {"type": "object", "properties": {
             "room": {"type": "string"}, "payload": {"type": "object"}, "idempotency_key": {"type": "string"}},
             "required": ["room", "payload"]}},
    )
    return reg