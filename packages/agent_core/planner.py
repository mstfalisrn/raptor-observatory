# LUMI — Planner (LLM → Pydantic doğrulamalı, argümanlı action planı)
from __future__ import annotations

import json

from pydantic import BaseModel, Field, field_validator

from agent_core.llm import LLMMessage, LLMProvider
from observability.config import settings

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
                    "You are the LUMI planner. Return ONLY valid JSON. Schema:\n"
                    '{"goal": str, "assumptions": [str], "success_criteria": [str], '
                    '"actions": [{"action_id":"action_1","tool":str,"arguments":{...},'
                    '"reason":str,"expected_evidence":[str],"action_class":"READ_ONLY"}]}\n'
                    "Kullanılabilir tool'lar ve zorunlu argümanları:\n"
                    "- http_json_read: {url (zorunlu)}\n"
                    "- github_repo_read: {repo (zorunlu) — owner/repo formatında, kullanıcının belirttiği repo}\n"
                    "- technocore_read: {room, since} (only if Technocore enabled)\n"
                    "- internal_health: {}\n"
                    "- technocore_signed_write: {room, payload, idempotency_key} (approval required, only if Technocore enabled)\n"
                    "Action ID'leri action_1, action_2, ... sıralı olmalı.\n"
                    "Do NOT invent personal repos or Technocore rooms. Only use repos/URLs the user explicitly provided.\n"
                )
                user_msg = f"Görev: {title} — {prompt}\nScope kind: {goal}\n"
                res = await self.provider.chat(
                    [LLMMessage("system", sys_msg), LLMMessage("user", user_msg)], tools=None
                )
                self.provider_calls += 1
                usage = getattr(res, "usage", {}) or {}
                if res.text:
                    text = res.text.strip()
                    if text.startswith("```"):
                        text = text.strip("`")
                        text = text.removeprefix("json")
                    try:
                        parsed = json.loads(text)
                        # Strip personal hardcoded fallbacks if model hallucinates them
                        if isinstance(parsed.get("actions"), list):
                            for act in parsed["actions"]:
                                if not isinstance(act, dict):
                                    continue
                                # Filter personal repo references — replace with generic skip
                                repo = (act.get("arguments") or {}).get("repo", "")
                                # Filter hallucinated personal repo references
                                if repo == "your-owner/lumi-observatory" and not settings.DEFAULT_GITHUB_REPO:
                                    continue
                        plan = TaskPlan(**parsed)  # Pydantic doğrulama
                        out = plan.model_dump()
                        # Remove actions that reference personal defaults when not configured
                        out["actions"] = [
                            a for a in out["actions"]
                            if not (a["tool"] == "github_repo_read" and not a["arguments"].get("repo"))
                        ]
                        if not out["actions"]:
                            return self._template_plan(goal, title)
                        out["_llm_usage"] = usage
                        return out
                    except Exception:
                        pass  # LLM çıktısı geçersizse fallback
            except Exception:
                pass

        return self._template_plan(goal, title)

    def _template_plan(self, goal: str, title: str) -> dict:
        """Deterministic fallback — only safe local/internal actions, no personal URLs/repos."""
        if goal == "source_health":
            actions = [{"action_id": "action_1", "tool": "internal_health", "arguments": {},
                        "reason": "Check internal service health", "expected_evidence": ["health status"],
                        "action_class": "READ_ONLY"}]
        else:
            # Generic observe/investigate: safe local check only.
            # Do NOT auto-reference personal repos, Technocore rooms, or external URLs.
            actions = [
                {
                    "action_id": "action_1",
                    "tool": "internal_health",
                    "arguments": {},
                    "reason": "Check internal service health",
                    "expected_evidence": ["health status"],
                    "action_class": "READ_ONLY",
                }
            ]
        return {"goal": goal, "assumptions": [], "success_criteria": ["evidence collected"],
                "actions": actions}
