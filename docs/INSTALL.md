# INSTALL — RAPTOR Agentic Observatory

> Public quickstart — 60 seconds to running stack. MIT Licensed.
> Her yerde aynı 3 adım — Kopyala: `cp .env.example .env — hiçbir gerçek token yazma` — gizli bilgi repo'da yok — `./scripts/secret-scan.sh` ile doğrula

## 🚀 3 Adımda Kurulum (her yerde aynı)

```bash
# 1) klonla
git clone https://github.com/your-owner/raptor-observatory.git && cd raptor-observatory

# 2) env — kopyala; mock ile anahtar gerekmez, openai_compatible için LLM_API_KEY doldur
cp .env.example .env  # içi CHANGE_ME — LLM_API_KEY gerekirse düzenle, mock works with no key

# 3) tek komut (idempotent) — CHANGE_ME'leri otomatik üretir ve ayağa kaldırır
./scripts/quickstart.sh
# veya: docker compose up -d --build

# → http://localhost:3525
# ilk giriş: ADMIN_EMAIL (your-email@example.com / admin@raptor) + .env → ADMIN_PASSWORD_HASH (quickstart log'da parola gösterilir)
# gizli bilgi repo'da yok — ./scripts/secret-scan.sh ile doğrula
```

> Detaylı LLM matris için: [CONFIGURATION.md](CONFIGURATION.md) — `mock` (ücretsiz) · `openai_compatible` → OpenAI / OpenRouter / Ollama

## İlk Giriş

