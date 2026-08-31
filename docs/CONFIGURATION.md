# CONFIGURATION — RAPTOR

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
# ilk giriş: ADMIN_EMAIL (your-email@example.com) + .env → ADMIN_PASSWORD_HASH
# gizli bilgi repo'da yok — ./scripts/secret-scan.sh ile doğrula
```

- **Önkoşullar:** Docker 24+, 4 GB RAM, 10 GB disk, port 3525 boş — detay: [INSTALL.md](INSTALL.md#prerequisites)
- **Doğrulama:** `./scripts/secret-scan.sh .` ve `curl -s http://localhost:3525/health/ready | jq`

LLM, Telegram and Technocore configuration. All values via `.env` (see `.env.example`). Kopyala: `cp .env.example .env — hiçbir gerçek token yazma`

## LLM Provider Matrix

Single env set controls all providers. `mock` needs no key. gizli bilgi repo'da yok — `./scripts/secret-scan.sh` ile doğrula

| Provider | `LLM_PROVIDER` | `LLM_BASE_URL` | `LLM_MODEL` | `LLM_API_KEY` |
|---|---|---|---|---|
| **Mock (free)** | `mock` | `https://api.openai.com/v1` | `gpt-4o-mini` | `CHANGE_ME` (ignored) |
| **OpenAI** | `openai_compatible` | `https://api.openai.com/v1` | `gpt-4o-mini` | `sk-...` |
| **OpenRouter** | `openai_compatible` | `https://openrouter.ai/api/v1` | `anthropic/claude-3.5-sonnet` | `sk-or-...` |
| **Ollama (local)** | `openai_compatible` | `http://host.docker.internal:11434/v1` | `llama3.1` | `ollama` |

> `mock` runs the entire agentic loop (planner -> executor -> verifier) with deterministic fixtures.
> Tests and CI use `mock` by default.
> Kopyala: `cp .env.example .env — hiçbir gerçek token yazma` — mock ile anahtarsız çalışır.

### Examples

**1. Mock — no key:**
```bash
LLM_PROVIDER=mock
# LLM_API_KEY=CHANGE_ME kalabilir — mock ignores it
# Kurulum: cp .env.example .env — hiçbir gerçek token yazma — sonra ./scripts/quickstart.sh → http://localhost:3525
```

**2. OpenAI:**
```bash
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-proj-...
```

**3. OpenRouter (Anthropic via OpenRouter):**
```bash
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=anthropic/claude-3.5-sonnet
LLM_API_KEY=sk-or-v1-...
# Optional: OpenRouter wants HTTP-Referer / X-Title headers — set via provider config if needed.
```

**4. Ollama (local Docker):**
```bash
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=llama3.1
LLM_API_KEY=ollama
# Linux: replace host.docker.internal with host gateway IP (e.g. 172.17.0.1) if needed.
# Ensure: ollama serve && ollama pull llama3.1
```

Verify: `POST /api/v1/settings/llm/test` (Settings -> LLM Test) or `curl -s http://127.0.0.1:3525/health/ready`.

## İlk Giriş

- **URL:** http://localhost:3525
- **E-posta:** `ADMIN_EMAIL` (varsayılan `your-email@example.com`) — `.env` → `ADMIN_EMAIL`
- **Parola:** `.env` → `ADMIN_PASSWORD_HASH` (PBKDF2) — quickstart.sh `CHANGE_ME` ise otomatik üretir ve log'da gösterir; gizli bilgi repo'da yok — `./scripts/secret-scan.sh` ile doğrula

## Telegram

| Variable | Example | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `123456:AAF...` | From @BotFather; leave empty to disable |
| `TELEGRAM_ALLOWED_USER_IDS` | `12345678,987654321` | Numeric IDs only; `*`/empty = deny all |
| `TELEGRAM_WEBHOOK_SECRET` | 64 hex | X-Telegram-Bot-Api-Secret-Token verified |
| `TELEGRAM_GROUP_ENABLED` | `false` | Group mode off by default |

Webhook path is opaque: `/webhooks/telegram/<opaque>` — never log token/path.

## Technocore

| Variable | Default | Notes |
|---|---|---|
| `TECHNOCORE_BASE_URL` | `https://technocore.chat` | API base |
| `TECHNOCORE_ROOM_CLAIM` | `dm-topic` | Default room for read/write |

Reads occur every 5 min (scheduler). Writes are DID-signed and gated behind approval (`PUBLIC-POST-APPROVED`).

## Önkoşullar & Doğrulama

| Requirement | Minimum |
|---|---|
| Docker Engine | 24+ |
| RAM | 4 GB (8 GB önerilir) |
| Disk | 10 GB |
| Port | 3525 boş |

```bash
docker --version && docker compose version
./scripts/secret-scan.sh .        # gizli bilgi repo'da yok — ./scripts/secret-scan.sh ile doğrula
curl -s http://localhost:3525/health/ready | jq
docker compose logs -f
```

## Troubleshooting

| Sorun | Çözüm |
|---|---|
| `3525 in use` | `ss -tlnp \| grep 3525` veya `GATEWAY_PORT=3526 docker compose up -d` |
| `password authentication failed` | `grep POSTGRES_PASSWORD .env` ile `DATABASE_URL` eşleşmeli — quickstart.sh otomatik sync eder |
| `secret-scan` fail | `git rm --cached .env` — hiçbir gerçek token commit etme |
| LLM 401/403 | `LLM_API_KEY` / `LLM_BASE_URL` kontrol — mock ile test et |
| Login başarısız | `ADMIN_EMAIL` / `ADMIN_PASSWORD_HASH` kontrol — quickstart log'daki parola |

## References

- Env template: `.env.example` — Kopyala: `cp .env.example .env — hiçbir gerçek token yazma`
- Setup script: `scripts/quickstart.sh` (idempotent) veya `docker compose up -d --build` → http://localhost:3525
- Setup script (prod): `scripts/configure-secrets.sh --gen`
- Health: `GET /health/live`, `GET /health/ready`
- Secret scan: `./scripts/secret-scan.sh .` — gizli bilgi repo'da yok — `./scripts/secret-scan.sh` ile doğrula
