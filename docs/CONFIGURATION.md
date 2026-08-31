# CONFIGURATION — RAPTOR

LLM, Telegram and Technocore configuration. All values via `.env` (see `.env.example`).

## LLM Provider Matrix

Single env set controls all providers. `mock` needs no key.

| Provider | `LLM_PROVIDER` | `LLM_BASE_URL` | `LLM_MODEL` | `LLM_API_KEY` |
|---|---|---|---|---|
| **Mock (free)** | `mock` | `https://api.openai.com/v1` | `gpt-4o-mini` | `CHANGE_ME` (ignored) |
| **OpenAI** | `openai_compatible` | `https://api.openai.com/v1` | `gpt-4o-mini` | `sk-...` |
| **OpenRouter** | `openai_compatible` | `https://openrouter.ai/api/v1` | `anthropic/claude-3.5-sonnet` | `sk-or-...` |
| **Ollama (local)** | `openai_compatible` | `http://host.docker.internal:11434/v1` | `llama3.1` | `ollama` |

> `mock` runs the entire agentic loop (planner -> executor -> verifier) with deterministic fixtures.
> Tests and CI use `mock` by default.

### Examples

**1. Mock — no key:**
```bash
LLM_PROVIDER=mock
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

## References

- Env template: `.env.example`
- Setup script: `scripts/configure-secrets.sh --gen`
- Health: `GET /health/live`, `GET /health/ready`
