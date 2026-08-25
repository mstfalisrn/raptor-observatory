# RAPTOR — Context Assembler / Inspector
# Bağlamı token bütçesine göre katmanlar; gizli chain-of-thought GÖSTERMEZ.
# Her segment meta veri: segment_type, source_id, title, token_count, relevance,
# freshness, confidence, included_reason, contains_untrusted, redaction_count.

from __future__ import annotations

import dataclasses
import time
from typing import Any


@dataclasses.dataclass
class ContextSegment:
    segment_type: str
    source_id: str
    title: str
    content: str
    token_count: int = 0
    relevance_score: float = 0.0
    freshness: str = ""
    confidence: float = 0.0
    included_reason: str = ""
    contains_untrusted_input: bool = False
    redaction_count: int = 0


# Basit token tahmini (~4 karakter/token)
def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# Daima rezerve edilen çıktı payı (output reserve sıfırlanamaz)
OUTPUT_RESERVE_TOKENS = 2048


class ContextAssembler:
    """Bağlam katmanlarını toplayıcı; token budget'a uyar, untrusted izole eder."""

    SEQUENCE = [
        "system_policy",
        "task_goal",
        "conversation_window",
        "episodic_memory",
        "semantic_memory",
        "procedural_memory",
        "tool_schemas",
    ]

    def __init__(self, max_tokens: int = 60000, *, redactor: Any = None) -> None:
        self.max_tokens = max(OUTPUT_RESERVE_TOKENS + 1024, max_tokens)
        self.redactor = redactor
        self._segments: dict[str, ContextSegment] = {}

    def add(self, segment_type: str, content: str, *, title: str = "", source_id: str = "",
            relevance: float = 0.0, confidence: float = 0.0, untrusted: bool = False) -> None:
        if self.redactor is not None:
            scrub = self.redactor.scrub
        else:
            from observability.security import redact
            scrub = redact  # type: ignore[assignment]
        content = scrub(content)
        redactions = 0
        if "<REDACTED>" in content or "<SECRET_REDACTED>" in content:
            redactions = content.count("<REDACTED>") + content.count("<SECRET_REDACTED>")
        self._segments[segment_type] = ContextSegment(
            segment_type=segment_type,
            source_id=source_id,
            title=title,
            content=content,
            token_count=estimate_tokens(content),
            relevance_score=relevance,
            freshness=str(int(time.time())),
            confidence=confidence,
            included_reason=f"katman {segment_type} -> bütçe kurallı seçim",
            contains_untrusted_input=untrusted,
            redaction_count=redactions,
        )

    def assemble(self) -> tuple[list[ContextSegment], str]:
        """Bütçe içinde segment'leri sıralı döndürür + birleşik denetlenebilir prompt üretir."""
        ordered = []
        budget = self.max_tokens - OUTPUT_RESERVE_TOKENS
        used = 0
        # öncelik sırası sabit, ardından relevance sıralaması
        for stype in self.SEQUENCE:
            seg = self._segments.get(stype)
            if seg is None:
                continue
            if used + seg.token_count > budget and stype not in ("system_policy", "task_goal"):
                seg.included_reason = "token bütçesi aşımı → atlandı"
                continue
            ordered.append(seg)
            used += seg.token_count

        # kalan katmanlar relevance'a göre
        extras = sorted(
            [s for s in self._segments.values() if s not in ordered],
            key=lambda s: s.relevance_score,
            reverse=True,
        )
        for seg in extras:
            if used + seg.token_count > budget:
                seg.included_reason = "token bütçesi aşımı → atlandı"
                continue
            ordered.append(seg)
            used += seg.token_count

        # denetlenebilir prompt: her segment başına bilgi notu, gizli düşünce yok
        parts = []
        for seg in ordered:
            untagged = " [UNTRUSTED]" if seg.contains_untrusted_input else ""
            parts.append(
                f"### {seg.segment_type}{untagged} ({seg.included_reason})\n{seg.content}"
            )
        prompt = "\n\n".join(parts)
        return ordered, prompt

    def inspector_metadata(self) -> list[dict]:
        return [
            {
                "segment_type": s.segment_type,
                "title": s.title,
                "token_count": s.token_count,
                "relevance_score": s.relevance_score,
                "freshness": s.freshness,
                "confidence": s.confidence,
                "included_reason": s.included_reason,
                "contains_untrusted_input": s.contains_untrusted_input,
                "redaction_count": s.redaction_count,
            }
            for s in self._segments.values()
        ]