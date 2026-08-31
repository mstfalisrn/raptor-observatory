# Configuration

All runtime configuration is via environment variables in `.env` (see `.env.example`). LLM, Telegram, and Technocore integrations are configured here.

> Secrets are placeholders — never commit real values. Verify with `./scripts/secret-scan.sh`.

## Quick Start

```bash
# 1) Clone
git clone https://github.com/your-owner/raptor-observatory.git && cd raptor-observatory

# 2) Environment — copy the template (all values are CHANGE_ME placeholders)
cp .env.example .env
# Mock works with no key; for real providers edit LLM_API_KEY below

# 3) Start — idempotent; generates secrets for any remaining CHANGE_ME values
./scripts/quickstart.sh
# -> http://localhost:3525
```

- **Prerequisites:** Docker 24+, 4 GB RAM, 10 GB disk, port 3525 available — see [INSTALL.md](INSTALL.md#prerequisites).
- **Health check:** `curl -s http://localhost:3525/health/ready | jq`
- **Secret scan:** `./scripts/secret-scan.sh .` — must be clean before committing.

## LLM Provider Matrix

A single set of variables controls all providers. `mock` requires no API key and is the default for local development and CI.

| Provider | `LLM_PROVIDER` | `LLM_BASE_URL` | `LLM_MODEL` | `LLM_API_KEY` |
|---|---|---|---|---|
| **Mock (free)** | `mock` | `https://api.openai.com/v1` | `gpt-4o-mini` | `CHANGE_ME` (ignored) |
| **OpenAI** | `openai_compatible` | `https://api.openai.com/v1` | `gpt-4o-mini` | `sk-...` |
| **OpenRouter** | `openai_compatible` | `https://openrouter.ai/api/v1` | `anthropic/claude-3.5-sonnet` | `sk-or-...` |
| **Ollama (local)** | `openai_compatible` | `http://host.docker.internal:11434/v1` | `llama3.1` | `ollama` |

> `mock` runs the entire agentic loop (Planner -> Coordinator -> ToolExecutor -> Verifier -> Reporter) with deterministic fixtures. Tests and CI use `mock` by default.

Verify the provider via **Settings -> LLM Test** (`POST /api/v1/settings/llm/test`) or `curl -s http://127.0.0.1:3525/health/ready | jq`.

### Examples

**1. Mock — no key required:**

```bash
LLM_PROVIDER=mock
# LLM_API_KEY can remain CHANGE_ME — mock ignores it
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
# OpenRouter may require HTTP-Referer / X-Title headers — set via provider config if needed.
```

**4. Ollama (local):**

```bash
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=llama3.1
LLM_API_KEY=ollama
# Linux: replace host.docker.internal with the host gateway IP (e.g. 172.17.0.1) if needed.
# Ensure Ollama is running: ollama serve && ollama pull llama3.1
```

## First Login

| Field | Value |
|---|---|
| URL | `http://localhost:3525` |
| Email | `ADMIN_EMAIL` from `.env` (default `admin@example.com`) |
| Password | The password that hashes to `ADMIN_PASSWORD_HASH` in `.env` |

`quickstart.sh` generates a random password if `ADMIN_PASSWORD_HASH` is still `CHANGE_ME` and prints it once to the log. Save it immediately — subsequent restarts validate against the stored hash.

## Telegram

| Variable | Example | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `123456:AAF...` | From @BotFather; leave empty to disable Telegram |
| `TELEGRAM_ALLOWED_USER_IDS` | `12345678,987654321` | Comma-separated numeric IDs; `*` or empty denies all |
| `TELEGRAM_WEBHOOK_SECRET` | 64 hex chars | Verified via `X-Telegram-Bot-Api-Secret-Token` header |
| `TELEGRAM_GROUP_ENABLED` | `false` | Group mode is off by default |

- Webhook path is opaque: `/webhooks/telegram/<opaque>` — never log the token or path.
- Updates are deduplicated by `update_id` (idempotent inbox).
- To disable Telegram, leave `TELEGRAM_BOT_TOKEN` empty.

## Technocore

| Variable | Default | Notes |
|---|---|---|
| `TECHNOCORE_BASE_URL` | `https://technocore.chat` | API base URL |
| `TECHNOCORE_ROOM_CLAIM` | `dm-topic` | Default room for read/write |

- Reads are polled every 5 minutes by the scheduler.
- Writes are DID-signed and gated behind approval (`PUBLIC-POST-APPROVED`).
- Room history is stored with cursors for incremental sync.

## Other Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `POSTGRES_PASSWORD` | yes | `CHANGE_ME` | Must match `DATABASE_URL` |
| `DATABASE_URL` | yes | `postgresql+psycopg://raptor:CHANGE_ME@raptor-postgres:5432/raptor` | Async variant uses `postgresql+asyncpg://` |
| `REDIS_URL` | no | `redis://raptor-redis:6379/0` | Redis Streams queue |
| `JWT_SECRET` | yes | `CHANGE_ME` | 64 hex chars — `openssl rand -hex 32` |
| `SESSION_ENCRYPTION_MASTER_KEY` | yes | `CHANGE_ME` | Session cookie encryption |
| `RUN_MAX_ITERATIONS` | no | `40` | Agentic loop iteration budget |
| `RUN_MAX_WALL_SECONDS` | no | `900` | Wall-clock timeout (seconds) |
| `RUN_MAX_TOKEN_BUDGET` | no | `200000` | Token budget per run |

See `.env.example` for the full list with comments. All `CHANGE_ME` values are placeholders that `quickstart.sh` replaces with generated secrets if left unchanged.

## Verification & Troubleshooting

```bash
docker --version && docker compose version
./scripts/secret-scan.sh .                          # must be clean
curl -s http://localhost:3525/health/live | jq      # liveness
curl -s http://localhost:3525/health/ready | jq     # readiness (DB + Redis)
docker compose logs -f
```

| Issue | Fix |
|---|---|
| `3525 in use` | `ss -tlnp | grep 3525` or `GATEWAY_PORT=3526 docker compose up -d` |
| `password authentication failed` | `POSTGRES_PASSWORD` and `DATABASE_URL` must use the same value — quickstart syncs them automatically |
| `secret-scan` fails | Remove committed secrets, ensure `.env` is in `.gitignore`; rotate exposed values |
| LLM 401/403 | Check `LLM_API_KEY` / `LLM_BASE_URL` — verify with `mock` first |
| Login failed | Verify `ADMIN_EMAIL` / `ADMIN_PASSWORD_HASH` in `.env` against the quickstart log |

## References

- Environment template: `.env.example`
- Quickstart script: `scripts/quickstart.sh` (idempotent) — `docker compose up -d --build` also works
- Health endpoints: `GET /health/live`, `GET /health/ready`
- Secret scan: `./scripts/secret-scan.sh .`
- Install guide: [INSTALL.md](INSTALL.md)
- UI guide: [UI_GUIDE.md](UI_GUIDE.md)
