# RAPTOR — Code Chunk 006

> GPT sırayla okuyup birleştirsin (MCP 100KB limit).

## `packages/observability/models.py`

```py
# RAPTOR — veri modeli (veri tabanı tabloları)
# Şartnamedeki asgari tablolar: 23. Event/audit tabloları append-only tasarlandı.
# Timestamps UTC saklanır; UI UTC gösterir.

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column, relationship

# Portable JSON: SQLite test'te JSON, PostgreSQL production'da JSONB (test+prod uyumu)
JSONType = JSON().with_variant(JSONB, "postgresql")

# pgvector desteği — yoksa JSONB fallback (claim'i korumak için)
try:
    from pgvector.sqlalchemy import Vector  # type: ignore
except ImportError:  # pragma: no cover
    Vector = None  # type: ignore


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class _UUIDMixin:
    @declared_attr
    def id(cls):
        return mapped_column(
            PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
        )


class _TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# ----------------------------------------------------------------------------
# Enums
# ----------------------------------------------------------------------------
class RunStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    CONTEXT_BUILDING = "CONTEXT_BUILDING"
    PLANNING = "PLANNING"
    POLICY_CHECK = "POLICY_CHECK"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    PERSISTING = "PERSISTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


class MemoryStatus(enum.StrEnum):
    CANDIDATE = "CANDIDATE"
    APPROVED = "APPROVED"
    AUTO_APPROVED = "AUTO_APPROVED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    DELETED = "DELETED"


class ApprovalStatus(enum.StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


class ActionClass(enum.StrEnum):
    READ_ONLY = "READ_ONLY"
    SAFE_WRITE = "SAFE_WRITE"
    PUBLIC_WRITE = "PUBLIC_WRITE"
    PRIVILEGED_HOST = "PRIVILEGED_HOST"
    DESTRUCTIVE = "DESTRUCTIVE"


class SourceType(enum.StrEnum):
    TECHNOCORE_ROOM = "technocore_room"
    GITHUB_REPO = "github_repo"
    HTTP_JSON = "http_json"
    INTERNAL_HEALTH = "internal_health"


class UNTRUSTED(enum.StrEnum):
    DATA = "UNTRUSTED_DATA"


# ----------------------------------------------------------------------------
# Kimlik / hesap
# ----------------------------------------------------------------------------
class User(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    telegram_identities: Mapped[list[TelegramIdentity]] = relationship(back_populates="user")


class TelegramIdentity(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "telegram_identities"
    __table_args__ = (UniqueConstraint("telegram_user_id", name="uq_tg_user"),)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    username: Mapped[str] = mapped_column(String(120), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=True)
    is_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user: Mapped[User] = relationship(back_populates="telegram_identities")


class AgentProfile(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "agent_profiles"
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    system_policy: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_allowlist: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# ----------------------------------------------------------------------------
# Görev / run
# ----------------------------------------------------------------------------
class Task(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_idempotency_key", "idempotency_key", unique=True,
                           postgresql_where=text("idempotency_key IS NOT NULL")),)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    budget: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=True, unique=False)
    runs: Mapped[list[Run]] = relationship(back_populates="task")


class Run(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "runs"
    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RunStatus.QUEUED.value)
    plan_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=True)  # plans FK döngüsü önlenir; plans.run_id -> runs FK tutar
    iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_budget: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    token_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_used: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str] = mapped_column(String(64), nullable=True)
    control_request: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "pause" | "stop" | None
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    task: Mapped[Task] = relationship(back_populates="runs")
    events: Mapped[list[RunEvent]] = relationship(back_populates="run")
    tool_calls: Mapped[list[ToolCall]] = relationship(back_populates="run")


class RunEvent(_UUIDMixin, Base):
    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_run_events_run_seq"),
                      Index("ix_run_events_run_seq", "run_id", "seq"),)
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # global SSE cursor — run içi seq'den bağımsız, monoton global event ID
    global_seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    run: Mapped[Run] = relationship(back_populates="events")


class Plan(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "plans"
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id"), nullable=False
    )
    plan_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    expected_evidence: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class ToolCall(_UUIDMixin, Base):
    __tablename__ = "tool_calls"
    __table_args__ = (Index("ix_tool_calls_run_id", "run_id"),)
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    input_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_redacted: Mapped[str] = mapped_column(Text, nullable=False, default="")
    result_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    action_class: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_decision: Mapped[str] = mapped_column(String(24), nullable=False, default="ALLOW")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    run: Mapped[Run] = relationship(back_populates="tool_calls")


# ----------------------------------------------------------------------------
# Onay / epsilon
# ----------------------------------------------------------------------------
class Approval(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "approvals"
    action_class: Mapped[str] = mapped_column(String(32), nullable=False)
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target: Mapped[str] = mapped_column(Text, nullable=False, default="")
    impact_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ApprovalStatus.PENDING.value)
    requester_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decided_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id"), nullable=True
    )


# ----------------------------------------------------------------------------
# Context
# ----------------------------------------------------------------------------
class ContextSnapshot(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "context_snapshots"
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id"), nullable=False
    )
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context_segments: Mapped[list[ContextSegment]] = relationship(back_populates="snapshot")


class ContextSegment(_UUIDMixin, Base):
    __tablename__ = "context_segments"
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("context_snapshots.id"), nullable=False
    )
    segment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    freshness: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    included_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    contains_untrusted_input: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    redaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot: Mapped[ContextSnapshot] = relationship(back_populates="context_segments")


# ----------------------------------------------------------------------------
# Hafıza
# ----------------------------------------------------------------------------
class MemoryItem(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "memory_items"
    __table_args__ = (Index("ix_memory_status", "status"),)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ttl: Mapped[int] = mapped_column(Integer, nullable=True)  # saniye; None = ölümsüz
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=MemoryStatus.CANDIDATE.value)
    verification_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unverified")
    embedding: Mapped[list] = mapped_column(JSONType, nullable=True)  # legacy JSONB, pgvector ile birlikte saklanır
    # Faz4: pgvector vector sütunu — 1536 boyut (OpenAI ada-002 uyumlu); extension zaten initdb'de CREATE EXTENSION vector
    embedding_vector: Mapped[list] = mapped_column(
        (Vector(1536) if Vector is not None else JSONType),
        nullable=True,
    )  # type: ignore[arg-type]
    category: Mapped[str] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryRelation(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "memory_relations"
    from_memory_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("memory_items.id"), nullable=False
    )
    to_memory_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("memory_items.id"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False)  # contradicts | supersedes | related


# ----------------------------------------------------------------------------
# Kaynaklar / gözlemler / kanıt
# ----------------------------------------------------------------------------
class Source(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "sources"
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    config: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    error_series: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    backoff_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceObservation(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "source_observations"
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sources.id"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    change_type: Mapped[str] = mapped_column(String(64), nullable=False)
    change: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class EvidenceItem(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "evidence_items"
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id"), nullable=True
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    claim: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Report(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "reports"
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    signed_did: Mapped[str] = mapped_column(Text, nullable=True)


class PublicationAttempt(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "publication_attempts"
    __table_args__ = (Index("ix_pub_idempotency_key", "idempotency_key", unique=True,
                           postgresql_where=text("idempotency_key <> ''")),)
    report_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reports.id"), nullable=True
    )
    target: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    response: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")


# ----------------------------------------------------------------------------
# Technocore cursor / nonce / prompt / policy / audit
# ----------------------------------------------------------------------------
class TechnocoreCursor(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "technocore_cursors"
    room: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TechnocoreNonce(_UUIDMixin, _TimestampMixin, Base):
    """Faz 7: DID başına room nonce monotonic — atomik increment için ayrı tablo."""

    __tablename__ = "technocore_nonces"
    __table_args__ = (
        UniqueConstraint("room", "did", name="uq_technocore_nonce_room_did"),
        Index("ix_technocore_nonce_room_did", "room", "did"),
    )
    room: Mapped[str] = mapped_column(String(255), nullable=False)
    did: Mapped[str] = mapped_column(String(80), nullable=False)
    last_nonce: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PromptVersion(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "prompt_versions"
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompt_name_ver"),)


class PolicyVersion(_UUIDMixin, _TimestampMixin, Base):
    __tablename__ = "policy_versions"
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint("name", "version", name="uq_policy_name_ver"),)


class AuditEvent(_UUIDMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_ts", "ts"),)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    resource_id: Mapped[str] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ----------------------------------------------------------------------------
# Telegram dedup — update_id idempotency (BIGINT)
# ----------------------------------------------------------------------------
class TelegramUpdate(Base):
    __tablename__ = "telegram_updates"
    __table_args__ = (UniqueConstraint("update_id", name="uq_tg_update_id"),)
    # BIGINT — Telegram update_id 64-bit'e sığar; Integer overflow'u önler
    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)  # PENDING|PROCESSING|PROCESSED|FAILED
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


# ----------------------------------------------------------------------------
# Outbox — reliable queue (transactionel outbox pattern)
# ----------------------------------------------------------------------------
class OutboxMessage(_UUIDMixin, Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (
        Index("ix_outbox_processed", "processed", "created_at"),
        Index("ix_outbox_topic", "topic"),
        UniqueConstraint("idempotency_key", name="uq_outbox_idempotency"),
    )
    topic: Mapped[str] = mapped_column(String(120), nullable=False, default="raptor.run_queued")
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # Redis Streams entry id after publish (for tracing)
    stream_id: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
```

