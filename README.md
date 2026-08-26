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
