# RAPTOR Agentic Observatory

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
| `raptor-postgres` | PostgreSQL 16 + pgvector | yok (internal) |
| `raptor-redis` | kuyruk/koordinasyon | yok (internal) |

Tüm container'lar non-root, read-only rootfs, cap_drop ALL. Host thin tek bind `127.0.0.1:3525`.

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

## Faz durumu

- ✅ Faz 0-6: keşif, scaffold, DB(22 tablo), agent core, kuyruk+worker, Telegram altyapısı,
     Web UI, production stack + systemd + SSE (uçtan uca doğrulandı)
- ✅ Faz 7: DID keypair + protokol hash + imza doğrulaması (public yayın gate'sinde)
- ✅ Faz 8: 23/23 test, secret scan, backup/restore, non-root/read-only/port güvenliği
- ⏳ Faz 7 public kayıt: `PUBLIC-POST-APPROVED` bekler
- ⏳ Canlı Telegram: gerçek bot token ve LLM key gerekir

Daha fazla: [ARCHITECTURE.md](ARCHITECTURE.md) · [SECURITY.md](SECURITY.md) · [OPERATIONS.md](OPERATIONS.md) · [DECISIONS.md](DECISIONS.md)