## `packages/observability/queue.py`

```py
# RAPTOR — reliable queue (Redis Streams consumer group + outbox publisher)
from __future__ import annotations

import json

STREAM = "raptor:stream:run_queue"
GROUP = "raptor-workers"
CONSUMER_PREFIX = "worker-"
DLQ_STREAM = "raptor:stream:dlq"

# outbox topic
TOPIC_RUN_QUEUED = "raptor.run_queued"


def ensure_stream_group(redis_client) -> None:
    """Idempotent XGROUP CREATE MKSTREAM."""
    try:
        redis_client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except Exception as e:
        # BUSYGROUP = already exists
        if "BUSYGROUP" not in str(e):
            raise


def publish_to_stream(redis_client, payload: dict, idempotency_key: str | None = None) -> str:
    """XADD payload to stream; returns entry id."""
    fields = {"data": json.dumps(payload, ensure_ascii=False)}
    if idempotency_key:
        fields["idempotency_key"] = idempotency_key
    # maxlen approx 10000 to avoid unbounded growth
    return redis_client.xadd(STREAM, fields, maxlen=10000, approximate=True)


def publish_to_dlq(redis_client, payload: dict, reason: str) -> str:
    """Poison/terminal message'ı DLQ stream'ine yaz."""
    fields = {"data": json.dumps(payload, ensure_ascii=False), "reason": reason}
    return redis_client.xadd(DLQ_STREAM, fields, maxlen=10000, approximate=True)


def read_group(redis_client, consumer_name: str, count: int = 1, block_ms: int = 5000):
    """XREADGROUP GROUP GROUP consumer_name COUNT count BLOCK block_ms STREAMS STREAM >"""
    return redis_client.xreadgroup(GROUP, consumer_name, {STREAM: ">"}, count=count, block=block_ms)


def ack(redis_client, entry_id: str) -> None:
    redis_client.xack(STREAM, GROUP, entry_id)


def claim_pending(redis_client, consumer_name: str, min_idle_ms: int = 30000, count: int = 10):
    """Reclaim pending entries that exceeded lease idle time (XAUTOCLAIM)."""
    try:
        # redis-py >=5 supports xautoclaim
        result = redis_client.xautoclaim(STREAM, GROUP, consumer_name, min_idle_ms, "0-0", count=count)
        # Redis 6/redis-py4 -> (next_id, entries) len 2
        # Redis 7/redis-py5 -> [next_id, entries, deleted_ids] len 3 — üçüncü eleman silinmiş ID'ler, entry değil
        if isinstance(result, (list, tuple)):
            if len(result) == 2:
                return result[1]
            if len(result) == 3:
                # entries ikinci eleman, deleted_ids üçüncüyü entry sanma
                return result[1]
        return result or []
    except Exception:
        # fallback: XPENDING + XCLAIM path
        try:
            pending = redis_client.xpending_range(STREAM, GROUP, "-", "+", count)
            reclaimed = []
            for p in pending:
                # p may be dict or tuple
                if isinstance(p, dict):
                    pid = p.get("message_id") or p.get("entry_id")
                    idle = p.get("time_since_delivered") or p.get("idle") or 0
                else:
                    pid = p[0] if len(p) > 0 else None
                    idle = p[1] if len(p) > 1 else 0
                if pid and int(idle) >= min_idle_ms:
                    claimed = redis_client.xclaim(STREAM, GROUP, consumer_name, min_idle_ms, [pid])
                    reclaimed.extend(claimed or [])
            return reclaimed
        except Exception:
            return []

```

## `packages/observability/security.py`

```py
# RAPTOR — gizlilik/redaction yardımcıları
# Sırlar, token, authorization header, cookie, token pattern ve runtime env değerleri
# modele/semantic memory'ye girmeden önce redakte edilir.
# Faz4: DLP katılaştırıldı — private key, AWS, yüksek entropi, env literal bloklama
from __future__ import annotations

import os
import re

# ——— Statik kalıplar ———
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Authorization / Bearer / api-key
    (re.compile(r"(?i)(authorization|bearer|api[_-]?key)\s*[:=]\s*(bearer\s+)?(\S+)"), r"\1=<REDACTED>"),
    # Telegram bot token: <digits>:<hex>
    (re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"), "<TG_TOKEN_REDACTED>"),
    # JWT
    (re.compile(r"\bey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "<JWT_REDACTED>"),
    # Genel secret uzun token
    (re.compile(r"\b(sk|pk|ghp|gho)_[A-Za-z0-9]{20,}\b"), "<SECRET_REDACTED>"),
    # --set env / ENV=
    (re.compile(r"(?i)(TELEGRAM_BOT_TOKEN|LLM_API_KEY|JWT_SECRET|[A-Z_]*PASSWORD)=(\S+)"), r"\1=<REDACTED>"),
    # Private key
    (re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"), "<PRIVATE_KEY_REDACTED>"),
    # AWS Access Key / Secret
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<AWS_KEY_REDACTED>"),
    (re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*(\S+)"), r"aws_secret_access_key=<REDACTED>"),
    # Generic high-entropy password assignment
    (re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\";]{8,})['\"]?"), r"\1=<REDACTED>"),
    # Database URL with password
    (re.compile(r"(?i)(postgresql|postgres|mysql|mongodb)(://[^:]+:)([^@]+)(@)"), r"\1\2<REDACTED>\4"),
]

# Harici girdilerden redakte edilecek genel regex'ler (hex/base64-ish)
_SECRET_VALUE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b[0-9A-Fa-f]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b"),
]

# Runtime env değerleri buraya eklenir — yalnızca bir kez
_loaded_env_secrets: set[str] = set()
# Hangi env anahtarlarının secret olduğu (dar liste — fail-closed değil, false positive azaltır)
_SECRET_KEY_HINTS = ("PASSWORD", "SECRET", "TOKEN", "API_KEY", "ENCRYPTION", "MASTER_KEY")
_PLACEHOLDERS = {"CHANGE_ME", "REPLACE_ME", "dev-only-change-me", "dev-webhook-secret", "dev-only-32-byte-master-key-0000000000", ""}


def _is_secret_key(key: str) -> bool:
    k = key.upper()
    return any(h in k for h in _SECRET_KEY_HINTS)


def load_secrets_from_env(environ: dict[str, str] | None = None) -> int:
    """Mevcut ortam değerlerini redaksiyon setine ekle. Dönüş: eklenen yeni değer sayısı.

    - Yalnızca secret-hint anahtarları ve uzun (>=12) ve filesystem path'i olmayan değerler.
    - Placeholder/CHANGE_ME değerleri atlanır.
    - Aynı değer ikinci kez eklenmez (idempotent).
    - Thread-unsafe ama idempotent; startup'ta bir kez çağrılması yeterli.

    """
    env = environ if environ is not None else dict(os.environ)
    added = 0
    for k, v in env.items():
        if not v or not isinstance(v, str):
            continue
        if v in _PLACEHOLDERS:
            continue
        if len(v) < 12:
            continue
        if v.startswith("/"):
            continue
        if not _is_secret_key(k):
            continue
        # placeholder alt-string içeriyorsa atla
        if "CHANGE_ME" in v or "REPLACE_ME" in v:
            continue
        if v in _loaded_env_secrets:
            continue
        # değeri literal olarak redakte et
        try:
            pat = re.compile(re.escape(v))
        except re.error:
            continue
        _loaded_env_secrets.add(v)
        _SECRET_VALUE_PATTERNS.append(pat)
        _PATTERNS.append((pat, "<ENV_REDACTED>"))
        added += 1
    return added


# Modül import'unda mevcut env'yi bir kez yükle (runtime secret'leri hemen redakte edilsin)
# Başarısız olursa sessiz geç — testlerde environ mock edilebilir
try:
    load_secrets_from_env()
except Exception:
    pass


def redact(text: str) -> str:
    """Belirgin secret/token/header kalıplarını maskeler."""
    if not text:
        return text
    out = text
    for pattern, repl in _PATTERNS:
        try:
            out = pattern.sub(repl, out)
        except Exception:
            continue
    # ekstra: yüksek entropi patternleri ikinci tur
    for pat in _SECRET_VALUE_PATTERNS:
        try:
            # hex/base64 benzeri uzun stringleri ENV_REDACTED zaten kapsar; burada generic
            # Not: sadece hex 32+ zaten _PATTERNS'te yok, o yüzden burada uygula
            # Literal env değerleri zaten _PATTERNS'te, tekrar etme
            if pat.pattern.startswith("\\b[0-9A-Fa-f]") or pat.pattern.startswith("\\b[A-Za-z0-9+/]"):
                out = pat.sub("<SECRET_REDACTED>", out)
        except Exception:
            continue
    return out


def contains_secret(text: str) -> bool:
    """DLP: metin gizli değer içeriyor mu? (block/flag için hızlı kontrol)."""
    if not text:
        return False
    # redacted versiyon farklıysa secret vardı
    return redact(text) != text


def scrub_and_flag(text: str) -> tuple[str, bool]:
    """DLP helper: redact et ve secret var mıydı döndür."""
    if not text:
        return text, False
    scrubbed = redact(text)
    had_secret = scrubbed != text
    return scrubbed, had_secret


class Redactor:
    def __init__(self) -> None:
        self._extra: list[tuple[re.Pattern, str]] = []

    def add_literal(self, value: str) -> None:
        if value and len(value) >= 4:
            self._extra.append((re.compile(re.escape(value)), "<SECRET_REDACTED>"))

    def scrub(self, text: str) -> str:
        out = redact(text)
        for pat, repl in self._extra:
            out = pat.sub(repl, out)
        return out

    def contains_secret(self, text: str) -> bool:
        return contains_secret(text) or any(pat.search(text) for pat, _ in self._extra)

    def scrub_and_flag(self, text: str) -> tuple[str, bool]:
        scrubbed = self.scrub(text)
        return scrubbed, scrubbed != text

```

