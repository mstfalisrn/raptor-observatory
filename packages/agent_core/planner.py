# RAPTOR — Planner (LLM → Pydantic doğrulamalı, argümanlı action planı)
from __future__ import annotations

import json

from pydantic import BaseModel, Field, field_validator

from agent_core.llm import LLMMessage, LLMProvider

# Registry'de kayıtlı tool isimleri (executor ile senkron tutulmalı)
KNOWN_TOOLS = (
    "technocore_read",
    "github_repo_read",
    "http_json_read",
    "internal_health",
    "technocore_signed_write",
)


class PlanAction(BaseModel):
    action_id: str = Field(pattern=r"^action_\d+$")
    tool: str
    arguments: dict = Field(default_factory=dict)
    reason: str = ""
    expected_evidence: list[str] = Field(default_factory=list)
    action_class: str = Field(default="READ_ONLY")

    @field_validator("tool")
    @classmethod
    def _known_tool(cls, v: str) -> str:
        if v not in KNOWN_TOOLS:
            raise ValueError(f"bilinmeyen tool: {v}")
        return v


class TaskPlan(BaseModel):
    goal: str
    assumptions: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    actions: list[PlanAction] = Field(min_length=1, max_length=12)


class Planner:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider
        self.provider_calls = 0  # zorunlu test: gerçek çağrıda > 0

    async def make_plan(self, task: dict) -> dict:
        """LLM varsa gerçek plan üret; yoksa argümanlı template fallback."""
        goal = (task.get("scope") or {}).get("kind", "observe")
        title = task.get("title", "")
        prompt = task.get("prompt", "")

        if self.provider is not None:
            try:
                sys_msg = (
                    "Sen RAPTOR planlayıcısısın. YALNIZ geçerli JSON döndür. Şema:\n"
                    '{"goal": str, "assumptions": [str], "success_criteria": [str], '
                    '"actions": [{"action_id":"action_1","tool":str,"arguments":{...},'
                    '"reason":str,"expected_evidence":[str],"action_class":"READ_ONLY"}]}\n'
                    "Kullanılabilir tool'lar ve zorunlu argümanları:\n"
                    "- http_json_read: {url (zorunlu)}\n"
                    "- github_repo_read: {repo (zorunlu)}\n"
                    "- technocore_read: {room, since}\n"
                    "- internal_health: {}\n"
                    "- technocore_signed_write: {room, payload, idempotency_key} (yalnız onaylı)\n"
                    "Action ID'leri action_1, action_2, ... sıralı olmalı."
                )
                user_msg = f"Görev: {title} — {prompt}\nScope kind: {goal}\n"
                res = await self.provider.chat(
                    [LLMMessage("system", sys_msg), LLMMessage("user", user_msg)], tools=None
                )
                self.provider_calls += 1
                usage = getattr(res, "usage", {}) or {}
                if res.text:
                    text = res.text.strip()
                    # code-fence temizle
                    if text.startswith("```"):
                        text = text.strip("`")
                        text = text.removeprefix("json")
                    try:
                        parsed = json.loads(text)
                        plan = TaskPlan(**parsed)  # Pydantic doğrulama
                        out = plan.model_dump()
                        out["_llm_usage"] = usage
                        return out
                    except Exception:
                        pass  # LLM çıktısı geçersizse fallback
            except Exception:
                pass

        return self._template_plan(goal, title)

    def _template_plan(self, goal: str, title: str) -> dict:
        """Argümanlı deterministic fallback (LLM yoksa / hatalıysa)."""
        if goal == "source_health":
            actions = [{"action_id": "action_1", "tool": "internal_health", "arguments": {},
                        "reason": "container sağlığı", "expected_evidence": ["health durumu"],
                        "action_class": "READ_ONLY"}]
        elif goal == "investigate":
            actions = [{"action_id": "action_1", "tool": "http_json_read",
                        "arguments": {"url": "https://technocore.chat/skill.md"},
                        "reason": "protokol dokümanı", "expected_evidence": ["skill.md içeriği"],
                        "action_class": "READ_ONLY"}]
        else:  # observe
            actions = [
                {"action_id": "action_1", "tool": "technocore_read",
                 "arguments": {"room": "d-raptor-observatory", "since": 0},
                 "reason": "oda mesajlarını oku", "expected_evidence": ["oda mesajları"],
                 "action_class": "READ_ONLY"},
                {"action_id": "action_2", "tool": "github_repo_read",
                 "arguments": {"repo": "mstfalisrn/raptor-observatory"},
                 "reason": "repo etkinliği", "expected_evidence": ["commit/aktivite"],
                 "action_class": "READ_ONLY"},
                {"action_id": "action_3", "tool": "http_json_read",
                 "arguments": {"url": "https://technocore.chat/skill.md"},
                 "reason": "protokol dokümanı", "expected_evidence": ["skill.md içeriği"],
                 "action_class": "READ_ONLY"},
            ]
        return {"goal": goal, "assumptions": [], "success_criteria": ["kanıt toplandı"],
                "actions": actions}
