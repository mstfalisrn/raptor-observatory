# RAPTOR Agentic Observatory

[![CI](https://github.com/your-owner/raptor-observatory/actions/workflows/ci.yml/badge.svg)](https://github.com/your-owner/raptor-observatory/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.0.0-blue)](https://github.com/your-owner/raptor-observatory/releases)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)

## 🚀 Tek Komut Kurulum

> 60 saniyede çalışan stack — her yerde aynı 3 adım. Kopyala: `cp .env.example .env — hiçbir gerçek token yazma`

Kopyala: cp .env.example .env — hiçbir gerçek token yazma
gizli bilgi repo'da yok — ./scripts/secret-scan.sh ile doğrula

```bash
# 1) klonla
git clone https://github.com/your-owner/raptor-observatory.git && cd raptor-observatory

# 2) env — kopyala; mock ile anahtar gerekmez, openai_compatible için LLM_API_KEY doldur
cp .env.example .env  # içi CHANGE_ME — LLM_API_KEY gerekirse düzenle, mock works with no key

# 3) tek komut (idempotent) — CHANGE_ME'leri otomatik üretir ve ayağa kaldırır
./scripts/quickstart.sh
# veya: docker compose up -d --build

# → http://localhost:3525
```

- **İlk giriş:** `ADMIN_EMAIL` (varsayılan `your-email@example.com` / `admin@raptor` alias) + `.env` → `ADMIN_PASSWORD_HASH` — quickstart.sh ilk kurulumda parola üretip log'da gösterir; `ADMIN_PASSWORD_HASH` boşsa `.env`'den oku
- **Önkoşullar:** Docker 24+, Docker Compose v2.20+, 4 GB RAM (8 GB önerilir), 10 GB disk, port `3525` boş
- **Gizli bilgi repo'da yok — `./scripts/secret-scan.sh` ile doğrula** — hiçbir gerçek token commit edilmez; doğrulama: `./scripts/secret-scan.sh .`
- **LLM:** `mock` (ücretsiz, anahtarsız) · `openai_compatible` → OpenAI / OpenRouter / Ollama — bkz. [CONFIGURATION.md](docs/CONFIGURATION.md) matris
- **Sorun mu?** `docker compose logs -f` · `curl -s http://localhost:3525/health/ready | jq` · [INSTALL.md Troubleshooting](docs/INSTALL.md#troubleshooting)

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

> Her yerde aynı 3 adım — aynı komutlar. Kopyala: `cp .env.example .env — hiçbir gerçek token yazma`

Kopyala: cp .env.example .env — hiçbir gerçek token yazma
gizli bilgi repo'da yok — ./scripts/secret-scan.sh ile doğrula

### Public Quickstart (60 sn) — önerilen

```bash
# 1) klonla
git clone https://github.com/your-owner/raptor-observatory.git && cd raptor-observatory

# 2) env — kopyala; mock ile anahtar gerekmez, openai_compatible için LLM_API_KEY doldur
cp .env.example .env  # içi CHANGE_ME — LLM_API_KEY gerekirse düzenle, mock works with no key

# 3) tek komut (idempotent) — CHANGE_ME'leri otomatik üretir ve ayağa kaldırır
./scripts/quickstart.sh
# veya: docker compose up -d --build

# → http://localhost:3525
# ilk giriş: ADMIN_EMAIL (your-email@example.com) + .env → ADMIN_PASSWORD_HASH (quickstart log'da parola gösterilir)
```

Tarayıcıda aç: **http://localhost:3525** — prod tünel (opsiyonel): `https://raptor.your-domain.example`

> `LLM_PROVIDER=mock` ile API anahtarı olmadan da otonom loop çalışır (ücretsiz test).
> gizli bilgi repo'da yok — `./scripts/secret-scan.sh` ile doğrula — `./scripts/secret-scan.sh .`
> Önkoşullar: Docker 24+, 4 GB RAM, 10 GB disk, port 3525 boş — detay: [docs/INSTALL.md](docs/INSTALL.md)

### Production (managed) — `./secrets` ile

Sunucuda Hermes-managed kurulum için secret'lar `./secrets/raptor-observatory/app.env` içinde tutulur:

```bash
# 1) secret'lar (root-only)
./scripts/configure-secrets.sh --gen        # otomatik üret
./scripts/configure-secrets.sh              # interaktif (TG bot + LLM key)

# 2) compose env
cp .env.example .env                         # üretimde değerleri ./secrets/raptor-observatory/app.env dosyasından aktar
# POSTGRES_PASSWORD, JWT_SECRET, SESSION_ENCRYPTION_MASTER_KEY, TELEGRAM_WEBHOOK_SECRET ...

# 3) stack
docker compose up -d --build
./scripts/secret-scan.sh .                   # secret taraması

# 4) test
pytest
```

## AI API Bağlama (LLM Provider)

Tek env seti — `mock` veya herhangi bir OpenAI-compatible sağlayıcı:

| Alan | Env Değişkeni | Açıklama |
|---|---|---|
| Provider | `LLM_PROVIDER` | `mock` (ücretsiz / test) veya `openai_compatible` |
| Base URL | `LLM_BASE_URL` | OpenAI-compatible endpoint |
| Model | `LLM_MODEL` | Kullanılacak model adı |
| API Key | `LLM_API_KEY` | Sağlayıcı API anahtarı (`mock` için `CHANGE_ME` kalabilir) |

### Örnekler

| Sağlayıcı | `LLM_PROVIDER` | `LLM_BASE_URL` | `LLM_MODEL` | `LLM_API_KEY` |
|---|---|---|---|---|
| **Mock (ücretsiz)** | `mock` | `https://api.openai.com/v1` | `gpt-4o-mini` | `CHANGE_ME` |
| **OpenAI** | `openai_compatible` | `https://api.openai.com/v1` | `gpt-4o-mini` | `sk-...` |
| **OpenRouter** | `openai_compatible` | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` | `sk-or-...` |
| **Ollama (local)** | `openai_compatible` | `http://localhost:11434/v1` | `llama3.1` | `ollama` veya `CHANGE_ME` |

```bash
# .env — OpenAI örneği
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...

# .env — OpenRouter örneği
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openai/gpt-4o-mini
LLM_API_KEY=sk-or-...

# .env — Ollama (yerel) örneği
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.1
LLM_API_KEY=ollama
```

> Bağlantıyı test et: `curl -s http://localhost:3525/health/ready | jq` ve UI → Settings → LLM Test (`POST /api/v1/settings/llm/test`).

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