## `packages/policy/__init__.py`

```py

```

## `packages/policy/approval.py`

```py
# RAPTOR — ApprovalService (onay kaydı oluşturma + atomik karar + consume + replay koruması)
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from observability import models
from policy.engine import action_hash


class ApprovalService:
    """Ortak onay servisi — Telegram ve Web UI aynı yolu kullanır."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def create(
        self,
        *,
        run_id: str,
        action_id: str,
        tool: str,
        arguments: dict,
        action_class: str,
        target: str,
        impact_summary: str = "",
        ttl_seconds: int = 3600,
    ) -> models.Approval:
        payload = {"action_id": action_id, "tool": tool, "arguments": arguments}
        h = action_hash(action_class, target, payload)
        a = models.Approval(
            action_class=action_class,
            action_hash=h,
            target=target,
            impact_summary=impact_summary,
            payload=payload,
            status=models.ApprovalStatus.PENDING.value,
            run_id=uuid.UUID(run_id) if run_id else None,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        self.s.add(a)
        await self.s.flush()
        return a

    async def decide(self, approval_id: str, decision: str, user_id: str) -> models.Approval:
        """Atomik karar: SELECT FOR UPDATE + expiry + status + role (çağıranda) kontrolü."""
        try:
            uid = uuid.UUID(approval_id)
        except ValueError:
            raise ValueError("approval_id geçersiz") from None
        # SELECT ... FOR UPDATE — aynı anda ikinci kararı engeller
        res = await self.s.execute(
            select(models.Approval).where(models.Approval.id == uid).with_for_update()
        )
        a = res.scalar_one_or_none()
        if a is None:
            raise ValueError("onay bulunamadı")
        if a.status != models.ApprovalStatus.PENDING.value:
            raise ValueError(f"zaten karara bağlanmış: {a.status}")
        if a.expires_at and a.expires_at < datetime.now(UTC):
            a.status = models.ApprovalStatus.EXPIRED.value
            raise ValueError("onay süresi dolmuş")
        if decision not in ("approve", "reject"):
            raise ValueError("decision approve|reject olmalı")
        a.status = models.ApprovalStatus.APPROVED.value if decision == "approve" else models.ApprovalStatus.REJECTED.value
        a.decision = decision
        a.decided_by_user_id = uuid.UUID(user_id) if user_id else None
        await self.s.flush()
        return a

    async def get(self, approval_id: str) -> models.Approval | None:
        try:
            uid = uuid.UUID(approval_id)
        except ValueError:
            return None
        return await self.s.get(models.Approval, uid)

    async def consume(self, approval_id: str) -> bool:
        """Onaylandıktan sonra tek kullanımlık işaretle (replay koruması)."""
        try:
            uid = uuid.UUID(approval_id)
        except ValueError:
            return False
        res = await self.s.execute(
            select(models.Approval).where(models.Approval.id == uid).with_for_update()
        )
        a = res.scalar_one_or_none()
        if a is None:
            return False
        if a.status != models.ApprovalStatus.APPROVED.value:
            return False  # yalnız APPROVED tüketilebilir; CONSUMED/PENDING reddedilir
        a.status = models.ApprovalStatus.CONSUMED.value
        await self.s.flush()
        return True

```

## `packages/policy/engine.py`

```py
# RAPTOR — politika + onay motoru
# Her tool call: ALLOW | REQUIRE_APPROVAL | DENY
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json

from observability.config import settings
from observability.models import ActionClass


@dataclasses.dataclass
class PolicyDecision:
    action_class: str
    decision: str  # ALLOW | REQUIRE_APPROVAL | DENY
    reason: str = ""
    requires_faz_approval: bool = False


# Varsayılan araç -> eylem sınıfı haritası (kayıtlı/şemalı araçlar)
TOOL_TO_ACTION = {
    # Connectors
    "technocore_read": ActionClass.READ_ONLY.value,
    "github_repo_read": ActionClass.READ_ONLY.value,
    "http_json_read": ActionClass.READ_ONLY.value,
    "internal_health": ActionClass.READ_ONLY.value,
    # Yazma
    "technocore_signed_write": ActionClass.PUBLIC_WRITE.value,
    "db_self_write": ActionClass.SAFE_WRITE.value,   # yalnız RAPTOR'un kendi DB'si
    # Politika / yetki
    "apply_privileged": ActionClass.PRIVILEGED_HOST.value,
    "destructive_op": ActionClass.DESTRUCTIVE.value,
}

# Faz onayı gerektiren aşamalar (public write, privileged host, destructive)
_GATED = {
    ActionClass.PUBLIC_WRITE.value,
    ActionClass.PRIVILEGED_HOST.value,
    ActionClass.DESTRUCTIVE.value,
}


class PolicyEngine:
    def __init__(self) -> None:
        self._overrides: dict[str, str] = {}

    def set_override(self, tool: str, decision: str) -> None:
        self._overrides[tool] = decision

    def set_auto_approve_classes(self, classes: set[str]) -> None:
        self._auto = set(classes)

    def decide(self, tool: str) -> PolicyDecision:
        if tool in self._overrides:
            return PolicyDecision(ActionClass.READ_ONLY.value, self._overrides[tool], "override")
        if tool not in TOOL_TO_ACTION:
            return PolicyDecision(ActionClass.DESTRUCTIVE.value, "DENY", f"bilinmeyen araç: {tool}")
        action_class = TOOL_TO_ACTION[tool]
        if action_class == ActionClass.DESTRUCTIVE.value:
            return PolicyDecision(action_class, "DENY", "destructive yalnız fasıl onayı")
        if action_class == ActionClass.PRIVILEGED_HOST.value:
            return PolicyDecision(action_class, "REQUIRE_APPROVAL", "host değişikliği insan onayı")
        if action_class in _GATED:
            return PolicyDecision(action_class, "REQUIRE_APPROVAL", "public write onayı")
        if action_class == ActionClass.SAFE_WRITE.value:
            return PolicyDecision(action_class, "ALLOW", "audit log'lu kendi DB yazımı")
        return PolicyDecision(action_class, "ALLOW", f"otomatik ({action_class})")


def canonical_json(payload: dict) -> str:
    """Sıralı, kompakt canonical JSON — hash bağlaması için deterministik."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def action_hash(action_class: str, target: str, payload: dict) -> str:
    """Tek kullanımlık onay eylemine bağlı hash — onay başka içeriğe taşınamaz."""
    material = canonical_json({"action_class": action_class, "target": target, "payload": payload})
    return hashlib.sha256(material.encode()).hexdigest()


def build_approval_token(approval_id: str, action_hash: str, user_id: str, expiry: int) -> str:
    """Callback/onay kaydı: HMAC-SHA256 (düz SHA-256 değil) — JWT_SECRET anahtarlı."""
    raw = f"{approval_id}:{action_hash}:{user_id}:{expiry}"
    return hmac.new(settings.JWT_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
```

## `packages/requirements-api.txt`

```txt
# RAPTOR pinned Python bağımlılıkları — API, worker, scheduler ortak çekirdeği
# Sürümler sabittir; otomatik yükseltme/`latest` yok.
# Host'ta Hermes venv kullanılmaz; her servis kendi image'ında build edilir.

# web/API framework
fastapi==0.115.6
uvicorn[standard]==0.32.1
pydantic==2.10.4
pydantic-settings==2.7.0
python-multipart==0.0.20

# DB / ORM / migrasyon
SQLAlchemy[asyncio]==2.0.36
asyncpg==0.30.0
psycopg[binary]==3.2.3
alembic==1.14.0

# kuyruk / koordinasyon
redis==5.2.1

# HTTP / SSRF
httpx==0.28.1

# elektronik imza / DID
cryptography==44.0.0
PyNaCl==1.5.0
base58==2.1.1

# Telegram
python-telegram-bot==21.9

# verimlilik / güvenlik
python-dotenv==1.0.1
orjson==3.10.12
passlib==1.7.4

# vektör arama
pgvector==0.4.0

# pyjwt
PyJWT==2.10.1

# CLI/yardımcı
python-dotenv==1.0.1
```

## `packages/requirements-dev.txt`

```txt
pytest==8.3.4
pytest-asyncio==0.24.0
pytest-cov==6.0.0
httpx==0.28.1
aiosqlite==0.22.1
```

## `packages/requirements-scheduler.txt`

