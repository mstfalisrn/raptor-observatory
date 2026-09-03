# LUMI — Verifier (çıktının kanıtını ve hedef koşullarını kontrol eder)
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
        # hiç check yoksa bile evidence'e göre karar ver
        if not self._checks:
            ev = run_result.get("evidence") or []
            # en az bir başarılı tool + hiç hata yok
            has_ok = any(x.get("ok") for x in ev) if isinstance(ev, list) else False
            has_err = any(not x.get("ok", True) for x in ev) if isinstance(ev, list) else False
            all_passed = bool(ev) and has_ok and not has_err
            evidence.append({"check": "default_evidence", "passed": all_passed, "meta": {"n": len(ev) if isinstance(ev, list) else 0}})
        return VerificationResult(passed=all_passed, evidence=evidence)


class DefaultVerifier(Verifier):
    def __init__(self) -> None:
        super().__init__()
        # Gerçek kanıt: en az bir başarılı tool + hata yok + evidence var
        def _evidence_check(r: dict):
            ev = r.get("evidence") or []
            if not ev:
                return False, {"has_evidence": False}
            has_ok = any(x.get("ok") for x in ev)
            has_err = any(not x.get("ok", True) for x in ev)
            return (has_ok and not has_err), {"has_evidence": bool(ev), "has_ok": has_ok, "has_err": has_err, "n": len(ev)}

        self.add_check("hedef_kanit_var_mi", _evidence_check)
