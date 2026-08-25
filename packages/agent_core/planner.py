# RAPTOR — Planner (yapılandırılmış plan + beklenen kanıt)
from __future__ import annotations


class Planner:
    def __init__(self) -> None:
        # Görev tipi -> adım şablonları
        self._templates = {
            "observe": {
                "tools": ["technocore_read", "github_repo_read", "http_json_read"],
                "steps": ["kaynakları oku", "değişikliği tespit et", "kanıt topla"],
            },
            "source_health": {"tools": ["internal_health"], "steps": ["container sağlığını kontrol et"]},
            "investigate": {"tools": ["http_json_read", "github_repo_read"], "steps": ["sorgula", "çapraz doğrula"]},
        }

    async def make_plan(self, task: dict) -> dict:
        goal = (task.get("scope") or {}).get("kind", "observe")
        tpl = self._templates.get(goal, self._templates["observe"])
        return {
            "goal": goal,
            "steps": tpl["steps"],
            "tools": tpl["tools"],
            "expected_evidence": ["kaynak içeriği", "değişiklik astarı", "zaman damgası"],
        }