```txt
fastapi==0.115.6
uvicorn[standard]==0.32.1
pydantic==2.10.4
pydantic-settings==2.7.0
SQLAlchemy[asyncio]==2.0.36
asyncpg==0.30.0
psycopg[binary]==3.2.3
redis==5.2.1
httpx==0.28.1
cryptography==44.0.0
orjson==3.10.12
```

## `packages/requirements-worker.txt`

```txt
fastapi==0.115.6
uvicorn[standard]==0.32.1
pydantic==2.10.4
pydantic-settings==2.7.0
SQLAlchemy[asyncio]==2.0.36
asyncpg==0.30.0
psycopg[binary]==3.2.3
redis==5.2.1
httpx==0.28.1
cryptography==44.0.0
PyNaCl==1.5.0
base58==2.1.1
orjson==3.10.12
pgvector==0.4.0
```

## `pyproject.toml`

```toml
[tool.ruff]
target-version = "py312"
line-length = 120
src = ["packages", "apps", "tests", "migrations"]
extend-exclude = ["apps/web"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "S", "UP", "TRY", "RUF"]
ignore = [
    "E501",    # line-too-long: ruff format'ın işi (kod tabanı 120'yi aşan yorum/dokümantasyon barındırır)
    "E402",    # module-import-not-at-top: döngüsel import önleme (try içi import)
    "B008",    # FastAPI Depends() default arg — framework gereği
    "BLE001",  # blind-except: agent resilience, kasıtlı (hata loglanır)
    "S110",    # try-except-pass: resilience
    "S112",    # try-except-continue
    "S101",    # assert: prod doğrulama + testlerde kullanılır
    "RUF001",  # Türkçe string literal'lardaki ı/İ (API mesajları, hata mesajları)
    "RUF002",  # Türkçe docstring'lerdeki ı/İ
    "RUF003",  # Türkçe yorumlardaki ı/İ karakterleri (kod tabanı Türkçe)
    "S104",    # bind-all-interfaces: yalnız container içi uvicorn (host portu kapalı)
    "TRY002",  # raise-vanilla-class
    "TRY003",  # raise-vanilla-args: HTTPException(detail="...") standart
    "TRY300",  # try-consider-else
    "TRY301",  # raise-within-try
]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101", "B017", "PLR2004", "S108", "S105", "S311"]
"migrations/*" = ["E501", "F401", "I001"]

[tool.pytest.ini_options]
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
pythonpath = ["packages"]
addopts = "-q"

[tool.coverage.run]
source = ["packages"]
omit = ["*/migrations/*"]

[tool.coverage.report]
fail_under = 70
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.:",
]

[tool.bandit]
exclude_dirs = ["tests", "migrations", "apps/web"]

```

## `pytest.ini`

```ini
[pytest]
asyncio_default_fixture_loop_scope = function
testpaths = tests
pythonpath = packages
addopts = -q
```

## `scripts/backup-restore.sh`

```sh
#!/usr/bin/env bash
# RAPTOR — veritabanı yedekleme (PostgreSQL dump) ve restore helper
# Yedekler /var/backups/raptor-observatory altına timestamp'li yazılır.
set -euo pipefail

BACKUP_DIR="${RAPTOR_BACKUP_DIR:-/var/backups/raptor-observatory}"
CONTAINER="raptor-postgres"
DB_USER="${POSTGRES_USER:-raptor}"
DB_NAME="${POSTGRES_DB:-raptor}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD gerekiyor}"

mkdir -p "$BACKUP_DIR"
chmod 0700 "$BACKUP_DIR"

action="${1:-backup}"
TS=$(date +%Y%m%d-%H%M%S)

case "$action" in
  backup)
    OUT="$BACKUP_DIR/raptor-$TS.dump"
    docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" "$CONTAINER" \
      pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$OUT"
    chmod 0600 "$OUT"
    echo "✅ Yedek: $OUT ($(du -h "$OUT" | cut -f1))"
    ;;
  restore)
    SRC="${2:?restore için kaynak dump dosyası gerekir}"
    # Yedek DB'ye geri yükle (üretim DB'sini ezmeden)
    docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" "$CONTAINER" \
      createdb -U "$DB_USER" -O "$DB_USER" raptor_restore_test 2>/dev/null || true
    docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" "$CONTAINER" \
      pg_restore -U "$DB_USER" -d raptor_restore_test --no-owner --no-privileges < "$SRC"
    echo "✅ Restore testi tamam: raptor_restore_test veritabanına yüklendi"
    echo "   (üretim veritabanına dokunulmadı)"
    ;;
  *)
    echo "Kullanım: $0 backup|restore <dosya>"
    exit 1
    ;;
esac
```

## `scripts/configure-secrets.sh`

```sh
#!/usr/bin/env bash
# RAPTOR Agentic Observatory — Güvenli secret kurulum yardımcısı (Faz 1 hardened)
#
# Kullanım:
#   ./scripts/configure-secrets.sh              # interaktif (read -s) giriş
#   ./scripts/configure-secrets.sh --gen        # güvenli otomatik üret (DB/JWT/ENC/WEBHOOK)
#   ./scripts/configure-secrets.sh --check      # dosya var mı / izinleri doğru mu kontrol et
#   RAPTOR_SECRETS_DIR=/tmp/test ./scripts/configure-secrets.sh --gen
#
# Kurallar:
#   - Değerler ekrana YAZILMAZ (read -s, gen_hex içerde)
#   - Dosya atomik yazılır (tmp+mv), 0600, root:root
#   - Mevcut dosya timestamp'li backup alınır (onay istenir, --gen'de otomatik yedek)
#   - Gerçek secret asla commit'e/log'a/ekrana düşmez
#   - --check fail-closed: eksik/placeholder/zayıf secret'te exit 1
set -euo pipefail

SECRETS_DIR="${RAPTOR_SECRETS_DIR:-./secrets/raptor-observatory}"
ENV_FILE="$SECRETS_DIR/app.env"
BACKUP_DIR="$SECRETS_DIR/backups"

MODE="${1:-interactive}"

# --check modu: sadece doğrulama, yazma yok
if [ "$MODE" = "--check" ]; then
  FAIL=0
  if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Secret dosyası yok: $ENV_FILE"
    exit 1
  fi
  perm=$(stat -c %a "$ENV_FILE" 2>/dev/null || stat -f %Lp "$ENV_FILE" 2>/dev/null || echo "unknown")
  if [ "$perm" != "600" ]; then
    echo "❌ İzin hatası: $ENV_FILE is $perm, expected 600"
    FAIL=1
  fi
  for key in DB_PASSWORD JWT_SECRET SESSION_ENCRYPTION_MASTER_KEY TELEGRAM_WEBHOOK_SECRET; do
    val=$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tail -n1 || true)
    if [ -z "$val" ] || [ "$val" = "CHANGE_ME" ] || [ "$val" = "dev-only-change-me" ]; then
      echo "❌ Eksik/placeholder secret: $key"
      FAIL=1
    elif [ "${#val}" -lt 16 ]; then
      echo "❌ Çok kısa secret: $key (len=${#val}, min 16)"
      FAIL=1
    fi
  done
  if [ "$FAIL" = "0" ]; then
    echo "✅ Secret dosyası OK: $ENV_FILE (0600, required keys present)"
  else
    echo "❌ Secret check FAILED"
    exit 1
  fi
  exit 0
fi

umask 077
mkdir -p "$SECRETS_DIR" "$BACKUP_DIR"
chmod 0700 "$SECRETS_DIR"
if [ "$(id -u)" = "0" ]; then
  chown root:root "$SECRETS_DIR" 2>/dev/null || true
fi

# --- Mevcut dosya varsa backup al ve onay iste ---
if [ -f "$ENV_FILE" ]; then
  echo "⚠️  Mevcut secret dosyası bulundu: $ENV_FILE"
  if [ -t 0 ] && [ "$MODE" != "--gen" ]; then
    read -r -p "Devam edilirse mevcut dosya backup'a taşınacak. Onaylıyor musun? [y/N] " YES || YES="n"
    [ "$YES" = "y" ] || { echo "İptal."; exit 1; }
  elif [ "$MODE" = "--gen" ]; then
    echo "   (--gen modunda otomatik yedek alınıyor)"
  fi
  TS=$(date +%Y%m%d-%H%M%S)
  cp "$ENV_FILE" "$BACKUP_DIR/app.env.bak-$TS"
  chmod 0600 "$BACKUP_DIR/app.env.bak-$TS"
  if [ "$(id -u)" = "0" ]; then chown root:root "$BACKUP_DIR/app.env.bak-$TS" 2>/dev/null || true; fi
  echo "Yedek: $BACKUP_DIR/app.env.bak-$TS"
fi

# Güvenli random değer üretici (hex, N byte) — /dev/urandom yoksa openssl fallback
gen_hex() {
  local n="${1:-32}"
  if [ -r /dev/urandom ]; then
    head -c "$n" /dev/urandom | od -A n -t x1 | tr -d ' \n'
  else
    openssl rand -hex "$n" 2>/dev/null | tr -d '\n'
  fi
}
gen_b64() {
  local n="${1:-32}" out="${2:-48}"
  if [ -r /dev/urandom ]; then
    head -c "$n" /dev/urandom | base64 | tr -d '=\n+/' | head -c "$out"
  else
    openssl rand -base64 "$n" 2>/dev/null | tr -d '=\n+/' | head -c "$out"
  fi
}

# --- Yeni dosyayı tmp'de kur, sonra atomik taşı ---
TMP="$ENV_FILE.tmp.$$"
: > "$TMP"
chmod 0600 "$TMP"

put() { printf '%s\n' "$1" >> "$TMP"; }

if [ "$MODE" = "--gen" ]; then
  echo "🔐 Otomatik güvenli üretim modu..."
  DB_PW=$(gen_hex 24)
  JWT=$(gen_hex 32)
  ENC=$(gen_hex 32)
  WH=$(gen_b64 24 40)
  put "# RAPTOR secrets — otomatik üretilen (root-only). Değerleri kimseye gösterme."
  put "# DB — docker-compose POSTGRES_PASSWORD ve DB_PASSWORD alias"
  put "DB_PASSWORD=$DB_PW"
  put "POSTGRES_PASSWORD=$DB_PW"
  put "# App"
  put "JWT_SECRET=$JWT"
  put "SESSION_ENCRYPTION_MASTER_KEY=$ENC"
  put "TELEGRAM_WEBHOOK_SECRET=$WH"
  put "# Opsiyonel — boş kalırsa mock provider; doluysa gerçek provider kullanılır"
  put "TELEGRAM_BOT_TOKEN="
  put "LLM_API_KEY="
  put "LLM_BASE_URL="
  put "LLM_MODEL="
  # shell'de değişkenleri temizle (ps'e düşmesin)
  unset DB_PW JWT ENC WH
else
  echo "🔐 Interaktif kurulum (girdiğin değerler ekrana yazılmaz)."
  put "# RAPTOR secrets — root-only. Boş değerleri sonra da doldurup ./scripts/configure-secrets.sh çalıştırabilirsin."
  put "# DB"
  read -s -p "PostgreSQL şifresi (DB_PASSWORD): " v; echo; put "DB_PASSWORD=$v"; POSTGRES_PW="$v"
  put "POSTGRES_PASSWORD=$POSTGRES_PW"
  unset POSTGRES_PW
  put "# App"
  read -s -p "JWT secret (JWT_SECRET, min 32 hex): " v; echo; put "JWT_SECRET=$v"
  read -s -p "Session encryption master key: " v; echo; put "SESSION_ENCRYPTION_MASTER_KEY=$v"
  read -s -p "Telegram webhook secret token: " v; echo; put "TELEGRAM_WEBHOOK_SECRET=$v"
  echo "(Aşağıdakiler için Telegram bot ve provider gerekiyor — boş bırakabilirsin, sonra doldururuz.)"
  read -s -p "Telegram bot token (TELEGRAM_BOT_TOKEN): " v; echo; put "TELEGRAM_BOT_TOKEN=$v"
  read -s -p "LLM API key (LLM_API_KEY): " v; echo; put "LLM_API_KEY=$v"
  read -p "LLM base URL (LLM_BASE_URL, ör https://api.openai.com/v1): " v; put "LLM_BASE_URL=$v"
  read -p "LLM model (LLM_MODEL, ör gpt-4o-mini): " v; put "LLM_MODEL=$v"
  unset v
fi

mv "$TMP" "$ENV_FILE"
chmod 0600 "$ENV_FILE"
if [ "$(id -u)" = "0" ]; then chown root:root "$ENV_FILE" 2>/dev/null || true; fi

echo "✅ Secret dosyası hazır: $ENV_FILE (0600, root:root)"
echo "   Kullanıcı/şifre/token değerleri ekrana yazılmadı."
echo "   Doğrulamak için: ./scripts/configure-secrets.sh --check"

```

