# RAPTOR — Code Chunk 001

> GPT sırayla okuyup birleştirsin (MCP 100KB limit).

## `ARCHITECTURE.md`

```md
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
```

## `CHANGELOG.md`

```md
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

```

## `DECISIONS.md`

```md
# DECISIONS.md — Karar Kaydı

Bu dosya mimari ve ürün kararlarını, gerekçeleriyle birlikte tutar (append-only niyetli).

## D1 — Tek origin mimarisi (UI + API aynı origin)
- **Karar:** Web UI statik build'i `raptor-api` image'ına gömdük; `raptor-web` ayrı servis kaldırıldı.
- **Gerekçe:** Şartname "tek origin altında API ile sun" der. Tek origin CORS/CSRF/cookie
  risklerini azaltır, SSO/Cloudflare Access tek noktada doğrulanır.
- **Alternatif **: ayrı static server. Reddedildi (çift origin).

## D2 — Quartz/Celery yerine Redis listesi
- **Karar:** Job queue Redis list (`raptor:queue`); worker bloş poll eder.
- **Gerekçe:** Bağımlılık az, istemci-sürücülü, yeterli. Üretimde RQ/arq'ya geçilebilir.
- **Not:** Soyut arayüz üzerinden değiştirilebilir.

## D3 — `runs.plan_id`'de FK döngüsü kırıldı
- **Karar:** `runs.plan_id` düz UUID kolonu; `plans.run_id -> runs` tek yönlü FK.
- **Gerekçe:** plan↔run çift yönlü FK Alembic autogenerate'i bozuyordu (tables order).
- **Etki:** referans doğruluğunu uygulama katmanı sağlar.

## D4 — Alembic async (asyncpg)
- **Karar:** Datab basis `postgresql+asyncpg`; Alembic env async çalışır.
- **Gerekçe:** App async; senkron psycopg şeması iki farklı URL gerektiriyordu.

## D5 — Technocore public yazı varsayılan kapalı
- **Karar:** `technocore_signed_write` policy'de `REQUIRE_APPROVAL`; `PUBLIC-POST-APPROVED`
  gate'i. DID key yine de üretildi, imza doğrulandı.
- **Gerekçe:** "kullanıcı onayı olmadan yazma yok" — airdrop/spam karşıtı.

## D6 — Cloudflare Access şimdi kurulmadı
- **Karar:** Public hostname şimdilik aktive edilmedi; yalnız localhost/Tailscale.
- **Gerekçe:** Şartnamedeki "Access hazır değilse public hostname'i aktive etme" kuralı.
  Access kurulunca ingress + DNS + origin JWT doğrulaması eklenir.

## D7 — Verb/LLM key'ler sıfırdan gelir
- **Karar:** Telegram bot ve LLM provider ayrı (Hermes'ten kopyalanmaz); secret script
  ile girilir. Mock provider varsayılan dev/test için.
- **Gerekçe:** İzolasyon kuralı; Hermes sırları paylaşılmaz.
```

## `OPERATIONS.md`

```md
# OPERATIONS.md — RAPTOR Operasyon / Runbook

## Servisler
| Servis | Durum komutu | Log |
|---|---|---|
| Stack (systemd) | `systemctl status raptor-observatory` | `journalctl -u raptor-observatory` |
| API | `docker logs raptor-api` | internal 8000 |
| Worker | `docker logs raptor-worker` | internal 8001 |
| Scheduler | `docker logs raptor-scheduler` | internal 8002 |
| Gateway | `docker logs raptor-gateway` | 127.0.0.1:3525 |
| PostgreSQL | `docker logs raptor-postgres` | internal |
| Redis | `docker logs raptor-redis` | internal |

## Health
- `curl http://127.0.0.1:3525/health/live`  → liveness
- `curl http://127.0.0.1:3525/health/ready` → DB bağlantısı

## Yedek / Geri yükleme
```bash
export $(grep '^DB_PASSWORD=' ./secrets/raptor-observatory/app.env)
./scripts/backup-restore.sh backup
./scripts/backup-restore.sh restore /var/backups/raptor-observatory/raptor-<ts>.dump
```
Restore **ayrı** `raptor_restore_test` DB'sine yazar; üretim verisine dokunmaz.

## Deployment / Güncelleme
```bash
cd /path/to/raptor-observatory
docker compose up -d --build
./scripts/secret-scan.sh .
```

## Incident
- **Worker takıldı:** `docker restart raptor-worker` — Redis queue'den aynen devam.
- **API unhealthy:** `docker logs raptor-api` — migration/import hatası kontrol.
- **Data kaybı:** yedekten restore (`backup-restore.sh restore`).
- **Circuit breaker açıldı:** cooldown 30sn sonra otomatik sıfırlanır; kalıcısa tool revisiew.

## Sırlar
- Değiştirme: `./scripts/configure-secrets.sh --gen` veya interaktif; ardından `docker compose up -d`.
- Asla ekrana/loga/commit'e yazma.

## Erişim
- Localhost: `http://127.0.0.1:3525`
- Tailscale: sunucu IP `100.122.82.116` üzerinden erişilebilir.
- Public hostname: Cloudflare Access kurulunca `raptor.your-domain.example`.
```

## `README.md`

```md
# RAPTOR Agentic Observatory

