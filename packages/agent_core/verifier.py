# RAPTOR — Verifier (çıktının kanıtını ve hedef koşullarını kontrol eder)
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class VerificationResult:
    passed: bool
    evidence: list[dict]
    notes: str = ""


class Verifier:
    def __init__(self) -> None:
        self._checks: list = []

    def add_check(self, name: str, fn) -> None:  # fn(result) -> (bool, dict)
        self._checks.append((name, fn))

    async def verify(self, run_result: dict) -> VerificationResult:
        evidence: list[dict] = []
        all_passed = True
        for name, fn in self._checks:
            try:
                ok, meta = fn(run_result)
            except Exception as e:  # pragma: no cover
                ok, meta = False, {"error": type(e).__name__}
            evidence.append({"check": name, "passed": ok, "meta": meta})
            all_passed = all_passed and ok
        return VerificationResult(passed=all_passed, evidence=evidence)


class DefaultVerifier(Verifier):
    def __init__(self) -> None:
        super().__init__()
        # Hedef: çıktıda ya planlanan olgu ya da "doğrulanamadı" açıklaması olmalı
        async def _wrapper(fn):
            return fn
        self.add_check("hedef_kanit_var_mi", lambda r: (bool(r.get("evidence")) or bool(r.get("claim")), {
            "has_evidence": bool(r.get("evidence")), "claim": r.get("claim")
        }))