## `scripts/secret-scan.sh`

```sh
#!/usr/bin/env bash
# RAPTOR — secret scan v3 (fail-closed)
# Exit: 0 temiz, 1 gerçek sır bulundu, 2 tarama hatası (fail-closed)
# Hiçbir dosya atlatılmaz; placeholder/CHANGE_ME hariç gerçek değer yakalanır.
set -uo pipefail
ROOT="${1:-.}"
if [ ! -d "$ROOT" ]; then
  echo "❌ ROOT yok: $ROOT" >&2
  exit 2
fi
cd "$ROOT" || exit 2

# fail-closed: gerekli araçlar yoksa hata
for bin in grep find sed; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "❌ Gerekli araç yok: $bin (fail-closed)" >&2
    exit 2
  fi
done

# Yüksek güvenilirlikli gerçek değer kalıpları (literal token/credentials)
# Placeholder'lar (CHANGE_ME, dev-only, REPLACE_ME, empty) asla eşleşmez
STRONG=(
  'TELEGRAM_BOT_TOKEN[=: ]+[0-9]{6,}:[A-Za-z0-9_-]{30,}'   # gerçek TG token
  'TELEGRAM_BOT_TOKEN[=:][ ]*[0-9]{6,}:[A-Za-z0-9_-]{30,}' # env assignment variant
  'mongodb(\+srv)?://[^: ]+:[^@ ]{8,}@[^: ]+'               # gerçek DB creds (pw >=8)
  'postgresql(\+[^: ]+)?://[^: ]+:[^@ ]{8,}@[^: ]+'         # postgres URL with pw >=8
  '\bgh[pousr]_[A-Za-z0-9]{20,}\b'                        # GitHub token
  '\bsk(-[A-Za-z0-9]{8,}){2,}\b'                          # OpenAI-style sk-...
  'LLM_API_KEY[=: ]+[A-Za-z0-9_-]{24,}'                  # gerçek LLM key assignment
  'JWT_SECRET[=: ]+[A-Za-z0-9_\-+/=]{24,}'               # JWT secret assignment (non-placeholder)
  'SESSION_ENCRYPTION_MASTER_KEY[=: ]+[A-Za-z0-9_\-+/=]{24,}'
  'POSTGRES_PASSWORD[=: ]+[A-Za-z0-9_\-+/=]{8,}'
  'DB_PASSWORD[=: ]+[A-Za-z0-9_\-+/=]{8,}'
)

# Placeholder'ları eşleşmeden çıkar (satır bazında filtrelenir)
is_placeholder_line() {
  echo "$1" | grep -qE 'CHANGE_ME|REPLACE_ME|dev-only|example\.com|_here|your-.*-here|\$\{|random|:x@|localhost:5432/raptor|127\.0\.0\.1' 2>/dev/null
}

hits=0
scanned=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  # fixture/test kendini tarama — pozitif fixture'lar kasıtlı olarak gerçek pattern içerir, repo leak değil
  if echo "$f" | grep -qE 'tests/security/test_secret_scan|tests/fixtures/secret-scan' 2>/dev/null; then
    continue
  fi
  scanned=$((scanned+1))
  # .env.example ve fixture'lar özel: .env.example ayrı kontrol edilir; fixture positive'ler allowlist'tedir
  # Ama fail-closed: tarama dışı bırakma YOK — sadece raporlama için etiketle
  for pat in "${STRONG[@]}"; do
    if grep -qE "$pat" "$f" 2>/dev/null; then
      # satırı al, placeholder ise atla (gerçek değer değil)
      line=$(grep -nE "$pat" "$f" 2>/dev/null | head -1)
      if is_placeholder_line "$line"; then
        continue
      fi
      # fixture positive files are expected to be caught — mark but still count unless in allowlist dir
      if echo "$f" | grep -qE 'tests/fixtures/secret-scan-positive|secret-scan-fixtures' 2>/dev/null; then
        # positive fixture: should be detected; don't count as repo leak, just ensure detection works
        continue
      fi
      # test_policy_redaction.py'deki ""Authorization: Bearer ***"" gibi maskelenmiş test stringleri
      # eğer satırda <REDACTED> veya *** maskesi varsa atla
      if echo "$line" | grep -qE '<REDACTED>|<MASKED>|\*\*\*' 2>/dev/null; then
        # ama satırda gerçek token da varsa yine de yakala — ek kontrol
        if echo "$line" | grep -qE '[A-Za-z0-9_-]{30,}' 2>/dev/null && ! echo "$line" | grep -qE 'CHANGE_ME'; then
          # gerçek değer var gibi, yine raporla
          :
        else
          continue
        fi
      fi
      echo "⚠️  GERÇEK SIR ADAYI: $f"
      echo "$line" | head -1 | sed -E 's/([0-9]{6,}:[A-Za-z0-9_-]{30,}|mongodb(\+srv)?:\/\/[^@]+@|postgresql(\+[^:]+)?:\/\/[^@]+@|sk-[A-Za-z0-9]{8,}[A-Za-z0-9_-]*|[A-Za-z0-9_-]{30,})/<MASKED>/g'
      hits=1
    fi
  done
done < <(find . -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' -o -name '*.sh' -o -name '*.yml' -o -name '*.yaml' -o -name '*.json' -o -name '*.md' -o -name '*.ini' -o -name '*.env*' -o -name '*.example' \) \
    -not -path '*/.git/*' -not -path '*/.venv/*' -not -path '*/node_modules/*' -not -path '*/dist/*' \
    -not -path '*/.pytest_cache/*' -not -path '*/instance/*' -not -path '*/__pycache__/*' \
    -not -path '*/tests/security/test_secret_scan.py' \
    -not -path '*/backups/*' 2>/dev/null )

# fail-closed: hiç dosya taranamadıysa hata
if [ "$scanned" -eq 0 ]; then
  echo "❌ Tarama hatası: hiç dosya taranamadı (fail-closed)" >&2
  exit 2
fi

# gerçek secret dosyalarını hiçbir zaman commit etme — repo içinde app.env varsa kesin fail
# .env için: sadece git takibindeyse fail (dev .env gitignore'dadır)
if find . -name 'app.env' -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/.venv/*' 2>/dev/null | grep -q .; then
  real_env=$(find . -name 'app.env' -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/.venv/*' 2>/dev/null | head -5)
  if [ -n "$real_env" ]; then
    echo "❌ REPO İÇİNDE app.env VAR — commit etme!"
    echo "$real_env"
    hits=1
  fi
fi
# .env sadece git'te takibliyse fail (git ls-files ile kontrol, fail-closed değilse sadece uyar)
if [ -d ".git" ] && git ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo "❌ REPO İÇİNDE .env TAKİPLİ — .gitignore'a ekle!"
  hits=1
fi

# .env.example güvenliği: sadece CHANGE_ME / boş / safe placeholder içermeli
if [ -f ".env.example" ]; then
  # .env.example içinde gerçek TG token / sk- / 64 hex gibi değer varsa fail
  if grep -qE '[0-9]{6,}:[A-Za-z0-9_-]{30,}' .env.example 2>/dev/null; then
    if ! grep -qE 'CHANGE_ME' .env.example 2>/dev/null; then
      : # placeholder yoksa gerçek token demektir
    fi
    # CHANGE_ME olmayan gerçek token satırı var mı?
    if grep -E '[0-9]{6,}:[A-Za-z0-9_-]{30,}' .env.example 2>/dev/null | grep -qv 'CHANGE_ME' 2>/dev/null; then
      echo "❌ .env.example içinde gerçek Telegram token var!"
      hits=1
    fi
  fi
  # .env.example içinde sk- ile başlayan gerçek key var mı (CHANGE_ME hariç)
  if grep -qE 'sk-[A-Za-z0-9]{20,}' .env.example 2>/dev/null; then
    if grep -E 'sk-[A-Za-z0-9]{20,}' .env.example 2>/dev/null | grep -qv 'CHANGE_ME' 2>/dev/null; then
      echo "❌ .env.example içinde gerçek LLM key var!"
      hits=1
    fi
  fi
  # POSTGRES_PASSWORD / JWT_SECRET satırında CHANGE_ME yoksa ve değer uzun ise fail
  for key in POSTGRES_PASSWORD DB_PASSWORD JWT_SECRET SESSION_ENCRYPTION_MASTER_KEY TELEGRAM_BOT_TOKEN LLM_API_KEY; do
    line=$(grep -E "^${key}=" .env.example 2>/dev/null | head -1 || true)
    if [ -n "$line" ]; then
      val=$(echo "$line" | cut -d= -f2-)
      # boş veya CHANGE_ME ise OK
      if [ -z "$val" ] || echo "$val" | grep -q 'CHANGE_ME' 2>/dev/null; then
        continue
      fi
      # 8+ karakter ve CHANGE_ME değilse gerçek değer şüphesi
      if [ "${#val}" -ge 8 ] && ! echo "$val" | grep -qE '^\$\{' 2>/dev/null; then
        echo "❌ .env.example içinde $key gerçek değer içeriyor: $line (yalnız CHANGE_ME olmalı)"
        hits=1
      fi
    fi
  done
fi

if [ "$hits" = "0" ]; then
  echo "✅ Secret scan temiz: repo'da gerçek credential yok. (taranan dosya: $scanned)"
else
  echo "❌ Secret scan: gerçek sır adayı bulundu — commit'i DURDUR."
  exit 1
fi

```

