# RAPTOR — Context Assembler / Inspector
# Bağlamı token bütçesine göre katmanlar; gizli chain-of-thought GÖSTERMEZ.
# Her segment meta veri: segment_type, source_id, title, token_count, relevance,
# freshness, confidence, included_reason, contains_untrusted, redaction_count.
# Faz4: katmanlar ayrık (system_policy / task_goal / memory / tool_schemas / untrusted),
#       overwrite hatası düzeltildi (dict -> list), token counting iyileştirildi.

from __future__ import annotations

import dataclasses
import re
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


# Basit token tahmini (~4 karakter/token) — tiktoken varsa daha doğru say
def estimate_tokens(text: str) -> int:
    # tiktoken mevcutsa cl100k_base kullan, yoksa fallback
    try:
        import tiktoken  # type: ignore

        enc = tiktoken.get_encoding("cl100k_base")
        return max(1, len(enc.encode(text)))
    except Exception:
        return max(1, len(text) // 4)


# Daima rezerve edilen çıktı payı (output reserve sıfırlanamaz)
OUTPUT_RESERVE_TOKENS = 2048

# Katman tanımı — 5 ana katman + uyumluluk için alt tipler
# Öncelik sırası: düşük sayı = yüksek öncelik (önce dahil edilir)
LAYER_PRIORITY: dict[str, int] = {
    "system_policy": 0,
    "task_goal": 1,
    "conversation_window": 2,
    # memory grubu — hepsi aynı katman
    "episodic_memory": 3,
    "semantic_memory": 3,
    "procedural_memory": 3,
    "memory": 3,
    "tool_schemas": 4,
    # untrusted — en düşük öncelik, ayrı sınırlandırılır
    "untrusted": 5,
    "tool_output": 5,
    "external_data": 5,
}

# Kanonik katman sırası (SEQUENCE) — geriye uyum için eski + yeni tipler
SEQUENCE = [
    "system_policy",
    "task_goal",
    "conversation_window",
    "episodic_memory",
    "semantic_memory",
    "procedural_memory",
    "memory",
    "tool_schemas",
    "untrusted",
]

# Katman -> maksimum pay (bütçenin oranı) — untrusted sınırlandırılır
LAYER_BUDGET_RATIO: dict[str, float] = {
    "untrusted": 0.25,  # untrusted toplam bütçenin %25'ini aşamaz
}

# Redaction placeholders — geniş sayım için
_REDACTED_RE = re.compile(r"<[^>]*REDACTED[^>]*>")

# Untrusted içeriği izole etmek için sınır işaretleri
UNTRUSTED_BEGIN = "<<<UNTRUSTED_DATA_BEGIN>>>"
UNTRUSTED_END = "<<<UNTRUSTED_DATA_END>>>"


def _layer_of(segment_type: str) -> str:
    """Segment tipini kanonik katmana eşle."""
    if segment_type in LAYER_PRIORITY:
        # memory alt tiplerini 'memory' olarak normalize etme — öncelik aynı
        return segment_type
    # bilinmeyen tipler 'untrusted' sayılmaz, kendi katmanı
    return segment_type


def _priority(segment_type: str) -> int:
    return LAYER_PRIORITY.get(segment_type, 99)


class ContextAssembler:
    """Bağlam katmanlarını toplayıcı; token budget'a uyar, untrusted izole eder."""

    # dışa açık sabitler
    SEQUENCE = SEQUENCE
    OUTPUT_RESERVE_TOKENS = OUTPUT_RESERVE_TOKENS

    def __init__(self, max_tokens: int = 60000, *, redactor: Any = None) -> None:
        self.max_tokens = max(OUTPUT_RESERVE_TOKENS + 1024, max_tokens)
        self.redactor = redactor
        # Faz4 düzeltmesi: dict -> list (overwrite bug çözümü)
        # Aynı segment_type birden fazla kez eklenebilir (örn. memory birden fazla hit)
        self._segments: list[ContextSegment] = []

    def add(self, segment_type: str, content: str, *, title: str = "", source_id: str = "",
            relevance: float = 0.0, confidence: float = 0.0, untrusted: bool = False) -> None:
        # DLP: redact
        if self.redactor is not None:
            scrub = self.redactor.scrub
        else:
            from observability.security import redact
            scrub = redact  # type: ignore[assignment]
        content = scrub(content)

        # Untrusted izolasyonu: ayrı işaretleme + boundary
        is_untrusted = untrusted or segment_type in ("untrusted", "tool_output", "external_data")
        if is_untrusted:
            # içeriği boundary içine al (prompt injection mitigasyonu)
            if UNTRUSTED_BEGIN not in content:
                content = f"{UNTRUSTED_BEGIN}\n{content}\n{UNTRUSTED_END}"

        # redaction sayımı — tüm varyantları say
        redactions = len(_REDACTED_RE.findall(content))

        seg = ContextSegment(
            segment_type=segment_type,
            source_id=source_id,
            title=title,
            content=content,
            token_count=estimate_tokens(content),
            relevance_score=relevance,
            freshness=str(int(time.time())),
            confidence=confidence,
            included_reason=f"katman {segment_type} -> bütçe kurallı seçim",
            contains_untrusted_input=is_untrusted,
            redaction_count=redactions,
        )
        # overwrite yok — append
        self._segments.append(seg)

    def assemble(self) -> tuple[list[ContextSegment], str]:
        """Bütçe içinde segment'leri sıralı döndürür + birleşik denetlenebilir prompt üretir."""
        ordered: list[ContextSegment] = []
        budget = self.max_tokens - OUTPUT_RESERVE_TOKENS
        used = 0
        untrusted_used = 0
        untrusted_budget = int(budget * LAYER_BUDGET_RATIO.get("untrusted", 0.25))

        # Öncelik sırası sabit, ardından relevance sıralaması
        # Sequence içindeki tipleri öncelik sırasına göre işle; aynı tipte birden fazla segment olabilir
        # Önce sequence sırası
        seq_segments: list[ContextSegment] = []
        remaining: list[ContextSegment] = []
        # segment_type'a göre grupla ama sırayı koru
        seg_by_type: dict[str, list[ContextSegment]] = {}
        for s in self._segments:
            seg_by_type.setdefault(s.segment_type, []).append(s)
        # SEQUENCE sırasına göre ekle
        for stype in self.SEQUENCE:
            for seg in seg_by_type.pop(stype, []):
                seq_segments.append(seg)
        # kalan unknown tipler
        for segs in seg_by_type.values():
            remaining.extend(segs)
        # remaining relevance'a göre sırala
        remaining.sort(key=lambda s: s.relevance_score, reverse=True)

        all_in_order = seq_segments + remaining

        for seg in all_in_order:
            # katman bütçesi kontrolü (untrusted sınırlı)
            if seg.contains_untrusted_input:
                if untrusted_used + seg.token_count > untrusted_budget:
                    seg.included_reason = "untrusted katman bütçesi aşımı → atlandı"
                    continue
            # genel bütçe kontrolü — system_policy ve task_goal her zaman dahil (kritik)
            if used + seg.token_count > budget and seg.segment_type not in ("system_policy", "task_goal"):
                seg.included_reason = "token bütçesi aşımı → atlandı"
                continue
            ordered.append(seg)
            used += seg.token_count
            if seg.contains_untrusted_input:
                untrusted_used += seg.token_count

        # denetlenebilir prompt: her segment başına bilgi notu, gizli düşünce yok
        # Katman sınırları açıkça işaretlenir
        parts = []
        for seg in ordered:
            untagged = " [UNTRUSTED]" if seg.contains_untrusted_input else ""
            parts.append(
                f"### {seg.segment_type}{untagged} ({seg.included_reason})\n{seg.content}"
            )
        prompt = "\n\n".join(parts)
        return ordered, prompt

    def inspector_metadata(self) -> list[dict]:
        # Faz4: tüm segmentleri döndür (dahil edilmeyenler de reason ile)
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
            for s in self._segments
        ]

    # Yardımcı: katman bazlı token toplamları (inspector için)
    def layer_token_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self._segments:
            counts[s.segment_type] = counts.get(s.segment_type, 0) + s.token_count
        return counts
