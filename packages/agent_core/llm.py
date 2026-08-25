# RAPTOR — LLM provider arayüzü + OpenAI-compatible + mock
# Provider bağımsız; env ile base_url/model/api_key seçilir. Hermes env'ine dokunmaz.
from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from observability.config import settings


@dataclass
class LLMMessage:
    role: str  # system | user | assistant | tool
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass
class LLMToolCall:
    name: str
    arguments: dict
    id: str | None = None


@dataclass
class LLMResult:
    text: str = ""
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    finish_reason: str = ""
    usage: dict = field(default_factory=dict)
    # redact edilmemiş gizli düşünce YOK — denetlenebilir metadata döner


class LLMProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def chat(self, messages: list[LLMMessage], tools: list[dict] | None = None, **kw) -> LLMResult:
        ...

    @abc.abstractmethod
    async def check(self) -> bool:
        """Sağlayıcı erişilebilir mi (health)."""


class MockProvider(LLMProvider):
    """Test/dev varsayılan sağlayıcısı. Gerçek çağrı yapmaz; deterministic plan üretir."""

    name = "mock"

    async def chat(self, messages, tools=None, **kw) -> LLMResult:
        return LLMResult(
            text="[mock] Plan: sorgula-bağlam kur, ardından raporla.",
            finish_reason="stop",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

    async def check(self) -> bool:
        return True


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible Chat / Responses tarzı endpoint."""

    name = "openai_compatible"

    def __init__(self, base_url: str, model: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=60.0)

    async def chat(self, messages, tools=None, **kw) -> LLMResult:
        url = f"{self.base_url}/chat/completions"
        payload: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            **kw,
        }
        if tools is not None:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
        headers = {"Authorization": f"Bearer {self.api_key}"}
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        msg = data["choices"][0]["message"]
        tool_calls = [
            LLMToolCall(
                name=tc["function"]["name"],
                arguments=json.loads(tc["function"].get("arguments") or "{}"),
                id=tc.get("id"),
            )
            for tc in msg.get("tool_calls", [])
        ]
        return LLMResult(
            text=msg.get("content") or "",
            tool_calls=tool_calls,
            finish_reason=data["choices"][0].get("finish_reason", ""),
            usage=data.get("usage", {}),
        )

    async def check(self) -> bool:
        try:
            await self.chat([LLMMessage("user", "ping")])
            return True
        except Exception:
            return False


def build_provider(provider: str | None = None) -> LLMProvider:
    p = (provider or settings.LLM_PROVIDER or "mock").lower()
    if p == "openai_compatible" or p == "openai":
        return OpenAICompatibleProvider(
            settings.LLM_BASE_URL, settings.LLM_MODEL, settings.LLM_API_KEY
        )
    return MockProvider()