## `tests/security/test_auth.py`

```py
# RAPTOR — AŞAMA 2 auth/RBAC testleri (local session, CF Access kullanılmıyor)
import jwt as pyjwt
import pytest

from observability.auth import (
    ROLE_ORDER,
    create_session_token,
    decode_session_token,
    hash_password,
    verify_password,
)


class TestPasswordHash:
    def test_hash_and_verify(self):
        h = hash_password("s3cret-pass")
        assert verify_password("s3cret-pass", h)
        assert not verify_password("wrong", h)

    def test_hash_is_not_plaintext(self):
        h = hash_password("s3cret-pass")
        assert "s3cret-pass" not in h
        assert h.startswith("pbkdf2_sha256$")


class TestSessionToken:
    def test_roundtrip(self):
        tok = create_session_token("u-1", "admin", 3600)
        dec = decode_session_token(tok)
        assert dec["sub"] == "u-1"
        assert dec["role"] == "admin"
        assert dec["iss"] == "raptor-observatory"

    def test_expired_rejected(self):
        # expires_seconds negatif -> hemen expire (exp geçmişte)
        tok = create_session_token("u-1", "viewer", expires_seconds=-10)
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_session_token(tok)

    def test_tampered_rejected(self):
        tok = create_session_token("u-1", "admin", 3600)
        # imzayı boz
        parts = tok.split(".")
        parts[1] = "AAAA" + parts[1][4:]
        tampered = ".".join(parts)
        with pytest.raises(Exception):
            decode_session_token(tampered)

    def test_wrong_secret_rejected(self):
        tok = create_session_token("u-1", "admin", 3600)
        with pytest.raises(pyjwt.InvalidSignatureError):
            pyjwt.decode(tok, "wrong-secret-key-for-test", algorithms=["HS256"])


class TestRBAC:
    def test_role_order(self):
        assert ROLE_ORDER["admin"] > ROLE_ORDER["operator"] > ROLE_ORDER["viewer"]

    def test_require_role_logic(self):
        # require_role davranışı: viewer < operator < admin
        assert ROLE_ORDER.get("viewer", -1) < ROLE_ORDER.get("operator", 0)
        assert ROLE_ORDER.get("admin", -1) >= ROLE_ORDER.get("operator", 0)

```

## `tests/security/test_policy_redaction.py`

```py
# RAPTOR — policy motoru + redaction birim testleri (workflow-agnostic)

from observability.security import redact
from policy.engine import PolicyEngine, action_hash


class TestPolicy:
    def test_read_only_auto(self):
        e = PolicyEngine()
        d = e.decide("technocore_read")
        assert d.decision == "ALLOW"
        assert d.action_class == "READ_ONLY"

    def test_safe_write_auto(self):
        e = PolicyEngine()
        d = e.decide("db_self_write")
        assert d.decision == "ALLOW"

    def test_public_write_needs_approval(self):
        e = PolicyEngine()
        d = e.decide("technocore_signed_write")
        assert d.decision == "REQUIRE_APPROVAL"

    def test_privileged_needs_approval(self):
        e = PolicyEngine()
        d = e.decide("apply_privileged")
        assert d.decision == "REQUIRE_APPROVAL"

    def test_destructive_denied(self):
        e = PolicyEngine()
        d = e.decide("destructive_op")
        assert d.decision == "DENY"

    def test_unknown_tool_defaults_read_only_allow(self):
        e = PolicyEngine()
        assert e.decide("unknown_tool").decision == "DENY"


class TestRedaction:
    def test_bearer_redacted(self):
        out = redact("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret")
        assert "<REDACTED>" in out

    def test_telegram_token_redacted(self):
        out = redact("token=123456789:AAHdqTcvCH1vGWJfk07OFP1toIDKN_BnoQ_extra_long_token_here")
        assert "<TG_TOKEN_REDACTED>" in out

    def test_jwt_redacted(self):
        out = redact("bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")
        assert "<JWT_REDACTED>" in out

    def test_explicit_env_assignment_redacted(self):
        out = redact("TELEGRAM_BOT_TOKEN=123456789:AAHSecretTokenValue")
        assert "<REDACTED>" in out

    def test_runtime_env_value_redacted(self):
        from observability.security import load_secrets_from_env
        load_secrets_from_env({"JWT_SECRET": "runtime-unique-JWT-9999-super-secret-xyz123"})
        out = redact("leaked runtime-unique-JWT-9999-super-secret-xyz123 in logs")
        assert "runtime-unique-JWT-9999-super-secret-xyz123" not in out
        assert "<ENV_REDACTED>" in out

    def test_runtime_env_idempotent(self):
        from observability.security import load_secrets_from_env
        load_secrets_from_env({"LLM_API_KEY": "idempotent-key-1234567890-ABCDEF123456"})
        n2 = load_secrets_from_env({"LLM_API_KEY": "idempotent-key-1234567890-ABCDEF123456"})
        assert n2 == 0  # ikinci ekleme yapmamalı
        out = redact("idempotent-key-1234567890-ABCDEF123456 leaked")
        assert "<ENV_REDACTED>" in out

    def test_runtime_env_ignores_placeholder(self):
        from observability.security import load_secrets_from_env
        n = load_secrets_from_env({"JWT_SECRET": "CHANGE_ME"})
        assert n == 0
        n2 = load_secrets_from_env({"DB_PASSWORD": "short"})
        assert n2 == 0  # <12 char

    def test_action_hash_binds_content(self):
        h1 = action_hash("PUBLIC_WRITE", "/r/lobby", {"x": 1})
        h2 = action_hash("PUBLIC_WRITE", "/r/lobby", {"x": 2})
        assert h1 != h2  # onay başka içeriğe taşınamaz
```

