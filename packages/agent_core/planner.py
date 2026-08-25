# RAPTOR — Planner (LLM'e bağlı yapılandırılmış plan)
from __future__ import annotations

import json
from typing import Any

from agent_core.llm import LLMMessage, LLMProvider


class Planner:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider
        self._templates: dict[str, dict[str, Any]] = {
            "observe": {
                "tools": ["technocore_read", "github_repo_read", "http_json_read"],
                "steps": ["kaynakları oku", "değişikliği tespit et", "kanıt topla"],
            },
            "source_health": {"tools": ["internal_health"], "steps": ["container sağlığını kontrol et"]},
            "investigate": {"tools": ["http_json_read", "github_repo_read"], "steps": ["sorgula", "çapraz doğrula"]},
        }

    async def make_plan(self, task: dict) -> dict:
        goal = (task.get("scope") or {}).get("kind", "observe")
        # LLM varsa gerçek plan iste, yoksa template fallback
        if self.provider is not None:
            try:
                prompt = (
                    f"Görev: {task.get('title','')} — {task.get('prompt','')}\n"
                    f"Scope kind: {goal}\n"
                    "Senden beklenen: JSON olarak {goal, steps:[], tools:[], expected_evidence:[], assumptions:[], success_criterion, risk} döndür. "
                    "Yalnız registry'de olan tool'ları seç: technocore_read, github_repo_read, http_json_read, internal_health, technocore_signed_write."
                )
                res = await self.provider.chat(
                    [LLMMessage("system", "Sen RAPTOR planlayıcısısın. Yalnız JSON döndür."), LLMMessage("user", prompt)],
                    tools=None,
                )
                # usage bilgisini task'a iliştir (bütçe için)
                usage = getattr(res, "usage", {}) or {}
                if res.text:
                    try:
                        parsed = json.loads(res.text)
                        # minimal validation
                        if "tools" in parsed and isinstance(parsed["tools"], list):
                            parsed.setdefault("goal", goal)
                            parsed.setdefault("steps", [])
                            parsed.setdefault("expected_evidence", [])
                            parsed["_llm_usage"] = usage
                            return parsed
                    except Exception:
                        pass
            except Exception:
                pass
        tpl = self._templates.get(goal, self._templates["observe"])
        return {
            "goal": goal,
            "steps": tpl["steps"],
            "tools": tpl["tools"],
            "expected_evidence": ["kaynak içeriği", "değişiklik astarı", "zaman damgası"],
        }