[![CI](https://github.com/your-owner/raptor-observatory/actions/workflows/ci.yml/badge.svg)](https://github.com/your-owner/raptor-observatory/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.0.0-blue)](https://github.com/your-owner/raptor-observatory/releases)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)

Hermes'ten bağımsız çalışan, Telegram + Web UI üzerinden yönlendirilen, izlenebilir
agent runtime altyapısı. Gözlem (Technocore + açık kaynak) odaklı; bağlam denetlenebilir,
her eylem politikadan, hafıza kontrollü, çıktı kanıtlanabilir.

> Hermes bu sistemin **runtime'ı değildir** — yalnız kodlayan/kuran/doğrulayan operatördür.

## Mimari

```
Telegram Bot API ----\
                      > raptor-gateway (Caddy) -> raptor-api -> RunCoordinator
Web UI / Cloudflare -/                            |              +-> ContextAssembler
                                                  |              +-> PolicyEngine
                                                  |              +-> ToolExecutor (connectors)
                                                  |              +-> Verifier/Reporter
                                                  |
                            Redis <-> worker/scheduler <-> PostgreSQL + pgvector
```

## Servisler (Docker Compose)

| Servis | Rol | Port (host) |
|---|---|---|
| `raptor-gateway` | Caddy reverse proxy + UI/API | `127.0.0.1:3525` |
| `raptor-api` | FastAPI + SSE + webhook + UI static | iç |
| `raptor-worker` | run yürütme (Redis queue) | iç |
| `raptor-scheduler` | periyodik/takip | iç |
| `raptor-migrate` | one-shot Alembic migration | iç |
| `raptor-postgres` | PostgreSQL 16 + pgvector | yok (internal) |
| `raptor-redis` | kuyruk/koordinasyon | yok (internal) |

Tüm container'lar non-root, read-only rootfs, cap_drop ALL. Host'ta tek bind `127.0.0.1:3525`.

## Hızlı başlangıç

```bash
# 1) secret'lar (root-only)
./scripts/configure-secrets.sh --gen        # otomatik üret
./scripts/configure-secrets.sh              # interaktif (TG bot + LLM key)

# 2) compose env
cp .env.example .env                         # üretimde değerleri secret'tan aktar
# POSTGRES_PASSWORD, JWT_SECRET, SESSION_ENCRYPTION_MASTER_KEY, TELEGRAM_WEBHOOK_SECRET ...

# 3) stack
docker compose up -d --build
./scripts/secret-scan.sh .                   # secret taraması

# 4) test
pytest
```

## Yönetim

```bash
systemctl status raptor-observatory          # stack (boot'ta auto-start)
./scripts/backup-restore.sh backup           # yedek
./scripts/backup-restore.sh restore <dump>   # ayrı test DB'sine geri yükle
```

## Durum

Production-ready (AŞAMA 0–13 tamamlandı, canlıda):

- ✅ **AŞAMA 0–13** — keşif → scaffold → agent core → kuyruk/worker → Telegram durable inbox →
  atomik claim + DLQ → Technocore DID → embedding/hafıza → SSE global cursor → Web UI →
  migration servisi → CI kapıları → production deploy (uçtan uca doğrulandı)
- ✅ **Production canlı** — `raptor.your-domain.example` (Cloudflare Tunnel), Telegram
  `@raptoragarnaccio_bot`, Technocore oda `dm-topic`
- ✅ **Kalite kapıları** — 185 test, coverage ≥%70, ruff 0, bandit 0 Medium/High, secret-scan temiz
- ✅ **Güvenlik** — local auth (JWT + PBKDF2 + RBAC), rate limit, SSRF allowlist, non-root/read-only

## Sürümler (Versioning)

[SemVer](https://semver.org/) kullanılır; sürüm tek kaynaktan (`packages/observability/__init__.py`
`__version__`) okunur.

- Git tag: `vMAJOR.MINOR.PATCH` (örn. `v1.0.0`)
- Her sürüm [CHANGELOG.md](CHANGELOG.md)'de kayıtlıdır
- Sürüm çıkarmak: `gh release create v1.0.0 --generate-notes`

Daha fazla: [ARCHITECTURE.md](ARCHITECTURE.md) · [SECURITY.md](SECURITY.md) · [OPERATIONS.md](OPERATIONS.md) · [DECISIONS.md](DECISIONS.md) · [CHANGELOG.md](CHANGELOG.md)

```

## `SECURITY.md`

```md
# SECURITY.md — RAPTOR Güvenlik Modeli

## İzolasyon (değiştirilemez)
- Proje kökü: `/path/to/raptor-observatory`
- Sırlar: `./secrets/raptor-observatory/app.env` (0700/0600, root:root)
- `/path/.hermes`, Hermes runtime, container, volume, config, memory, skills
  ve `hermes.your-domain.example:9119` **dokunulmaz**.
- Hermes'in TG token / model anahtarı RAPTOR'a kopyalanmaz; ayrı bot + ayrı provider.
- RAPTOR container'larına Hermes dizini / Docker socket / host root mount **yok**.
- RAPTOR runtime'ı Hermes dururken de çalışır (ayrı Docker stack + systemd).

## Runtime güvenliği
- Tüm servisler: non-root (10001), read-only rootfs, `cap_drop: ALL`,
  `no-new-privileges:true`.
- PostgreSQL/Redis host portu açılmaz (internal network).
- Yalnız `raptor-gateway` host'ta `127.0.0.1:3525`'e bind eder.

## Agent güvenliği
- **Araçlar:** yalnız kayıtlı & şemalı araçlar; keyfi shell/Docker **yok**.
- **SSRF:** loopback/RFC1918/link-local/metadata/socket/internal hostname engeli;
  DNS çözümü + her redirect sonrası IP yeniden sınıflandırma; url allowlist + boyut/timeout.
- **Politika:** READ_ONLY auto · SAFE_WRITE audit'li · PUBLIC_WRITE/PRIVILEGED/DESTRUCTIVE
  insan onayı. Onaylar tek kullanımlık + süreli + eylem hash'ine bağlı.
- **Redaksiyon:** token, Authorization, JWT, env sırları modele/hafızaya girmeden maskelenir.
- **Untrusted:** Technocore mesajları daima `UNTRUSTED` — komut çıkarılamaz, tool tetiklenemez.

## Telegram
- Yalnız `TELEGRAM_ALLOWED_USER_IDS` (numeric); `*` / allow-all **yasak**.
- Grup varsayılan kapalı. Webhook secret token doğrulanır. Token loglanmaz.
- `update_id` ile idempotent; approve callback'leri user+action+hash+expiry bağlı token.

## Web
- Üretimde Cloudflare Access arkasında; origin `Cf-Access-Jwt-Assertion` doğrular.
- Secure/HttpOnly/SameSite cookie, CSP, rate limit, login audit.
- localStorage'a auth token/secret yazılmaz.

## Onay akışı (public yayın)
Technocore'a yazma yalnız kullanıcı `PUBLIC-POST-APPROVED` dediğinde, DID imzalı olarak.

## Sızma testleri (doğrulandı)
- SSRF birim testleri (loopback/rfc1918/metadata/redirect)
- Policy: public write/privileged = approval; destructive = deny
- Redaction birim testleri (Bearer/TG token/JWT)
- `secret-scan.sh` repo taraması temiz
- Backup/restore üretim verisine dokunmadan geçti
- Port taraması: raptor yalnız `127.0.0.1:3525`
```

## `apps/api/Dockerfile`

```txt
# RAPTOR — API + UI tek image (çok aşamalı)
# Aşama 1: Web build (node:22-alpine pinned)
ARG PYTHON_IMAGE
FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS web-build
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json /web/
RUN npm ci --no-audit --no-fund
COPY apps/web/ /web/
ENV VITE_API_BASE=/api VITE_SSE_BASE=/api/v1/events/stream
RUN npm run build

# Aşama 2: Python API + UI statik (python:3.12-slim pinned)
FROM ${PYTHON_IMAGE}

RUN groupadd -g 10001 raptor && useradd -u 10001 -g raptor -s /usr/sbin/nologin raptor

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/raptor

COPY packages/requirements-api.txt /srv/raptor/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY packages/ /srv/raptor/
COPY apps/api/ apps/api/
COPY migrations/ migrations/

COPY --from=web-build /web/dist/ /srv/raptor/apps/web/dist/

USER raptor
EXPOSE 8000
CMD ["sh", "-c", "uvicorn apps.api.app:app --host 0.0.0.0 --port 8000 --workers 1"]
```

## `apps/api/__init__.py`

```py

```

## `apps/api/app.py`

```py
# RAPTOR — FastAPI uygulaması
# Endpoint grupları: /health, /api/v1/*, /webhooks/telegram/<opaque_path>, /events/stream (SSE)
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text

from memory.service import MemoryService
from observability import __version__, models
from observability.config import settings
from observability.db import async_session_factory
from observability.security import redact

log = logging.getLogger("raptor.api")


# --- Lifespan: admin kullanıcısını seed et ---
from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    if settings.ADMIN_PASSWORD_HASH:
        async with async_session_factory() as s:
            res = await s.execute(select(models.User).where(models.User.username == settings.ADMIN_EMAIL))
            u = res.scalar_one_or_none()
            if u is None:
                s.add(models.User(username=settings.ADMIN_EMAIL, display_name="Admin",
                                  role="admin", is_active=True, password_hash=settings.ADMIN_PASSWORD_HASH))
                await s.commit()
                log.info("admin kullanıcı seed edildi: %s", settings.ADMIN_EMAIL)
            elif u.password_hash != settings.ADMIN_PASSWORD_HASH:
                u.password_hash = settings.ADMIN_PASSWORD_HASH
                await s.commit()
    # Telegram Application singleton: build+initialize+start BİR KEZ (webhook için)
    _tg = None
    if settings.TELEGRAM_BOT_TOKEN:
        try:
            from agent_core.telegram import get_service
            _tg = get_service()
            await _tg.initialize()
            log.info("Telegram Application initialized")
        except Exception as e:
            log.warning("Telegram initialize atlandı (dev): %s", type(e).__name__)
    yield
    if _tg is not None:
        await _tg.shutdown()


app = FastAPI(title="RAPTOR Agentic Observatory", version=__version__, lifespan=_lifespan)

# --- Fail-fast: production'da eksik/placeholder secret ile boot etme (P58) ---
import os as _os

if _os.getenv("APP_ENV") == "production":
    _missing = []
    for _k in ("JWT_SECRET", "SESSION_ENCRYPTION_MASTER_KEY", "TELEGRAM_WEBHOOK_SECRET"):
        _v = getattr(settings, _k.lower(), "") or _os.getenv(_k, "")
        if not _v or _v in ("CHANGE_ME", "dev-only-change-me") or len(str(_v)) < 16:
            _missing.append(_k)
    if _missing:
        raise RuntimeError(f"RAPTOR fail-fast: eksik/placeholder secret: {', '.join(_missing)}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://raptor.your-domain.example",
        "http://127.0.0.1:3525",
        "http://localhost:3525",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Cf-Access-Jwt-Assertion", "X-Telegram-Bot-Api-Secret-Token"],
)

# --- Local auth (CF Access kullanılmıyor) + rate limit + body size ---
from observability.auth import (
    create_session_token,
    get_current_user,
    rate_limiter,
    require_role,
    verify_password,
)

_PUBLIC_PATHS = {"/health/live", "/health/ready", "/api/health/live", "/api/health/ready", "/api/v1/auth/login", "/api/v1/auth/status"}


@app.middleware("http")
async def _guard(request: Request, call_next):
    path = request.url.path
    # Telegram webhook + health + login muaf (webhook secret header ile korunur)
    if path.startswith("/webhooks/telegram/") or path in _PUBLIC_PATHS:
        return await call_next(request)
    # Body boyut limiti (Content-Length + streaming guard)
    cl = request.headers.get("content-length", "")
    if cl.isdigit() and int(cl) > settings.MAX_REQUEST_BODY_BYTES:
        return JSONResponse({"detail": "request body çok büyük"}, status_code=413)
    # Global rate limit — gerçek istemci IP'si (Cloudflare Tunnel arkasında request.client.host=127.0.0.1 olur)
    cf_ip = request.headers.get("CF-Connecting-IP", "").strip()
    xff = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    ip = cf_ip or xff or (request.client.host if request.client else "unknown")
    if not await rate_limiter.check(f"rl:global:{ip}", settings.RATE_LIMIT_PER_MINUTE, 60):
        return JSONResponse({"detail": "rate limit aşıldı"}, status_code=429)
    return await call_next(request)


# ---------------------------------------------------------------------------
# Pydantic şemalar — secret alanları response modellerinde YOK
# ---------------------------------------------------------------------------
class TaskCreate(BaseModel):
    title: str
    prompt: str
    scope: dict = {}
    budget: dict = {}
    idempotency_key: str | None = None


class ApprovalDecision(BaseModel):
    decision: str  # approve | reject
    approval_id: str


class RunControl(BaseModel):
    action: str  # pause | resume | stop


def _tg_allowed() -> bool:
    return bool(settings.allowed_user_ids)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health/live")
async def health_live():
    return {"status": "live", "time": datetime.now(UTC).isoformat()}


@app.get("/health/ready")
async def health_ready():
    async with async_session_factory() as s:
        await s.execute(text("SELECT 1"))
    return {"status": "ready", "db": True}


@app.get("/api/health/live")
async def api_health_live():
    return {"status": "live", "time": datetime.now(UTC).isoformat()}


@app.get("/api/health/ready")
async def api_health_ready():
    async with async_session_factory() as s:
        await s.execute(text("SELECT 1"))
    return {"status": "ready", "db": True}


# ---------------------------------------------------------------------------
# Auth (local session)
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/v1/auth/login")
async def login(req: LoginRequest):
    async with async_session_factory() as s:
        res = await s.execute(select(models.User).where(models.User.username == req.email))
        u = res.scalar_one_or_none()
        if u is None or not u.is_active or not u.password_hash or not verify_password(req.password, u.password_hash):
            raise HTTPException(401, "geçersiz email veya parola")
        token = create_session_token(str(u.id), u.role, settings.SESSION_TTL_SECONDS)
        return {"token": token, "role": u.role, "email": u.username, "display_name": u.display_name}


@app.get("/api/v1/auth/status")
async def auth_status():
    return {"auth": "local", "admin_email": settings.ADMIN_EMAIL,
            "roles": ["admin", "operator", "viewer"],
            "session_ttl_seconds": settings.SESSION_TTL_SECONDS}


@app.get("/api/v1/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    async with async_session_factory() as s:
        res = await s.execute(select(models.User).where(models.User.id == user["user_id"]))
        u = res.scalar_one_or_none()
    if u is None:
        raise HTTPException(404, "kullanıcı yok")
    return {"user_id": str(u.id), "username": u.username, "role": u.role,
            "display_name": u.display_name, "is_active": u.is_active}


# ---------------------------------------------------------------------------
# Tasks / Runs — outbox pattern + Redis Streams
# ---------------------------------------------------------------------------
@app.post("/api/v1/tasks", status_code=201)
async def create_task(t: TaskCreate, user: dict = Depends(require_role("operator"))):
    from sqlalchemy.exc import IntegrityError
    outbox_key = f"task:{t.idempotency_key}" if t.idempotency_key else f"auto:{uuid.uuid4().hex}"
    async with async_session_factory() as s:
        # idempotency pre-check (optimistic)
        if t.idempotency_key:
            existing = await s.execute(
                select(models.Task).where(models.Task.idempotency_key == t.idempotency_key)
            )
            row = existing.scalar_one_or_none()
            if row is not None:
                # return existing task's latest run
                rres = await s.execute(select(models.Run).where(models.Run.task_id == row.id).order_by(models.Run.created_at.desc()).limit(1))
                rr = rres.scalar_one_or_none()
                raise HTTPException(409, detail={"error": "idempotency key zaten kullanıldı", "task_id": str(row.id), "run_id": str(rr.id) if rr else None})
        task = models.Task(
            title=t.title, prompt=t.prompt, scope=t.scope, budget=t.budget,
            idempotency_key=t.idempotency_key,
        )
        s.add(task)
        await s.flush()
        run = models.Run(task_id=task.id, status=models.RunStatus.QUEUED.value,
                         token_budget=settings.RUN_MAX_TOKEN_BUDGET,
                         cost_budget=settings.RUN_MAX_COST_BUDGET)
        s.add(run)
        await s.flush()
        # outbox transactional
        ob = models.OutboxMessage(
            topic="raptor.run_queued",
            payload={"run_id": str(run.id), "task_id": str(task.id)},
            idempotency_key=outbox_key,
            processed=False,
        )
        s.add(ob)
        try:
            await s.commit()
        except IntegrityError as ie:
            await s.rollback()
            msg = str(ie.orig) if hasattr(ie, "orig") else str(ie)
            if "ix_tasks_idempotency_key" in msg or "uq_" in msg or "idempotency" in msg.lower():
                raise HTTPException(409, "idempotency key zaten kullanıldı (race)") from ie
            raise HTTPException(500, f"commit hatası: {type(ie).__name__}") from ie
        # best-effort publish to Redis Streams (outbox publisher will retry)
        try:
            import redis as redis_lib

            from observability.queue import publish_to_stream
            r = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                from observability.queue import ensure_stream_group
                ensure_stream_group(r)
            except Exception:
                pass
            stream_id = publish_to_stream(r, {"run_id": str(run.id), "task_id": str(task.id)}, idempotency_key=outbox_key)
            # mark outbox processed (best-effort, scheduler will also reconcile)
            async with async_session_factory() as s2:
                ob2 = await s2.get(models.OutboxMessage, ob.id)
                if ob2 and not ob2.processed:
                    ob2.processed = True
                    ob2.processed_at = datetime.now(UTC)
                    ob2.stream_id = str(stream_id)
                    await s2.commit()
        except Exception:
            # outbox remains unprocessed -> scheduler will publish
            pass
        return {"task_id": str(task.id), "run_id": str(run.id), "status": run.status}


@app.get("/api/v1/runs")
async def list_runs(limit: int = 20, offset: int = 0, user: dict = Depends(get_current_user)):
    async with async_session_factory() as s:
        res = await s.execute(
            select(models.Run).order_by(models.Run.created_at.desc()).limit(limit).offset(offset)
        )
        runs = res.scalars().all()
        return [{"id": str(r.id), "status": r.status, "iteration": r.iteration,
                 "created_at": r.created_at.isoformat(), "error": r.error} for r in runs]


@app.get("/api/v1/runs/{run_id}/events")
async def run_events(run_id: str, user: dict = Depends(get_current_user)):
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(400, "run_id geçersiz") from None
    async with async_session_factory() as s:
        res = await s.execute(
            select(models.RunEvent).where(models.RunEvent.run_id == uid).order_by(models.RunEvent.seq)
        )
        return [{"seq": e.seq, "event_type": e.event_type, "payload": e.payload, "ts": e.ts.isoformat()}
                for e in res.scalars().all()]


@app.get("/api/v1/runs/{run_id}")
async def get_run(run_id: str, user: dict = Depends(get_current_user)):
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(400, "run_id geçersiz") from None
    async with async_session_factory() as s:
        run = await s.get(models.Run, uid)
        if run is None:
            raise HTTPException(404, "run bulunamadı")
        return {"id": str(run.id), "task_id": str(run.task_id), "status": run.status,
                "iteration": run.iteration, "token_used": run.token_used, "cost_used": run.cost_used,
                "worker_id": run.worker_id, "control_request": run.control_request,
                "error": run.error, "created_at": run.created_at.isoformat(),
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                # geriye uyum için deprecated alias
                "completed_at": run.finished_at.isoformat() if run.finished_at else None}


@app.post("/api/v1/runs/{run_id}/control")
async def control_run(run_id: str, c: RunControl, user: dict = Depends(require_role("operator"))):
    if c.action not in ("pause", "resume", "stop"):
        raise HTTPException(400, "action pause|resume|stop olmalı")
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(400, "run_id geçersiz") from None
    async with async_session_factory() as s:
        run = await s.get(models.Run, uid)
        if run is None:
            raise HTTPException(404, "run bulunamadı")
        if run.status not in (models.RunStatus.EXECUTING.value, models.RunStatus.QUEUED.value):
            raise HTTPException(409, f"run terminal durumda ({run.status}), kontrol edilemez")
        run.control_request = c.action if c.action != "resume" else None
        await s.commit()
        return {"ok": True, "run_id": str(run.id), "control_request": run.control_request}


@app.post("/api/v1/runs/{run_id}/retry")
async def retry_run(run_id: str, user: dict = Depends(require_role("operator"))):
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(400, "run_id geçersiz") from None
    async with async_session_factory() as s:
        run = await s.get(models.Run, uid)
        if run is None:
            raise HTTPException(404, "run bulunamadı")
        if run.status not in (models.RunStatus.FAILED.value, models.RunStatus.COMPLETED.value,
                              models.RunStatus.CANCELLED.value):
            raise HTTPException(409, f"run terminal değil ({run.status}), retry edilemez")
        # Retry aynı Run'ı reuse edip seq çakıştırmasın: aynı Task altında YENİ Run
        new_run = models.Run(
            task_id=run.task_id,
            status=models.RunStatus.QUEUED.value,
            retry_count=(run.retry_count or 0) + 1,
            token_budget=run.token_budget,
            cost_budget=run.cost_budget,
        )
        s.add(new_run)
        await s.flush()
        # outbox ile atomik enqueue (idempotent)
        try:
            out = models.OutboxMessage(
                topic="raptor.run_queued",
                payload={"run_id": str(new_run.id), "source_run_id": str(run.id)},
                idempotency_key=f"retry:{run.id}:{new_run.id}",
            )
            s.add(out)
        except Exception:
            pass
        await s.commit()
        # best-effort doğrudan stream'e de bas (outbox publisher yoksa)
        try:
            import redis as redis_lib

            from observability.queue import publish_to_stream
            r = redis_lib.from_url(settings.REDIS_URL)
            publish_to_stream(r, {"run_id": str(new_run.id)}, idempotency_key=f"retry:{run.id}:{new_run.id}")
        except Exception:
            pass
        return {"ok": True, "run_id": str(new_run.id), "source_run_id": str(run.id), "retry_count": new_run.retry_count}


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------
@app.get("/api/v1/approvals")
async def list_approvals(limit: int = 20, user: dict = Depends(get_current_user)):
    async with async_session_factory() as s:
        res = await s.execute(
            select(models.Approval).order_by(models.Approval.created_at.desc()).limit(limit)
        )
        return [{"id": str(a.id), "action_class": a.action_class, "target": redact(a.target),
                 "status": a.status, "impact_summary": a.impact_summary,
                 "expires_at": a.expires_at.isoformat() if a.expires_at else None}
                for a in res.scalars().all()]


@app.post("/api/v1/approvals/{approval_id}/decision")
async def decide_approval(approval_id: str, d: ApprovalDecision, user: dict = Depends(require_role("operator"))):
    # path approval_id ile body approval_id aynı olmalı
    if d.approval_id != approval_id:
        raise HTTPException(400, "path approval_id ile body approval_id uyuşmuyor")
    from policy.approval import ApprovalService
    try:
        async with async_session_factory() as s:
            svc = ApprovalService(s)
            a = await svc.decide(approval_id, d.decision, user.get("user_id"))
            # atomik: approve ise run resume outbox ile enqueue, reject ise run'ı terminale çek
            if d.decision == "approve" and a.run_id:
                # idempotent enqueue — aynı approval_id ikinci kez approve edilemez (decide zaten 409), fakat outbox da unique
                try:
                    s.add(models.OutboxMessage(
                        topic="raptor.run_queued",
                        payload={"run_id": str(a.run_id), "approval_id": str(a.id)},
                        idempotency_key=f"approve:{a.id}",
                    ))
                except Exception:
                    pass
            elif d.decision == "reject" and a.run_id:
                try:
                    r = await s.get(models.Run, a.run_id)
                    if r and r.status == models.RunStatus.WAITING_APPROVAL.value:
                        r.status = models.RunStatus.FAILED.value
                        r.error = "approval_rejected"
                except Exception:
                    pass
            await s.commit()
            # best-effort doğrudan stream'e de bas (outbox publisher yoksa düşmez)
            if d.decision == "approve" and a.run_id:
                try:
                    import redis as redis_lib

                    from observability.queue import publish_to_stream
                    rr = redis_lib.from_url(settings.REDIS_URL)
                    publish_to_stream(rr, {"run_id": str(a.run_id), "approval_id": str(a.id)}, idempotency_key=f"approve:{a.id}")
                except Exception:
                    pass
            return {"id": str(a.id), "status": a.status, "decision": a.decision}
    except ValueError as e:
        msg = str(e)
        if "süresi dolmuş" in msg or "EXPIRED" in msg:
            raise HTTPException(410, msg) from None
        if "bulunamadı" in msg:
            raise HTTPException(404, msg) from None
        if "zaten" in msg:
            raise HTTPException(409, msg) from None
        raise HTTPException(400, msg) from None


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------
class MemoryCreate(BaseModel):
    content: str
    source: str = ""
    confidence: float = 0.5
    category: str | None = None
    ttl_seconds: int | None = None


@app.get("/api/v1/memory")
async def list_memory(status: str | None = None, q: str | None = None, limit: int = 50, user: dict = Depends(get_current_user)):
    async with async_session_factory() as s:
        msvc = MemoryService(s)
        items = (await msvc.search(q, status, limit)) if q else (await msvc.list_status(status or "candidate", limit))
        return [{"id": str(i.id), "content": redact(i.content), "status": i.status,
                 "confidence": i.confidence, "source": i.source, "category": i.category,
                 "expires_at": i.expires_at.isoformat() if i.expires_at else None,
                 "created_at": i.created_at.isoformat()} for i in items]


@app.post("/api/v1/memory", status_code=201)
async def create_memory_candidate(m: MemoryCreate, user: dict = Depends(require_role("operator"))):
    async with async_session_factory() as s:
        msvc = MemoryService(s)
        item = await msvc.create_candidate(
            content=m.content, source=m.source, confidence=m.confidence,
            category=m.category, ttl_seconds=m.ttl_seconds,
        )
        await s.commit()
        return {"id": str(item.id), "status": item.status}


@app.post("/api/v1/memory/{memory_id}/decision")
async def decide_memory(memory_id: str, d: dict, user: dict = Depends(require_role("admin"))):
    try:
        uid = uuid.UUID(memory_id)
    except ValueError:
        raise HTTPException(400, "memory id geçersiz") from None
    action = d.get("decision")  # approve | reject | activate | supersede
    async with async_session_factory() as s:
        msvc = MemoryService(s)
        item = await s.get(models.MemoryItem, uid)
        if item is None:
            raise HTTPException(404, "kayıt yok")
        if action in ("approve", "activate"):
            await msvc.mark_active(uid)
        elif action == "reject":
            await msvc.reject(uid)
        else:
            raise HTTPException(400, "bilinmeyen decision")
        await s.commit()
        return {"id": memory_id, "status": action}


# ---------------------------------------------------------------------------
# Sources / Reports / Technocore
# ---------------------------------------------------------------------------
@app.get("/api/v1/sources")
async def list_sources():
    async with async_session_factory() as s:
        res = await s.execute(select(models.Source).order_by(models.Source.name))
        return [{"id": str(x.id), "name": x.name, "source_type": x.source_type,
                 "is_enabled": x.is_enabled, "last_accessed_at": x.last_accessed_at.isoformat() if x.last_accessed_at else None,
                 "error_series_len": len(x.error_series)} for x in res.scalars().all()]


@app.get("/api/v1/reports")
async def list_reports(limit: int = 20):
    async with async_session_factory() as s:
        res = await s.execute(select(models.Report).order_by(models.Report.created_at.desc()).limit(limit))
        return [{"id": str(r.id), "report_type": r.report_type, "subject": r.subject,
                 "confidence": r.confidence, "created_at": r.created_at.isoformat(),
                 "summary": r.summary} for r in res.scalars().all()]


@app.get("/api/v1/technocore")
async def technocore_status():
    return {"base_url": settings.TECHNOCORE_BASE_URL,
            "room_claim": settings.TECHNOCORE_ROOM_CLAIM, "registered": False}


@app.get("/api/v1/settings/non-secret")
async def settings_non_secret(user: dict = Depends(get_current_user)):
    return {
        "app_env": settings.APP_ENV,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "llm_base_url": settings.LLM_BASE_URL,
        "telegram_allowed_user_ids_count": len(settings.allowed_user_ids),
        "telegram_group_enabled": settings.TELEGRAM_GROUP_ENABLED,
        "technocore_base_url": settings.TECHNOCORE_BASE_URL,
        "run_max_iterations": settings.RUN_MAX_ITERATIONS,
        "run_max_wall_seconds": settings.RUN_MAX_WALL_SECONDS,
        # secret DEĞERLERİ asla dönmez; yalnız configured/valid durumu:
        "telegram_token_configured": bool(settings.TELEGRAM_BOT_TOKEN),
        "llm_key_configured": bool(settings.LLM_API_KEY),
    }


# ---------------------------------------------------------------------------
# SSE — gerçek zamanlı event stream (Last-Event-ID destekli)
# ---------------------------------------------------------------------------
@app.get("/api/v1/events/stream")
async def events_stream(request: Request):
    # Last-Event-ID: header öncelikli, fallback query param (?lastEventId / ?last_event_id)
    last_event_id = (
        request.headers.get("Last-Event-ID")
        or request.headers.get("last-event-id")
        or request.query_params.get("lastEventId")
        or request.query_params.get("last_event_id")
        or ""
    )
    try:
        last_seq = int(last_event_id) if last_event_id.strip().isdigit() else 0
    except Exception:
        last_seq = 0

    async def gen():
        import asyncio as _a
        cur = last_seq  # global_seq cursor (global monoton, run içi seq değil)
        yield "retry: 3000\n\n"
        try:
            while True:
                async with async_session_factory() as s:
                    q = (select(models.RunEvent)
                         .where(models.RunEvent.global_seq > cur)
                         .order_by(models.RunEvent.global_seq.asc())
                         .limit(50))
                    res = await s.execute(q)
                    rows = list(res.scalars().all())
                    if rows:
                        for e in rows:
                            cur = max(cur, int(e.global_seq))
                            payload = {"global_seq": e.global_seq, "seq": e.seq,
                                       "event_type": e.event_type, "ts": e.ts.isoformat(),
                                       "run_id": str(e.run_id)}
                            yield f"id: {e.global_seq}\ndata: {json.dumps(payload, default=str)}\n\n"
                    else:
                        yield f": keepalive {datetime.now(UTC).isoformat()}\n\n"
                await _a.sleep(2)
        except asyncio.CancelledError:
            return
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={
                                 "Cache-Control": "no-cache",
                                 "Connection": "keep-alive",
                                 "X-Accel-Buffering": "no",
                             })


# ---------------------------------------------------------------------------
# Telegram webhook (opaque path + mandatory secret header + BIGINT dedup)
# ---------------------------------------------------------------------------
def _expected_opaque_paths() -> set[str]:
    sec = settings.TELEGRAM_WEBHOOK_SECRET or ""
    if not sec:
        return set()
    # düz secret ve hash'i kabul — hash brute-force'u önler, düz secret geriye uyum
    h = hashlib.sha256(sec.encode()).hexdigest()
    return {sec, h[:32], h, hashlib.sha256(sec.encode()).hexdigest()[:16]}


@app.post("/webhooks/telegram/{opaque_path}")
async def telegram_webhook(opaque_path: str, request: Request):
    # 1) opaque path zorunlu — secret sızsa bile path bilinmeden atılmaz
    expected = _expected_opaque_paths()
    if expected and opaque_path not in expected:
        raise HTTPException(404, "webhook path bulunamadı")
    if not expected:
        # secret yapılandırılmamışsa webhook kapalı
        raise HTTPException(404, "webhook yapılandırılmamış")
    # 2) secret header ZORUNLU (P58 fail-fast dengi) — boş header ile geçiş YOK
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secret or secret != settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(403, "invalid webhook secret")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "geçersiz JSON") from None

    update_id = body.get("update_id")
    rec_id = int(update_id) if isinstance(update_id, int) else None
    # BIGINT durable inbox: PENDING kaydı (dedup + retry için)
    if rec_id is not None:
        try:
            async with async_session_factory() as s:
                existing = await s.get(models.TelegramUpdate, rec_id)
                if existing is not None and existing.status == "PROCESSED":
                    return {"ok": True, "dedup": True, "update_id": update_id}
                if existing is None:
                    payload_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:64]
                    s.add(models.TelegramUpdate(update_id=rec_id, payload_hash=payload_hash, status="PENDING"))
                    await s.commit()
        except Exception as e:
            if "uq_tg_update_id" in str(e) or "UniqueViolation" in str(e) or "duplicate" in str(e).lower():
                return {"ok": True, "dedup": True, "update_id": update_id}
            log.warning("telegram dedup DB hata: %s", redact(str(e)))

    # gerçekten işle (singleton) — işlenmeden PROCESSED sayılmaz
    from agent_core.telegram import get_service
    tg = get_service()
    try:
        await tg.handle_raw_update(body)
    except Exception as e:
        log.warning("telegram handle hata: %s", redact(str(e)))
        if rec_id is not None:
            try:
                async with async_session_factory() as s:
                    r2 = await s.get(models.TelegramUpdate, rec_id)
                    if r2 is not None:
                        r2.status = "FAILED"
                        r2.attempt_count = (r2.attempt_count or 0) + 1
                        await s.commit()
            except Exception:
                pass
        # 500 dön ki Telegram retry etsin
        return JSONResponse({"ok": False, "error": "processing_failed"}, status_code=500)

    # başarılı → PROCESSED
    if rec_id is not None:
        try:
            async with async_session_factory() as s:
                r2 = await s.get(models.TelegramUpdate, rec_id)
                if r2 is not None:
                    r2.status = "PROCESSED"
                    r2.attempt_count = (r2.attempt_count or 0) + 1
                    r2.processed_at = datetime.now(UTC)
                    await s.commit()
        except Exception:
            pass

    return {"ok": True, "update_id": update_id}