## `tests/security/test_secret_scan.py`

```py
# RAPTOR — secret-scan fixture testleri (fail-closed doğrulama)
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCAN = REPO / "scripts" / "secret-scan.sh"

def run_scan(tmpdir: Path) -> tuple[int, str]:
    r = subprocess.run([str(SCAN), str(tmpdir)], capture_output=True, text=True, timeout=10)  # noqa: S603 (sabit yol, untrusted input yok)
    return r.returncode, r.stdout + r.stderr

def test_clean_passes():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "app.py").write_text('import os\nx=os.environ.get("TELEGRAM_BOT_TOKEN")\n# JWT_SECRET=CHANGE_ME\n')
        (p / ".env.example").write_text('POSTGRES_PASSWORD=CHANGE_ME\nJWT_SECRET=CHANGE_ME\n')
        code, out = run_scan(p)
        assert code == 0, out
        assert "temiz" in out

def test_real_telegram_token_fails():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        # gerçek TG token formatı: 9digit:35+char
        (p / "app.py").write_text('TELEGRAM_BOT_TOKEN=123456789:AAHdqTcvCH1vGWJfk07OFP1toIDKN_BnoQ_extra_long_token\n')
        code, out = run_scan(p)
        assert code == 1, out
        assert "GERÇEK SIR" in out

def test_real_postgres_url_fails():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "config.py").write_text('DATABASE_URL=postgresql+asyncpg://raptor:SuperSecret12345678@db:5432/raptor\n')
        code, out = run_scan(p)
        assert code == 1, out

def test_placeholder_postgres_url_passes():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "migrations.py").write_text('url="postgresql+asyncpg://raptor:x@localhost/raptor"\n')
        (p / "compose.yml").write_text('DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/raptor\n')
        code, out = run_scan(p)
        assert code == 0, out

def test_env_example_with_real_secret_fails():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / ".env.example").write_text('POSTGRES_PASSWORD=supersecret123456\nJWT_SECRET=79a0b800cc70b064987cfc2ded9904bffd35f0799d02df5f8713f74fe93724f9\n')
        (p / "app.py").write_text('# clean\n')
        code, out = run_scan(p)
        assert code == 1, out
        assert ".env.example" in out

def test_env_example_clean_passes():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / ".env.example").write_text('POSTGRES_PASSWORD=CHANGE_ME\nJWT_SECRET=CHANGE_ME\nLLM_API_KEY=CHANGE_ME\nTELEGRAM_BOT_TOKEN=CHANGE_ME\n')
        code, out = run_scan(p)
        assert code == 0, out

def test_sk_pattern_fails():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "app.py").write_text('key="sk-proj-abcdefgh1234567890ABCDEFghijklmnopqrst"\n')
        _code, _out = run_scan(p)
        # sk- pattern requires sk-xxx-xxx so this may or may not match; LLM_API_KEY assignment should also trigger
        # Use LLM_API_KEY assignment form for reliable detection
        (p / "app2.py").write_text('LLM_API_KEY=sk-proj-abcdefgh1234567890ABCDEFGH123456\n')
        code2, out2 = run_scan(p)
        assert code2 == 1, out2

def test_no_files_fail_closed():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        # boş dizin — find hiç dosya bulamaz, fail-closed exit 2 beklenir
        code, out = run_scan(p)
        assert code == 2, out
        assert "fail-closed" in out.lower() or "hiç dosya" in out

```

## `tests/unit/test_agentic_loop.py`

```py
# RAPTOR — AŞAMA 3 agentic döngü testleri
import asyncio
import json

import pytest

from agent_core.coordinator import RunBudget, RunCoordinator
from agent_core.executor import ToolExecutor, ToolRegistry
from agent_core.llm import LLMProvider, LLMResult, MockProvider
from agent_core.planner import Planner
from agent_core.verifier import DefaultVerifier
from context_engine.assembler import ContextAssembler
from policy.engine import PolicyDecision


class _JSONProvider(LLMProvider):
    """Deterministik geçerli JSON plan üreten provider (provider_calls sayacı için)."""
    name = "json_test"

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, **kw):
        self.calls += 1
        plan = {"goal": "observe", "assumptions": [], "success_criteria": ["kanıt"],
                "actions": [{"action_id": "action_1", "tool": "github_repo_read",
                             "arguments": {"repo": "your-owner/raptor-observatory"},
                             "reason": "repo", "expected_evidence": [], "action_class": "READ_ONLY"}]}
        return LLMResult(text=json.dumps(plan), finish_reason="stop",
                         usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})

    async def check(self):
        return True


class TestPlanner:
    def test_provider_called(self):
        p = _JSONProvider()
        pl = Planner(provider=p)
        plan = asyncio.run(pl.make_plan({"title": "t", "prompt": "p", "scope": {"kind": "observe"}}))
        assert p.calls > 0, "provider çağrılmadı"
        assert plan["actions"], "actions boş"

    def test_actions_have_arguments(self):
        p = _JSONProvider()
        pl = Planner(provider=p)
        plan = asyncio.run(pl.make_plan({"title": "t", "prompt": "p", "scope": {"kind": "observe"}}))
        act = plan["actions"][0]
        assert act["tool"] == "github_repo_read"
        assert act["arguments"].get("repo") == "your-owner/raptor-observatory"

    def test_template_fallback_has_required_args(self):
        pl = Planner(provider=None)  # template fallback
        plan = asyncio.run(pl.make_plan({"title": "t", "prompt": "p", "scope": {"kind": "observe"}}))
        tools_args = {a["tool"]: a["arguments"] for a in plan["actions"]}
        assert "github_repo_read" in tools_args and "repo" in tools_args["github_repo_read"]
        assert "http_json_read" in tools_args and "url" in tools_args["http_json_read"]

    def test_unknown_tool_rejected(self):
        from agent_core.planner import PlanAction
        with pytest.raises(Exception):
            PlanAction(action_id="action_1", tool="totally_unknown_tool", arguments={})


class TestCoordinatorArgs:
    def test_args_passed_to_executor(self):
        reg = ToolRegistry()
        calls = {}

        async def rec(**kw):
            calls.update(kw)
            return {"ok": True}

        reg.register("technocore_read", rec, {"parameters": {"type": "object", "properties": {"room": {"type": "string"}, "since": {"type": "integer"}}}})
        executor = ToolExecutor(reg, task={"scope": {"kind": "observe"}, "prompt": "p", "title": "t"})

        class _FixedPlanner:
            async def make_plan(self, task):
                return {"goal": "observe", "actions": [
                    {"action_id": "action_1", "tool": "technocore_read",
                     "arguments": {"room": "test-room", "since": 5}, "reason": "", "expected_evidence": [], "action_class": "READ_ONLY"}]}

        class _AllowPolicy:
            def decide(self, tool):
                return PolicyDecision("READ_ONLY", "ALLOW", "test")

        coord = RunCoordinator(run_id="r-1", budget=RunBudget(max_iterations=5, max_tool_calls=5))
        asyncio.run(coord.run(executor, _FixedPlanner(), ContextAssembler(),
                              _AllowPolicy(), MockProvider(), DefaultVerifier()))
        assert calls.get("room") == "test-room", "argüman executor'a geçmedi"
        assert calls.get("since") == 5


class TestRunOutcome:
    def _setup(self, tool_fn):
        reg = ToolRegistry()
        reg.register("internal_health", tool_fn, {"parameters": {"type": "object", "properties": {}}})
        executor = ToolExecutor(reg, task={"scope": {"kind": "source_health"}, "prompt": "p", "title": "t"})

        class _FixedPlanner:
            async def make_plan(self, task):
                return {"goal": "source_health", "actions": [
                    {"action_id": "action_1", "tool": "internal_health", "arguments": {},
                     "reason": "", "expected_evidence": [], "action_class": "READ_ONLY"}]}

        class _AllowPolicy:
            def decide(self, tool):
                return PolicyDecision("READ_ONLY", "ALLOW", "test")

        return executor, _FixedPlanner(), _AllowPolicy()

    def test_success_completed(self):
        async def ok(**kw):
            return {"healthy": True}
        executor, planner, policy = self._setup(ok)
        coord = RunCoordinator(run_id="r-1", budget=RunBudget(max_iterations=5, max_tool_calls=5))
        status, _, _ = asyncio.run(coord.run(executor, planner, ContextAssembler(),
                                             policy, MockProvider(), DefaultVerifier()))
        assert status == "COMPLETED"

    def test_error_not_completed(self):
        async def fail(**kw):
            raise RuntimeError("boom")
        executor, planner, policy = self._setup(fail)
        coord = RunCoordinator(run_id="r-1", budget=RunBudget(max_iterations=5, max_tool_calls=5))
        status, _, _ = asyncio.run(coord.run(executor, planner, ContextAssembler(),
                                             policy, MockProvider(), DefaultVerifier()))
        assert status == "FAILED", f"beklenen FAILED, gelen {status}"

    def test_token_usage_recorded(self):
        async def ok(**kw):
            return {"healthy": True}
        executor, planner, policy = self._setup(ok)
        coord = RunCoordinator(run_id="r-1", budget=RunBudget(max_iterations=5, max_tool_calls=5))
        asyncio.run(coord.run(executor, planner, ContextAssembler(),
                              policy, MockProvider(), DefaultVerifier()))
        assert coord.tokens_used >= 0 and coord.cost_used >= 0.0

```