- **URL:** http://localhost:3525 (gateway `127.0.0.1:3525`)
- **E-posta:** `ADMIN_EMAIL` — varsayılan `your-email@example.com` (`.env`'de `ADMIN_EMAIL`) — `admin@raptor` alias de kabul
- **Parola:** `.env` → `ADMIN_PASSWORD_HASH` — quickstart.sh `CHANGE_ME` ise random parola üretir ve log'da tek sefer gösterir (`→ Kaydet: admin e-posta=... parola=...`). Sonra `docker compose logs -f` ile tekrar bakmayın — `.env`'deki hash ile doğrulayın. Varsayılan yoksa yeni hash üretin: `python3 -c "import hashlib,os;pw=input('parola: ');s=os.urandom(16);print(f'pbkdf2_sha256\$240000\${s.hex()}\${hashlib.pbkdf2_hmac(\"sha256\",pw.encode(),s,240000).hex()}')"`
- **Doğrulama:** `curl -s http://localhost:3525/health/ready | jq` ve UI → Settings → LLM Test

> gizli bilgi repo'da yok — `./scripts/secret-scan.sh` ile doğrula

## Prerequisites

| Requirement | Minimum | Notes |
|---|---|---|
| Docker Engine | 24+ | `docker --version` — Compose V2 bundled |
| Docker Compose | v2.20+ | `docker compose version` (plugin, not `docker-compose`) |
| RAM | 4 GB | 8 GB recommended (PG + Redis + API + Worker) |
| Disk | 10 GB free | pgvector image + build cache |
| OS | Linux x86_64 / macOS | Tested on Ubuntu 22.04 / 24.04 |
| Ports | `3525` free | Only host bind is `127.0.0.1:3525` (gateway) |
| Python | 3.12 | Only for local tests outside Docker |

Check ports / docker:
```bash
docker --version && docker compose version
ss -tlnp | grep 3525 || echo "port 3525 free"
free -h && df -h .
```

## Quickstart (detay)

```bash
# 1) clone
git clone https://github.com/your-owner/raptor-observatory.git && cd raptor-observatory

# 2) env — copy and fill secrets (CHANGE_ME placeholders)
cp .env.example .env  # hiçbir gerçek token yazma — gizli bilgi repo'da yok — ./scripts/secret-scan.sh ile doğrula
# Edit .env — at minimum fill (quickstart.sh CHANGE_ME ise otomatik üretir):
#   POSTGRES_PASSWORD, JWT_SECRET, SESSION_ENCRYPTION_MASTER_KEY, TELEGRAM_WEBHOOK_SECRET, ADMIN_PASSWORD_HASH
#   LLM_PROVIDER=mock            # free, no key needed — mock works with no key
#   # or: LLM_PROVIDER=openai_compatible + LLM_BASE_URL + LLM_MODEL + LLM_API_KEY
nano .env  # or vim

# 3a) one-command quickstart (idempotent — generates hex secrets if CHANGE_ME remains)
./scripts/quickstart.sh
# → http://localhost:3525  admin: your-email@example.com  logs: docker compose logs -f

# 3b) OR manual compose
# docker compose up -d --build

# 4) verify
./scripts/secret-scan.sh .        # must be clean — gizli bilgi repo'da yok — ./scripts/secret-scan.sh ile doğrula
curl -s http://127.0.0.1:3525/health/live | jq
curl -s http://127.0.0.1:3525/health/ready | jq
```

Open **http://localhost:3525** -> login (local auth) -> Dashboard. İlk giriş: `ADMIN_EMAIL` / `ADMIN_PASSWORD_HASH` — bkz. İlk Giriş.

> `LLM_PROVIDER=mock` runs the full agentic loop without any API key — useful for local testing.
> Production secrets path: `./secrets/raptor-observatory/app.env` (see `scripts/configure-secrets.sh --gen`).

## LLM Provider (özet)

| Provider | `LLM_PROVIDER` | `LLM_BASE_URL` | `LLM_MODEL` | `LLM_API_KEY` |
|---|---|---|---|---|
| **Mock (ücretsiz)** | `mock` | `https://api.openai.com/v1` | `gpt-4o-mini` | `CHANGE_ME` (ignored) |
| **OpenAI** | `openai_compatible` | `https://api.openai.com/v1` | `gpt-4o-mini` | `sk-...` |
| **OpenRouter** | `openai_compatible` | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` | `sk-or-...` |
| **Ollama (local)** | `openai_compatible` | `http://localhost:11434/v1` | `llama3.1` | `ollama` veya `CHANGE_ME` |

Detay: [CONFIGURATION.md](CONFIGURATION.md). Doğrulama: `curl -s http://localhost:3525/health/ready | jq` ve `POST /api/v1/settings/llm/test`.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `APP_ENV` | no | `development` | `development` / `production` / `test` |
| `POSTGRES_USER` | no | `raptor` | PG user |
| `POSTGRES_DB` | no | `raptor` | PG database |
| `POSTGRES_PASSWORD` | **yes** | `CHANGE_ME` | PG password — sync with `DATABASE_URL` |
| `DATABASE_URL` | **yes** | `postgresql+psycopg://raptor:CHANGE_ME@raptor-postgres:5432/raptor` | Async URL uses `postgresql+asyncpg://` in compose |
| `REDIS_URL` | no | `redis://raptor-redis:6379/0` | Redis Streams queue |
| `JWT_SECRET` | **yes** | `CHANGE_ME` | 64 hex chars — `openssl rand -hex 32` |
| `SESSION_ENCRYPTION_MASTER_KEY` | **yes** | `CHANGE_ME` | Session cookie encryption key |
| `TELEGRAM_WEBHOOK_SECRET` | **yes** | `CHANGE_ME` | Webhook header verification |
| `TELEGRAM_BOT_TOKEN` | optional | — | Leave empty if not using Telegram |
| `TELEGRAM_ALLOWED_USER_IDS` | optional | — | Comma-separated numeric IDs; `*`/empty = closed |
| `ADMIN_EMAIL` | no | `your-email@example.com` | İlk giriş e-postası |
| `ADMIN_PASSWORD_HASH` | **yes** | `CHANGE_ME` | PBKDF2 hash — quickstart.sh otomatik üretir |
| `LLM_PROVIDER` | no | `mock` | `mock` or `openai_compatible` |
| `LLM_BASE_URL` | if `openai_compatible` | `https://api.openai.com/v1` | OpenAI-compatible endpoint |
| `LLM_MODEL` | if `openai_compatible` | `gpt-4o-mini` | Model id |
| `LLM_API_KEY` | if `openai_compatible` | `CHANGE_ME` | Provider key (ignored for `mock`) |
| `RUN_MAX_ITERATIONS` | no | `40` | Agentic loop budget |
| `RUN_MAX_WALL_SECONDS` | no | `900` | Wall-clock timeout |
| `RUN_MAX_TOKEN_BUDGET` | no | `200000` | Token budget |
| `TECHNOCORE_BASE_URL` | no | `https://technocore.chat` | Technocore API |
| `TECHNOCORE_ROOM_CLAIM` | no | `dm-topic` | Default room |
| `VITE_API_BASE` | no | `/api` | Frontend API prefix (browser-exposed) |

> gizli bilgi repo'da yok — `./scripts/secret-scan.sh` ile doğrula — hiçbir gerçek token `.env.example`'a yazılmaz; `cp .env.example .env — hiçbir gerçek token yazma`

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `port is already allocated` / `3525 in use` | Another process holds 3525 | `ss -tlnp \| grep 3525` -> kill or `GATEWAY_PORT=3526 docker compose up -d` |
| `raptor-postgres` unhealthy / `FATAL: password authentication failed` | `POSTGRES_PASSWORD` vs `DATABASE_URL` mismatch | ensure both use same value; `grep POSTGRES_PASSWORD .env` and `grep DATABASE_URL .env` must align |
| `alembic upgrade head` hangs | PG not healthy yet | `docker logs raptor-postgres` + `docker inspect --format='{{.State.Health.Status}}' raptor-postgres` — wait for `healthy` |
| `secret-scan.sh` fails | Real secret committed or `.env` committed | Remove file, rotate secret, ensure `.env` in `.gitignore`; scan: `./scripts/secret-scan.sh .` |
| `quickstart.sh: docker: command not found` | Docker not installed | Install Docker 24+ and compose plugin |
| `LLM test` returns 401/403 | Wrong `LLM_API_KEY` / base URL | Check `docs/CONFIGURATION.md` matrix; `POST /api/v1/settings/llm/test` in Settings |
| `Login failed` / `geçersiz email veya parola` | Yanlış `ADMIN_EMAIL` / `ADMIN_PASSWORD_HASH` | `grep ADMIN .env` — e-posta ve hash uyumlu mu; quickstart log'daki parolayı dene; hash üret: `python3 -c "import hashlib,os;..."` |
| `gizli bilgi repo'da yok` uyarısı | `.env` commit edildi | `git rm --cached .env` + `.gitignore` kontrol + `./scripts/secret-scan.sh .` |

> Loglar: `docker compose logs -f` — Health: `curl -s http://localhost:3525/health/ready | jq` — Secret taraması: `./scripts/secret-scan.sh .` (gizli bilgi repo'da yok — `./scripts/secret-scan.sh` ile doğrula)

## Next Steps

- LLM providers: [`docs/CONFIGURATION.md`](CONFIGURATION.md)
- UI walkthrough: [`docs/UI_GUIDE.md`](UI_GUIDE.md)
- Full docs: `README.md`, `ARCHITECTURE.md`, `OPERATIONS.md`, `SECURITY.md`