# ---------------------------------------------------------------------------
# Root / UI
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    # UI build varsa onu servis et; yoksa basit durum sayfası
    import os as _os
    dist_index = "/srv/raptor/apps/web/dist/index.html"
    candidate = "apps/web/dist/index.html"
    built = _os.path.exists(dist_index) or _os.path.exists(candidate)
    if built:
        try:
            # dist'i api container'ın çalışma dizininden bul
            from pathlib import Path
            txt = (Path(candidate).read_text() if Path(candidate).exists() else Path(dist_index).read_text())
            return HTMLResponse(txt)
        except Exception:
            pass
    return HTMLResponse("""
    <html><head><title>RAPTOR Agentic Observatory</title></head>
    <body style="font-family:sans-serif;background:#0d1421;color:#e8eefc;display:flex;align-items:center;justify-content:center;height:100vh">
      <div style="text-align:center">
        <h1>🐦 RAPTOR Agentic Observatory</h1>
        <p>API çalışıyor. UI build'i dist'te değil.</p>
        <p><code>/health/live</code> · <code>/health/ready</code> · <code>/docs</code></p>
      </div>
    </body></html>
    """)


@app.get("/assets/{path:path}")
async def assets(path: str):
    import os as _os

    from fastapi.responses import FileResponse
    for base in ("apps/web/dist", "/srv/raptor/apps/web/dist"):
        p = f"{base}/assets/{path}"
        if _os.path.exists(p):
            return FileResponse(p)
    raise HTTPException(404)