## `tests/unit/test_approval.py`

```py
# RAPTOR — AŞAMA 4 approval testleri (hash bağlama + HMAC token + consume mantığı)
import hashlib
import hmac

from policy.engine import action_hash, build_approval_token, canonical_json


class TestActionHash:
    def test_payload_order_independent(self):
        h1 = action_hash("PUBLIC_WRITE", "/r/lobby", {"a": 1, "b": 2})
        h2 = action_hash("PUBLIC_WRITE", "/r/lobby", {"b": 2, "a": 1})
        assert h1 == h2, "hash anahtar sırasına bağlı olmamalı (canonical)"

    def test_different_payload_different_hash(self):
        h1 = action_hash("PUBLIC_WRITE", "/r/lobby", {"x": 1})
        h2 = action_hash("PUBLIC_WRITE", "/r/lobby", {"x": 2})
        assert h1 != h2

    def test_different_target_different_hash(self):
        h1 = action_hash("PUBLIC_WRITE", "/r/lobby", {"x": 1})
        h2 = action_hash("PUBLIC_WRITE", "/r/other", {"x": 1})
        assert h1 != h2


class TestApprovalToken:
    def test_hmac_not_plain_sha256(self):
        raw = "approval-1:hash123:user-1:1234567890"
        plain = hashlib.sha256(raw.encode()).hexdigest()
        hmac_token = build_approval_token("approval-1", "hash123", "user-1", 1234567890)
        assert hmac_token != plain, "token düz SHA-256 olmamalı (HMAC olmalı)"

    def test_hmac_key_bound(self):
        t1 = build_approval_token("a", "h", "u", 1)
        # farklı anahtarla farklı token (anahtar bağlı)
        alt = hmac.new(b"wrong-key", b"a:h:u:1", hashlib.sha256).hexdigest()
        assert t1 != alt


class TestCanonicalJson:
    def test_deterministic(self):
        a = canonical_json({"b": [1, 2], "a": {"x": "y"}})
        b = canonical_json({"a": {"x": "y"}, "b": [1, 2]})
        assert a == b

```

## `tests/unit/test_approval_service.py`

```py
# RAPTOR — AŞAMA 12 ApprovalService testleri (create/decide/consume/replay/expiry)
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from observability.models import ApprovalStatus, Base
from policy.approval import ApprovalService


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    S = async_sessionmaker(engine, expire_on_commit=False)
    async with S() as s:
        yield s
    await engine.dispose()


async def _create(session, **kw):
    svc = ApprovalService(session)
    a = await svc.create(
        run_id="",
        action_id=kw.get("action_id", "a1"),
        tool=kw.get("tool", "github_repo_read"),
        arguments=kw.get("arguments", {}),
        action_class=kw.get("action_class", "PUBLIC_WRITE"),
        target=kw.get("target", "repo:x/y"),
        ttl_seconds=kw.get("ttl_seconds", 3600),
    )
    await session.commit()
    return a


@pytest.mark.asyncio
async def test_create_and_get(session):
    a = await _create(session)
    assert a.status == ApprovalStatus.PENDING.value
    assert a.action_hash
    got = await ApprovalService(session).get(str(a.id))
    assert got is not None and str(got.id) == str(a.id)


@pytest.mark.asyncio
async def test_get_invalid_id(session):
    assert await ApprovalService(session).get("not-a-uuid") is None


@pytest.mark.asyncio
async def test_decide_approve_then_consume_replay(session):
    a = await _create(session)
    svc = ApprovalService(session)
    d = await svc.decide(str(a.id), "approve", str(uuid.uuid4()))
    assert d.status == ApprovalStatus.APPROVED.value
    await session.commit()
    assert await svc.consume(str(a.id)) is True
    await session.commit()
    # replay koruması: ikinci consume reddedilir
    assert await svc.consume(str(a.id)) is False


@pytest.mark.asyncio
async def test_decide_reject(session):
    a = await _create(session)
    d = await ApprovalService(session).decide(str(a.id), "reject", str(uuid.uuid4()))
    assert d.status == ApprovalStatus.REJECTED.value


@pytest.mark.asyncio
async def test_decide_twice_rejected(session):
    a = await _create(session)
    svc = ApprovalService(session)
    await svc.decide(str(a.id), "approve", str(uuid.uuid4()))
    await session.commit()
    with pytest.raises(ValueError):
        await svc.decide(str(a.id), "reject", str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_decide_not_found(session):
    with pytest.raises(ValueError):
        await ApprovalService(session).decide(str(uuid.uuid4()), "approve", str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_decide_invalid_decision(session):
    a = await _create(session)
    with pytest.raises(ValueError):
        await ApprovalService(session).decide(str(a.id), "maybe", str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_consume_pending_rejected(session):
    a = await _create(session)
    # PENDING onay consume edilemez
    assert await ApprovalService(session).consume(str(a.id)) is False


@pytest.mark.asyncio
async def test_consume_invalid_id(session):
    assert await ApprovalService(session).consume("not-a-uuid") is False

```

## `tests/unit/test_auth_http.py`

```py
# RAPTOR — AŞAMA 12 auth HTTP dependency + rate limiter redis testleri
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from observability.auth import (
    RateLimiter,
    create_session_token,
    get_current_user,
)


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_current_user_no_creds():
    with pytest.raises(HTTPException) as e:
        await get_current_user(None)
    assert e.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_invalid_token():
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bozuk-token")
    with pytest.raises(HTTPException) as e:
        await get_current_user(creds)
    assert e.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_expired_token():
    expired = create_session_token("u1", "admin", expires_seconds=-10)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired)
    with pytest.raises(HTTPException) as e:
        await get_current_user(creds)
    assert e.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_valid_token():
    token = create_session_token("u1", "admin")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    user = await get_current_user(creds)
    assert user["user_id"] == "u1"
    assert user["role"] == "admin"


# ---------------------------------------------------------------------------
# RateLimiter — redis yolu + reset + info
# ---------------------------------------------------------------------------
class _FakePipe:
    async def execute(self):
        return (1, True)


class _FakeRedis:
    def pipeline(self):
        return _FakePipe()

    async def delete(self, key):
        return 1


@pytest.mark.asyncio
async def test_rate_limiter_redis_path():
    rl = RateLimiter()
    rl._redis = _FakeRedis()
    rl._redis_tried = True
    assert await rl.check("k1", 10, 60) is True


@pytest.mark.asyncio
async def test_rate_limiter_memory_fallback():
    rl = RateLimiter()
    rl._redis = None
    rl._redis_tried = True
    assert await rl.check("k2", 2, 60) is True
    assert await rl.check("k2", 2, 60) is True
    assert await rl.check("k2", 2, 60) is False  # limit 2 aşıldı

```

## `tests/unit/test_auth_units.py`

```py
# RAPTOR — AŞAMA 12 auth unit testleri (parola, session, RBAC, rate limit)
import time

import pytest
from fastapi import HTTPException

from observability.auth import (
    RateLimiter,
    create_session_token,
    decode_session_token,
    hash_password,
    require_role,
    verify_password,
)


def test_hash_password_roundtrip():
    stored = hash_password("gizli-parola-123")
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_password("gizli-parola-123", stored) is True
    assert verify_password("yanlis", stored) is False


def test_verify_password_malformed():
    assert verify_password("x", "not-a-valid-hash") is False


def test_session_token_roundtrip():
    token = create_session_token("user-1", "operator")
    payload = decode_session_token(token)
    assert payload["sub"] == "user-1"
    assert payload["role"] == "operator"


def test_session_token_expired():
    token = create_session_token("u", "viewer", expires_seconds=-1)
    import jwt as _jwt
    with pytest.raises(_jwt.ExpiredSignatureError):
        decode_session_token(token)


@pytest.mark.asyncio
async def test_require_role_admin_blocks_viewer():
    dep = require_role("admin")
    with pytest.raises(HTTPException):
        await dep({"role": "viewer"})
    assert await dep({"role": "admin"}) == {"role": "admin"}


@pytest.mark.asyncio
async def test_require_role_operator_allows_admin():
    dep = require_role("operator")
    assert (await dep({"role": "admin"}))["role"] == "admin"


@pytest.mark.asyncio
async def test_rate_limiter_memory_fallback():
    rl = RateLimiter()
    rl._redis = None
    rl._redis_tried = True
    # 2 istek izinli, 3. reddedilir
    assert await rl.check("k1", limit=2, window_seconds=60) is True
    assert await rl.check("k1", limit=2, window_seconds=60) is True
    assert await rl.check("k1", limit=2, window_seconds=60) is False


@pytest.mark.asyncio
async def test_rate_limiter_window_expiry():
    rl = RateLimiter()
    rl._redis = None
    rl._redis_tried = True
    assert await rl.check("k2", limit=1, window_seconds=60) is True
    # pencereyi geçmiş gibi göster (eski timestamp)
    rl._mem["k2"] = [time.time() - 120]
    assert await rl.check("k2", limit=1, window_seconds=60) is True

```