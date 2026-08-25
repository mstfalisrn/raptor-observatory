#!/usr/bin/env bash
# RAPTOR — secret scan v2 (yalnız yüksek güvenilirlikli gerçek değerler)
# Exit: gerçek sır bulunduysa 1, temizse 0. Değişken referansı = false positive, atlanır.
set -uo pipefail
ROOT="${1:-.}"
cd "$ROOT" || exit 2

# Yüksek güvenilirlikli gerçek değer kalıpları (literal token/credentials)
STRONG=(
  'TELEGRAM_BOT_TOKEN[=: ]+[0-9]{6,}:[A-Za-z0-9_-]{30,}'   # gerçek TG token
  'mongodb(\+srv)?://[^: ]+:[^@ ]+@[^: ]+'               # gerçek DB creds
  '\bgh[pousr]_[A-Za-z0-9]{20,}\b'                        # GitHub token
  '\bsk(-[A-Za-z0-9]{8,}){2,}\b'                          # OpenAI-style
  'LLM_API_KEY[=: ]+[A-Za-z0-9_-]{24,}'                  # gerçek LLM key
  'JWT_SECRET[=: ]+(ey|sha|CHANGE_ME|dev-|[A-Fa-f0-9]{40,})' # sadece gerçek uzun
)

hits=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  # test fixture'larındaki kasıtlı örnekleri atla (Authorization: Bearer abc... testi)
  echo "$f" | grep -q 'test_policy' && continue
  # değişken referansı / placeholder / boş değer ise atla (false positive)
  grep -qE '\$\{[A-Z_]*\}|os\.environ|settings\.' "$f" 2>/dev/null && continue
  for pat in "${STRONG[@]}"; do
    if grep -qE "$pat" "$f" 2>/dev/null; then
      echo "⚠️  GERÇEK SIR ADAYI: $f"
      grep -nE "$pat" "$f" 2>/dev/null | head -1 | sed -E 's/([0-9]{6,}:[A-Za-z0-9_-]{30,}|mongodb(\+srv)?:\/\/[^@]+@|sk-[A-Za-z0-9]{8,}[A-Za-z0-9_-]*|[A-Za-z0-9_-]{30,})/<MASKED>/g'
      hits=1
    fi
  done
done < <(find . -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' -o -name '*.sh' -o -name '*.yml' -o -name '*.yaml' -o -name '*.json' -o -name '*.md' -o -name '*.ini' \) \
    -not -path '*/.git/*' -not -path '*/.venv/*' -not -path '*/node_modules/*' -not -path '*/dist/*' \
    -not -path '*/.pytest_cache/*' -not -path '*/instance/*' 2>/dev/null )

# gerçek secret dosyalarını hiçbir zaman commit etmediğimizden emin ol
if find . -name 'app.env' -not -path '*/.git/*' 2>/dev/null | grep -q .; then
  echo "❌ REPO İÇİNDE app.env VAR — commit etme!"
  hits=1
fi

if [ "$hits" = "0" ]; then
  echo "✅ Secret scan temiz: repo'da gerçek credential yok."
else
  echo "❌ Secret scan: gerçek sır adayı bulundu — commit'i DURDUR."
  exit 1
fi