```

## `apps/migrate/Dockerfile`

```txt
# RAPTOR — one-shot migration servisi (API migration çalıştırmaz; web build yok)
ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}

RUN groupadd -g 10001 raptor && useradd -u 10001 -g raptor -s /usr/sbin/nologin raptor

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/raptor

COPY packages/requirements-api.txt /srv/raptor/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY packages/ /srv/raptor/
COPY migrations/ migrations/

USER raptor
CMD ["sh", "-c", "alembic -c migrations/alembic.ini upgrade head"]

```

## `apps/scheduler/Dockerfile`

```txt
FROM python:3.12-slim@sha256:7a8b475003c4fe15a2cd4e55e5cfc2f3560bdc9333d624f24cdd6d4340fd7a17

RUN groupadd -g 10001 raptor && useradd -u 10001 -g raptor -s /usr/sbin/nologin raptor
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/raptor
COPY packages/requirements-scheduler.txt /srv/raptor/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY packages/ /srv/raptor/
COPY apps/scheduler/ /srv/raptor/apps/scheduler/
USER raptor
EXPOSE 8002
CMD ["uvicorn", "apps.scheduler.scheduler:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]
```

## `apps/scheduler/__init__.py`

```py

```

## `apps/scheduler/scheduler.py`

```py
# RAPTOR — Scheduler
# Gerçek işler: kaynak tarama + görev oluşturma, outbox publisher, stuck-run recovery, heartbeat
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import select

from observability import models
from observability.config import settings
from observability.db import async_session_factory

app = FastAPI(title="RAPTOR Scheduler", version="1.0.0")


@app.get("/health/live")
async def health_live():
    return {"status": "live"}


class SchedulerLoop:
    def __init__(self, interval_seconds: int = 60) -> None:
        import redis as redis_lib
        self.redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        self.interval = interval_seconds
        self._stuck_threshold = timedelta(minutes=15)
        self._lease_ms = 30000

    async def publish_outbox(self) -> int:
        """Outbox publisher: unprocessed messages -> Redis Streams (reliable)."""
        published = 0
        async with async_session_factory() as s:
            res = await s.execute(
                select(models.OutboxMessage)
                .where(models.OutboxMessage.processed.is_(False))
                .order_by(models.OutboxMessage.created_at.asc())
                .limit(20)
            )
            msgs = list(res.scalars().all())
            for m in msgs:
                if m.attempts > 10:
                    continue
                try:
                    from observability.queue import ensure_stream_group, publish_to_stream
                    try:
                        ensure_stream_group(self.redis)
                    except Exception:
                        pass
                    stream_id = publish_to_stream(self.redis, m.payload, idempotency_key=m.idempotency_key)
                    m.processed = True
                    m.processed_at = datetime.now(UTC)
                    m.stream_id = str(stream_id)
                    m.attempts += 1
                    published += 1
                except Exception as e:
                    m.attempts += 1
                    m.last_error = f"{type(e).__name__}: {str(e)[:300]}"
            if published or msgs:
                await s.commit()
        return published

    async def recover_stuck_runs(self) -> int:
        """Stuck-run recovery: EXECUTING runs with heartbeat/lease expired -> FAILED + requeue."""
        recovered = 0
        cutoff = datetime.now(UTC) - self._stuck_threshold
        async with async_session_factory() as s:
            # also consider lease_expires_at
            res = await s.execute(
                select(models.Run).where(
                    models.Run.status == models.RunStatus.EXECUTING.value,
                )
            )
            runs = list(res.scalars().all())
            for r in runs:
                heartbeat = r.heartbeat_at or r.updated_at
                lease_expired = r.lease_expires_at and r.lease_expires_at < datetime.now(UTC)
                stuck = (heartbeat and heartbeat < cutoff) or lease_expired
                if not stuck:
                    continue
                # mark failed and emit event, then requeue via outbox if retry budget remains
                r.status = models.RunStatus.FAILED.value
                r.error = "stuck_run_recovered"
                r.finished_at = datetime.now(UTC)
                r.heartbeat_at = datetime.now(UTC)
                seq_max = 0
                try:
                    # get max seq for run
                    from sqlalchemy import func
                    q = await s.execute(select(func.max(models.RunEvent.seq)).where(models.RunEvent.run_id == r.id))
                    seq_max = int(q.scalar() or 0)
                except Exception:
                    seq_max = 0
                s.add(models.RunEvent(run_id=r.id, seq=seq_max + 1, event_type="STUCK_RECOVERED", payload={"reason": "lease_expired", "worker_id": r.worker_id}))
                # retry_count artır + DLQ/requeue kararı
                retry = (r.retry_count or 0) + 1
                r.retry_count = retry
                if retry > 3:
                    # max retry aşıldı → DLQ
                    try:
                        from observability.queue import publish_to_dlq
                        publish_to_dlq(self.redis, {"run_id": str(r.id), "task_id": str(r.task_id), "retry_of": str(r.id)},
                                       reason="max_retries_exceeded")
                        s.add(models.RunEvent(run_id=r.id, seq=seq_max + 2, event_type="DLQ", payload={"retry_count": retry}))
                    except Exception:
                        pass
                else:
                    # exponential backoff ile requeue
                    backoff_sec = 30 * (2 ** (retry - 1))  # 30s, 60s, 120s
                    try:
                        new_run = models.Run(
                            task_id=r.task_id,
                            status=models.RunStatus.QUEUED.value,
                            token_budget=r.token_budget,
                            cost_budget=r.cost_budget,
                            retry_count=retry,
                        )
                        s.add(new_run)
                        await s.flush()
                        ob = models.OutboxMessage(
                            topic="raptor.run_queued",
                            payload={"run_id": str(new_run.id), "task_id": str(new_run.task_id), "retry_of": str(r.id)},
                            idempotency_key=f"retry:{r.id}:{new_run.id}",
                            processed=False,
                        )
                        s.add(ob)
                        s.add(models.RunEvent(run_id=new_run.id, seq=0, event_type="RETRY_QUEUED", payload={"from_run": str(r.id), "backoff_sec": backoff_sec}))
                    except Exception:
                        pass
                recovered += 1
            if recovered:
                await s.commit()
        return recovered

    async def check_sources(self) -> int:
        """Gerçek kaynak işleri: etkin kaynaklar için gözlem oluştur, task/run yarat."""
        await self.publish_outbox()
        await self.recover_stuck_runs()
        async with async_session_factory() as s:
            res = await s.execute(select(models.Source).where(models.Source.is_enabled.is_(True)))
            sources = list(res.scalars().all())
            for src in sources:
                # backoff check
                if src.backoff_until and src.backoff_until > datetime.now(UTC):
                    continue
                # for each enabled source, optionally create a surveillance task if no recent run
                # MVP: create a Task+Run+Outbox per source once per scheduler tick if last_accessed_at stale (>1h)
                stale = not src.last_accessed_at or (datetime.now(UTC) - src.last_accessed_at) > timedelta(hours=1)
                if stale:
                    try:
                        # idempotent per source per hour
                        idem = f"source:{src.id}:{datetime.now(UTC).strftime('%Y-%m-%d-%H')}"
                        # check existing task with same idempotency
                        ex = await s.execute(select(models.Task).where(models.Task.idempotency_key == idem))
                        if ex.scalar_one_or_none() is not None:
                            src.last_accessed_at = datetime.now(UTC)
                            continue
                        task = models.Task(
                            title=f"Kaynak gözetimi: {src.name}",
                            prompt=f"Kaynak {src.name} ({src.source_type}) gözetimi: değişiklikleri tara, kanıt topla, rapor üret.",
                            scope={"source_id": str(src.id), "source_type": src.source_type},
                            budget={"max_iterations": 10},
                            idempotency_key=idem,
                        )
                        s.add(task)
                        await s.flush()
                        run = models.Run(task_id=task.id, status=models.RunStatus.QUEUED.value,
                                         token_budget=settings.RUN_MAX_TOKEN_BUDGET,
                                         cost_budget=settings.RUN_MAX_COST_BUDGET)
                        s.add(run)
                        await s.flush()
                        ob = models.OutboxMessage(
                            topic="raptor.run_queued",
                            payload={"run_id": str(run.id), "task_id": str(task.id), "source_id": str(src.id)},
                            idempotency_key=f"run:{run.id}",
                            processed=False,
                        )
                        s.add(ob)
                        s.add(models.RunEvent(run_id=run.id, seq=0, event_type="QUEUED", payload={"source_id": str(src.id)}))
                        src.last_accessed_at = datetime.now(UTC)
                    except Exception:
                        await s.rollback()
                        continue
            if sources:
                try:
                    await s.commit()
                except Exception:
                    await s.rollback()
        return len(sources)

    async def run(self) -> None:
        while True:
            try:
                await self.check_sources()
            except Exception:
                pass
            await asyncio.sleep(self.interval)


_BG_TASKS: list = []


@app.on_event("startup")
async def _start():
    loop = SchedulerLoop(interval_seconds=60)
    _BG_TASKS.append(asyncio.create_task(loop.run()))

```

## `apps/web/Dockerfile`

```txt
# RAPTOR Web — React + TypeScript + Vite (üretim build)
FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ .
ENV VITE_API_BASE=/api VITE_SSE_BASE=/api/v1/events/stream
ARG VITE_API_BASE=/api
ARG VITE_SSE_BASE=/api/v1/events/stream
RUN npm run build

# runtime: static output'u api container'ının mount ettiği volume'e kopyala (build stage)
FROM scratch AS export
COPY --from=build /app/dist /dist
```

## `apps/web/__init__.py`

```py

```

## `apps/web/index.html`

```html
<!doctype html>
<html lang="tr">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>RAPTOR Observatory</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```