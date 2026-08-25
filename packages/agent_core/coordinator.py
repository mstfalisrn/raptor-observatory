# RAPTOR — Run Coordinator (görev state machine + bütçe/sınır/kill switch)
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from observability.config import settings
from observability.models import RunStatus


@dataclass
class RunBudget:
    max_iterations: int = settings.RUN_MAX_ITERATIONS
    max_tool_calls: int = settings.RUN_MAX_TOOL_CALLS
    max_wall_seconds: int = settings.RUN_MAX_WALL_SECONDS
    max_tokens: int = settings.RUN_MAX_TOKEN_BUDGET
    max_cost: float = settings.RUN_MAX_COST_BUDGET


class CircuitBreaker:
    def __init__(self, threshold: int = 5, cooldown: float = 30.0) -> None:
        self._threshold = threshold
        self._cooldown = cooldown
        self._failures: dict[str, list[float]] = {}

    def record_failure(self, key: str) -> bool:
        now = time.monotonic()
        lst = self._failures.setdefault(key, [])
        lst = [t for t in lst if now - t < self._cooldown]
        lst.append(now)
        self._failures[key] = lst
        return len(lst) >= self._threshold  # açıksa True

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


class RunCoordinator:
    """Tek run'ı QUEUED -> ... -> COMPLETED/FAILED/CANCELLED/PAUSED yürütür."""

    def __init__(self, run_id: str | None = None, budget: RunBudget | None = None,
                 *, allowlist_tools: set[str] | None = None) -> None:
        self.run_id = run_id or str(uuid.uuid4())
        self.budget = budget or RunBudget()
        self.status = RunStatus.QUEUED
        self.iteration = 0
        self.tool_calls_count = 0
        self.started_at: float | None = None
        self.tokens_used = 0
        self.cost_used = 0.0
        self._kill = False
        self._pause = False
        self._stop_event = asyncio.Event()
        self._breaker = CircuitBreaker()
        self.allowlist = allowlist_tools or set()
        self._events: list[dict] = []

    # --- kontrol ---
    def request_stop(self) -> None:
        self._kill = True
        self._stop_event.set()

    def request_pause(self) -> None:
        self._pause = True

    def resume(self) -> None:
        self._pause = False

    @property
    def is_killed(self) -> bool:
        return self._kill

    def emit(self, etype: str, payload: dict) -> None:
        self._events.append({"event_type": etype, "payload": payload, "seq": len(self._events)})

    # --- guardrail ---
    def can_continue(self) -> bool:
        if self._kill:
            return False
        if self._pause:
            self.emit("PAUSED", {})
            return False
        if self.started_at and (time.monotonic() - self.started_at) > self.budget.max_wall_seconds:
            self.emit("WALL_TIME_EXCEEDED", {})
            return False
        if self.iteration >= self.budget.max_iterations:
            self.emit("ITERATION_LIMIT", {"limit": self.budget.max_iterations})
            return False
        if self.tool_calls_count >= self.budget.max_tool_calls:
            self.emit("TOOL_CALL_LIMIT", {"limit": self.budget.max_tool_calls})
            return False
        if self.tokens_used > self.budget.max_tokens:
            self.emit("TOKEN_BUDGET_EXCEEDED", {})
            return False
        if self.cost_used > self.budget.max_cost:
            self.emit("COST_BUDGET_EXCEEDED", {})
            return False
        return True

    # --- ana döngü ---
    async def run(self, executor, planner, assembler, policy, provider, verifier):
        """Coordinator döngüsü — belli araçlar ve onay motoruyla çalışır."""
        self.status = RunStatus.CONTEXT_BUILDING
        self.started_at = time.monotonic()
        self.emit("STARTED", {"run_id": self.run_id})

        # 1) plan
        self.status = RunStatus.PLANNING
        plan = await planner.make_plan(task=executor.task)
        self.emit("PLAN", {"plan": plan})

        # 2) context
        ordered, prompt = assembler.assemble()
        self.emit("CONTEXT", {"segments": assembler.inspector_metadata()})

        executed = []
        # her plan aracı yalnızca BİR kez çalıştırılır (iteration, araç sayısı kadardır)
        plan_tools = [t for t in plan.get("tools", []) if not self.allowlist or t in self.allowlist]
        for tool in plan_tools:
            if not self.can_continue():
                break
            self.iteration += 1
            self.status = RunStatus.EXECUTING

            decision = policy.decide(tool)
            self.emit("POLICY_CHECK", {"tool": tool, "decision": decision.decision})

            if decision.decision == "DENY":
                self.status = RunStatus.FAILED
                self.emit("DENIED", {"tool": tool})
                break

            if decision.decision == "REQUIRE_APPROVAL":
                self.status = RunStatus.WAITING_APPROVAL
                self.emit("AWAITING_APPROVAL", {"tool": tool})
                # worker dışarıdan onay ister; bloker döner
                break

            try:
                result = await executor.execute(tool)
                self.tool_calls_count += 1
                executed.append({"tool": tool, "result": result})
                self.emit("TOOL_CALL", {"tool": tool, "ok": True})
                self._breaker.reset(tool)
            except Exception as e:
                self.emit("TOOL_ERROR", {"tool": tool, "error": type(e).__name__})
                if self._breaker.record_failure(tool):
                    self.status = RunStatus.FAILED
                    self.emit("CIRCUIT_OPEN", {"tool": tool})
                    break

        if self._pause:
            self.status = RunStatus.PAUSED
        elif self._kill:
            self.status = RunStatus.CANCELLED
        elif self.status == RunStatus.QUEUED or self.status == RunStatus.EXECUTING:
            # normal bitiş
            self.status = RunStatus.VERIFYING
            try:
                vres = await verifier.verify({"evidence": executed})
            except Exception:
                vres = None
            self.emit("VERIFY", {"passed": bool(vres and vres.passed)})
            self.status = RunStatus.PERSISTING if not self.is_killed else RunStatus.CANCELLED

        if self.status not in (RunStatus.CANCELLED.value, RunStatus.PAUSED.value, RunStatus.WAITING_APPROVAL.value, RunStatus.FAILED.value):
            if self.status == RunStatus.PERSISTING:
                self.status = RunStatus.COMPLETED
        self.emit("END", {"final_status": self.status.value})
        return self.status.value, executed, self._events