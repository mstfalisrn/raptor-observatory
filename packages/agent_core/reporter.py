# RAPTOR — Reporter (kısa insan özeti + makine-okunur sonuç paketi)
from __future__ import annotations

from datetime import UTC, datetime


class Reporter:
    def human_summary(self, run: dict) -> str:
        status = run.get("status", "UNKNOWN")
        summary = {
            "COMPLETED": f"✅ Tamamlandı — {run.get('id','')[:8]}",
            "FAILED": f"❌ Başarısız — {run.get('error','hata')}",
            "WAITING_APPROVAL": "🕐 Onay bekliyor",
            "PAUSED": "⏸️ Duraklatıldı",
            "CANCELLED": "🚫 İptal",
        }.get(status, f"ℹ️ {status}")
        return summary

    def machine_result(self, *, run_id: str, status: str, claim: str = "",
                       evidence: list | None = None, confidence: float = 0.0,
                       reports: list | None = None, error: str | None = None) -> dict:
        return {
            "run_id": run_id,
            "status": status,
            "claim": claim,
            "evidence": evidence or [],
            "confidence": confidence,
            "reports": reports or [],
            "error": error,
            "generated_at": datetime.now(UTC).isoformat(),
        }


def build_public_report(
    *, report_type: str, observed_at: str, subject: str, change: str,
    evidence: str, confidence: float, schema_version: int = 1,
) -> dict:
    """Public report şeması: type, observed_at, subject, change, evidence, confidence, schema_version."""
    return {
        "type": report_type,
        "observed_at": observed_at,
        "subject": subject,
        "change": change,
        "evidence": evidence,
        "confidence": confidence,
        "schema_version": schema_version,
    }