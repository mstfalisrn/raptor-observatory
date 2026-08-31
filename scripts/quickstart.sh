#!/usr/bin/env bash
# RAPTOR Agentic Observatory — one-command quickstart
# Usage: ./scripts/quickstart.sh  (run from repo root or via path)
# Idempotent: existing .env is preserved; only CHANGE_ME placeholders are replaced.
set -euo pipefail

# Resolve repo root (script is at <root>/scripts/quickstart.sh)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

# 1) Ensure .env exists (do not overwrite existing)
# Spec behavior: [ -f .env ] || cp .env.example .env
[ -f .env ] || cp .env.example .env
if [ ! -f .env ]; then
  echo "❌ .env.example not found at ${ROOT}/.env.example" >&2
  exit 1
fi
if [ -f .env ]; then
  # Distinguish creation vs preservation for UX (cp above is idempotent)
  if grep -q "CHANGE_ME" .env 2>/dev/null; then
    : # placeholders remain — will be replaced below
  fi
fi
# Friendly log (check if we just created it by comparing mtime? simpler: check if .env was just copied)
# We already handled cp; emit status:
if [ -f .env ]; then
  # Heuristic: if .env mtime is very recent (<5s) and we just did cp, assume created
  # Simpler: just state exists
  echo "✓ .env ready at ${ROOT}/.env"
fi

# Helper: generate 32 bytes hex (64 chars) — openssl preferred, fallback to /dev/urandom
gen_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  elif [ -r /dev/urandom ]; then
    head -c 32 /dev/urandom | od -A n -t x1 | tr -d ' \n'
  else
    echo "❌ No openssl or /dev/urandom available to generate secrets" >&2
    exit 1
  fi
}

replace_if_placeholder() {
  local var="$1"
  if grep -q "${var}=CHANGE_ME" .env; then
    local val
    val="$(gen_hex)"
    # Replace only the token CHANGE_ME, preserving trailing comments/whitespace
    sed -i "s/${var}=CHANGE_ME/${var}=${val}/" .env
    echo "✓ Generated ${var}"
  fi
}

replace_if_placeholder "JWT_SECRET"
replace_if_placeholder "SESSION_ENCRYPTION_MASTER_KEY"
replace_if_placeholder "TELEGRAM_WEBHOOK_SECRET"
replace_if_placeholder "POSTGRES_PASSWORD"

# Sync DATABASE_URL password if it still contains CHANGE_ME (keep DB URL consistent with POSTGRES_PASSWORD)
if grep -q "DATABASE_URL=.*CHANGE_ME" .env; then
  _pw="$(grep -E '^POSTGRES_PASSWORD=' .env | cut -d= -f2- | awk '{print $1}' | tail -n1 || true)"
  if [ -n "${_pw:-}" ] && [ "${_pw}" != "CHANGE_ME" ]; then
    sed -i "s|postgresql+psycopg://raptor:CHANGE_ME@|postgresql+psycopg://raptor:${_pw}@|" .env || true
    if grep -q "DATABASE_URL=.*CHANGE_ME" .env; then
      sed -i "/^DATABASE_URL=/ s/CHANGE_ME/${_pw}/" .env || true
    fi
    echo "✓ Synced DATABASE_URL with POSTGRES_PASSWORD"
  fi
  unset _pw
fi

echo "→ docker compose up -d --build"
docker compose up -d --build

if [ -x ./scripts/secret-scan.sh ]; then
  ./scripts/secret-scan.sh . || true
else
  echo "⚠️  scripts/secret-scan.sh not found or not executable — skipping scan" >&2
fi

echo "→ http://localhost:3525"
