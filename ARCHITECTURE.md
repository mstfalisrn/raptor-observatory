# ARCHITECTURE.md — RAPTOR Mimari

## Genel bakış
RAPTOR, bağımsız Docker Compose stack'i üzerinde koşan, gözlem-odaklı bir agent runtime'dır.
Hermes yalnız builder/operator; runtime veri yolunda yer almaz.

```
Telegram Bot API ----\
                      > raptor-gateway -> raptor-api -> RunCoordinator
Web UI / Cloudflare -/                            |
                                                  +-> ContextAssembler
                                                  +-> PolicyEngine
                                                  +-> ToolExecutor (connectors)
                                                  +-> Verifier/Reporter
                            Redis <-> worker/scheduler <-> PostgreSQL + pgvector
```

## Agent runtime (kayıt iş akışı)
Görev state machine (şartnamedeki ile birebir):

```
QUEUED -> CONTEXT_BUILDING -> PLANNING -> POLICY_CHECK
       -> WAITING_APPROVAL | EXECUTING
       -> VERIFYING -> PERSISTING -> COMPLETED
       -> FAILED | CANCELLED | PAUSED
```

Bileşenler:
- **RunCoordinator** — state machine, bütçe/timeout/iteration, circuit breaker, kill switch.
- **Planner** — yapılandırılmış plan + beklenen kanıt (task scope'a göre şablon).
- **ContextAssembler** — katmanlı bağlam, token bütçesi, denetlenebilir metadata.
- **PolicyEngine** — ALLOW / REQUIRE_APPROVAL / DENY.
- **ToolExecutor** — kayıtlı & şemalı araçlar; keyfi shell/docker yok.
- **Verifier** — kanıt/koşul kontrolü.
- **MemoryService** — candidate→approved/active→superseded/expired.
- **Reporter** — insan özeti + makine-okunur paket.

## Bağlam katmanları (Context Inspector)
1. system_policy 2. task_goal 3. conversation_window 4. episodic_memory
5. semantic_memory 6. procedural_memory 7. tool_schemas (+ output reserve).

Her segment: segment_type, source_id, title, token_count, relevance, freshness,
confidence, included_reason, contains_untrusted, redaction_count.

## Veri modeli — 22 tablo
users, telegram_identities, agent_profiles, tasks, runs, run_events(append-only),
plans, tool_calls, approvals, context_snapshots, context_segments, memory_items,
memory_relations, sources, source_observations, evidence_items, reports,
publication_attempts, technocore_cursors, prompt_versions, policy_versions, audit_events.

Timestamp: DB'de UTC; UI'da UTC.

## Kuyruk / worker
- Redis list `raptor:queue`. Worker bir run alır, coordinator ile yürütür, sonucu + event'leri DB'ye yazar.
- Araçlar bir kez çalıştırılır; iterasyon araç sayısı kadardır (D1 düzeltmesi).

## Connector'lar (MVP)
technocore_read, technocore_signed_write (DID+approval), github_repo_read,
http_json_read (SSRF korumalı), internal_health.

## API uçları
/health/live · /health/ready · /api/v1/{tasks,runs,runs/{id}/events,approvals,memory,sources,reports,technocore,settings/non-secret,events/stream} · /webhooks/telegram/<opaque>.

## SSE
`/api/v1/events/stream` son run event'lerini yayınlar; Caddy `flush_interval -1` ile stream.