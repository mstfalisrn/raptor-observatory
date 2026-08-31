# Changelog

Bu proje [Semantic Versioning](https://semver.org/spec/v2.0.0.html) kurallarına uyar.
Format [Keep a Changelog](https://keepachangelog.com/) temellidir.

## [1.1.0] - 2026-08-31

Public + UI + Autonomous sürümü. Tek origin, LLM-matris, modern web UI ve otonom hafıza.

### Eklenen (Added)
- **Public quickstart** — `docs/INSTALL.md` (Docker 24+, 4GB RAM, 3525 portu), `quickstart.sh` idempotent secret üretimi (`CHANGE_ME` → hex), `MIT LICENSE`, `README` public quickstart (60 sn).
- **LLM provider matrisi** — `docs/CONFIGURATION.md`: `mock` (ücretsiz, anahtar yok) vs `openai_compatible` tek matris; 4 örnek — Mock, OpenAI (`https://api.openai.com/v1` / `gpt-4o-mini` / `sk-...`), OpenRouter (`https://openrouter.ai/api/v1` / `anthropic/claude-3.5-sonnet` / `sk-or-...`), Ollama (`http://host.docker.internal:11434/v1` / `llama3.1` / `ollama`); `POST /api/v1/settings/llm/test` ile doğrulama.
- **Web UI yenileme** — Tailwind 4 + shadcn + oklch + 8pt grid + lucide-react + framer-motion; collapsible sidebar, mobile drawer (`Sheet`), topbar `backdrop-blur`, `oklch` light/dark tokens (`styles.css`).
- **Dashboard** — 4 KPI kartı (Total Runs, Success %, Queue Depth, Avg Tokens), son 5 run timeline, SSE nabzı (`SSEDot` + `animate-ping`).
- **Runs** — pagination (`limit/offset`), arama/filtre, stepper/detail view, durum `Badge` variantları.
- **Onboarding wizard** — `pages/Onboarding.tsx` (3 adım: env check → LLM seçimi → ilk prompt) + Command Center (`POST /v1/tasks`).
- **SSE canlı akış** — `/api/v1/events/stream` (`text/event-stream`, `Last-Event-ID` + `global_seq` cursor), `openSSE()` auto-reconnect, Topbar/Dashboard pulse.
- **Context Inspector** — 7 katmanlı denetlenebilir `context_segments` (token/relevance/freshness/confidence).
- **Memory auto-promote** — `candidate → approved/active → superseded/expired`, embedding retrieval (OpenAI-compatible).
- **outbox `not_before`** — scheduler deferred delivery için `not_before` kolonu; `d4e5f6a7b8c9` migrasyonu.
- **Docs/UI rehberi** — `docs/UI_GUIDE.md` (11 sekme haritası, tasarım sistemi, screenshot placeholder, onboarding, SSE).
- **PR/issue şablonları** — `.github/PULL_REQUEST_TEMPLATE.md` (checklist: ruff/pytest/bandit/secret-scan/compose), `.github/ISSUE_TEMPLATE/bug_report.md`.
- **CI** — 7 job korunuyor: `pytest` (pgvector/redis + alembic upgrade/downgrade), `ruff`, `bandit`, `secret-scan`, `compose-config`, `frontend` (tsc + build + audit), `docker-build`.

### Değişen (Changed)
- Frontend `apps/web` — Tailwind 4 (`@tailwindcss/vite`), shadcn primitives (`button/card/badge/input/sheet`), `cn()` utils, `App.tsx` sidebar/drawer/topbar.
- README — public quickstart ve LLM provider tablosu güncellendi.

### Teknik Notlar
- Host tek bind `127.0.0.1:3525` korunuyor; PG/Redis internal-only; non-root/read-only/cap_drop ALL.
- Local auth: JWT + PBKDF2 + RBAC; SSRF allowlist; secret-scan fail-closed.

## [1.0.0] - 2026-08-26

İlk production-ready sürüm. AŞAMA 0–13 tamamlandı; uçtan uca doğrulandı, canlıya alındı.

### Eklenen (Added)
- **Agentic döngü** — Planner (provider argümanlı actions) → Coordinator → ToolExecutor; plan/eylem/kanıt DB yazımı, token/maliyet takibi, pause/stop kontrolü.
- **ApprovalService** — atomik `SELECT FOR UPDATE` + expiry + `CONSUMED` replay; canonical JSON hash + HMAC token; path==body doğrulaması.
- **Telegram durable inbox** — webhook + Redis Streams; `PENDING/PROCESSED/FAILED` durumu; opaque path + secret header doğrulaması.
- **Atomik run claim** — `UPDATE WHERE status/lease` + heartbeat loop + `retry_count` + DLQ + exponential backoff.
- **Technocore entegrasyonu** — DID imzalı yazma (`load_key` prod'da auto-generate etmez), oda `dm-topic`, 5 dk okuma.
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
