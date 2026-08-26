# Changelog

Bu proje [Semantic Versioning](https://semver.org/spec/v2.0.0.html) kurallarına uyar.
Format [Keep a Changelog](https://keepachangelog.com/) temellidir.

## [1.0.0] - 2026-08-26

İlk production-ready sürüm. AŞAMA 0–13 tamamlandı; uçtan uca doğrulandı, canlıya alındı.

### Eklenen (Added)
- **Agentic döngü** — Planner (provider argümanlı actions) → Coordinator → ToolExecutor; plan/eylem/kanıt DB yazımı, token/maliyet takibi, pause/stop kontrolü.
- **ApprovalService** — atomik `SELECT FOR UPDATE` + expiry + `CONSUMED` replay; canonical JSON hash + HMAC token; path==body doğrulaması.
- **Telegram durable inbox** — webhook + Redis Streams; `PENDING/PROCESSED/FAILED` durumu; opaque path + secret header doğrulaması.
- **Atomik run claim** — `UPDATE WHERE status/lease` + heartbeat loop + `retry_count` + DLQ + exponential backoff.
- **Technocore entegrasyonu** — DID imzalı yazma (`load_key` prod'da auto-generate etmez), oda `d-raptor`, 5 dk okuma.
- **Embedding + hafıza** — OpenAI-compatible embedding provider, `EMBEDDING_MODEL/DIM` config, worker task başında memory retrieval.
- **Web UI** — run listesi/detay, pause/resume/stop/retry kontrolü, SSE canlı akış.
- **Migration servisi** — one-shot `raptor-migrate` (API migration çalıştırmaz); `service_completed_successfully` bağımlılığı.
- **CI kapıları** — ruff, bandit, coverage (%70), secret-scan, compose validate; PostgreSQL/Redis service container'ları.

### Değişen (Changed)
- `Vector(1536).with_variant()` pgvector çakışması düzeltildi → `Vector(1536)` doğrudan.
- JSONB → portable `JSONType` (SQLite + PostgreSQL uyumlu).
- Queue `raptor:queue` list → `raptor:stream:run_queue` Streams + `raptor:stream:dlq`.
- `RunEvent.global_seq` Identity + SSE global cursor (partial index `text()`).

### Düzeltilen (Fixed)
- pgvector `with_variant` import hatası (prod/migration container'ında yakalanıp düzeltildi).
- CI'da `aiosqlite` eksikliği (testler `sqlite+aiosqlite` kullanıyor) → `requirements-dev.txt`'e eklendi.

### Güvenlik (Security)
- Local auth: session JWT + PBKDF2 + RBAC (`admin/operator/viewer`), rate limit, body limit.
- SSRF allowlist (`technocore.chat`, `api.github.com`).
- Non-root container'lar, read-only rootfs, `cap_drop ALL`; host'ta tek bind `127.0.0.1:3525`.
- Secret-scan fail-closed; `.env.example` yalnız değişken adı + güvenli placeholder içerir.
