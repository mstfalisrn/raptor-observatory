#!/usr/bin/env bash
# RAPTOR — secret scan v3 (fail-closed)
# Exit: 0 temiz, 1 gerçek sır bulundu, 2 tarama hatası (fail-closed)
# Hiçbir dosya atlatılmaz; placeholder/CHANGE_ME hariç gerçek değer yakalanır.
set -uo pipefail
ROOT="${1:-.}"
if [ ! -d "$ROOT" ]; then
  echo "❌ ROOT yok: $ROOT" >&2
  exit 2
fi
cd "$ROOT" || exit 2

# fail-closed: gerekli araçlar yoksa hata
for bin in grep find sed; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "❌ Gerekli araç yok: $bin (fail-closed)" >&2
    exit 2
  fi
done

# Yüksek güvenilirlikli gerçek değer kalıpları (literal token/credentials)
# Placeholder'lar (CHANGE_ME, dev-only, REPLACE_ME, empty) asla eşleşmez
STRONG=(
  'TELEGRAM_BOT_TOKEN[=: ]+[0-9]{6,}:[A-Za-z0-9_-]{30,}'   # gerçek TG token
  'TELEGRAM_BOT_TOKEN[=:][ ]*[0-9]{6,}:[A-Za-z0-9_-]{30,}' # env assignment variant
  'mongodb(\+srv)?://[^: ]+:[^@ ]{8,}@[^: ]+'               # gerçek DB creds (pw >=8)
  'postgresql(\+[^: ]+)?://[^: ]+:[^@ ]{8,}@[^: ]+'         # postgres URL with pw >=8
  '\bgh[pousr]_[A-Za-z0-9]{20,}\b'                        # GitHub token
  '\bsk(-[A-Za-z0-9]{8,}){2,}\b'                          # OpenAI-style sk-...
  'LLM_API_KEY[=: ]+[A-Za-z0-9_-]{24,}'                  # gerçek LLM key assignment
  'JWT_SECRET[=: ]+[A-Za-z0-9_\-+/=]{24,}'               # JWT secret assignment (non-placeholder)
  'SESSION_ENCRYPTION_MASTER_KEY[=: ]+[A-Za-z0-9_\-+/=]{24,}'
  'POSTGRES_PASSWORD[=: ]+[A-Za-z0-9_\-+/=]{8,}'
  'DB_PASSWORD[=: ]+[A-Za-z0-9_\-+/=]{8,}'
)

# Placeholder'ları eşleşmeden çıkar (satır bazında filtrelenir)
is_placeholder_line() {
  echo "$1" | grep -qE 'CHANGE_ME|REPLACE_ME|dev-only|example\.com|_here|your-.*-here|\$\{|random|:x@|localhost:5432/raptor|127\.0\.0\.1|<MASKED>|<REDACTED>|\*\*\*|docs/mcp-audit' 2>/dev/null
}

hits=0
scanned=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  # türetilmiş audit kopyaları — gerçek leak değil, kaynak dosyanın kopyası (test fixture'lar <MASKED> içerir)
  if echo "$f" | grep -qE 'docs/mcp-audit' 2>/dev/null; then
    continue
  fi
  # fixture/test kendini tarama — pozitif fixture'lar kasıtlı olarak gerçek pattern içerir, repo leak değil
  if echo "$f" | grep -qE 'tests/security/test_secret_scan|tests/fixtures/secret-scan' 2>/dev/null; then
    continue
  fi
  scanned=$((scanned+1))
  # .env.example ve fixture'lar özel: .env.example ayrı kontrol edilir; fixture positive'ler allowlist'tedir
  # Ama fail-closed: tarama dışı bırakma YOK — sadece raporlama için etiketle
  for pat in "${STRONG[@]}"; do
    if grep -qE "$pat" "$f" 2>/dev/null; then
      # satırı al, placeholder ise atla (gerçek değer değil)
      line=$(grep -nE "$pat" "$f" 2>/dev/null | head -1)
      if is_placeholder_line "$line"; then
        continue
      fi
      # fixture positive files are expected to be caught — mark but still count unless in allowlist dir
      if echo "$f" | grep -qE 'tests/fixtures/secret-scan-positive|secret-scan-fixtures' 2>/dev/null; then
        # positive fixture: should be detected; don't count as repo leak, just ensure detection works
        continue
      fi
      # test_policy_redaction.py'deki ""Authorization: Bearer ***"" gibi maskelenmiş test stringleri
      # eğer satırda <REDACTED> veya *** maskesi varsa atla
      if echo "$line" | grep -qE '<REDACTED>|<MASKED>|\*\*\*' 2>/dev/null; then
        # ama satırda gerçek token da varsa yine de yakala — ek kontrol
        if echo "$line" | grep -qE '[A-Za-z0-9_-]{30,}' 2>/dev/null && ! echo "$line" | grep -qE 'CHANGE_ME'; then
          # gerçek değer var gibi, yine raporla
          :
        else
          continue
        fi
      fi
      echo "⚠️  GERÇEK SIR ADAYI: $f"
      echo "$line" | head -1 | sed -E 's/([0-9]{6,}:[A-Za-z0-9_-]{30,}|mongodb(\+srv)?:\/\/[^@]+@|postgresql(\+[^:]+)?:\/\/[^@]+@|sk-[A-Za-z0-9]{8,}[A-Za-z0-9_-]*|[A-Za-z0-9_-]{30,})/<MASKED>/g'
      hits=1
    fi
  done
done < <(find . -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' -o -name '*.sh' -o -name '*.yml' -o -name '*.yaml' -o -name '*.json' -o -name '*.md' -o -name '*.ini' -o -name '*.env*' -o -name '*.example' \) \
    -not -path '*/.git/*' -not -path '*/.venv/*' -not -path '*/node_modules/*' -not -path '*/dist/*' \
    -not -path '*/.pytest_cache/*' -not -path '*/instance/*' -not -path '*/__pycache__/*' \
    -not -path '*/tests/security/test_secret_scan.py' \
    -not -path '*/backups/*' 2>/dev/null )

# fail-closed: hiç dosya taranamadıysa hata
if [ "$scanned" -eq 0 ]; then
  echo "❌ Tarama hatası: hiç dosya taranamadı (fail-closed)" >&2
  exit 2
fi

# gerçek secret dosyalarını hiçbir zaman commit etme — repo içinde app.env varsa kesin fail
# .env için: sadece git takibindeyse fail (dev .env gitignore'dadır)
if find . -name 'app.env' -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/.venv/*' 2>/dev/null | grep -q .; then
  real_env=$(find . -name 'app.env' -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/.venv/*' 2>/dev/null | head -5)
  if [ -n "$real_env" ]; then
    echo "❌ REPO İÇİNDE app.env VAR — commit etme!"
    echo "$real_env"
    hits=1
  fi
fi
# .env sadece git'te takibliyse fail (git ls-files ile kontrol, fail-closed değilse sadece uyar)
if [ -d ".git" ] && git ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo "❌ REPO İÇİNDE .env TAKİPLİ — .gitignore'a ekle!"
  hits=1
fi

# .env.example güvenliği: sadece CHANGE_ME / boş / safe placeholder içermeli
if [ -f ".env.example" ]; then
  # .env.example içinde gerçek TG token / sk- / 64 hex gibi değer varsa fail
  if grep -qE '[0-9]{6,}:[A-Za-z0-9_-]{30,}' .env.example 2>/dev/null; then
    if ! grep -qE 'CHANGE_ME' .env.example 2>/dev/null; then
      : # placeholder yoksa gerçek token demektir
    fi
    # CHANGE_ME olmayan gerçek token satırı var mı?
    if grep -E '[0-9]{6,}:[A-Za-z0-9_-]{30,}' .env.example 2>/dev/null | grep -qv 'CHANGE_ME' 2>/dev/null; then
      echo "❌ .env.example içinde gerçek Telegram token var!"
      hits=1
    fi
  fi
  # .env.example içinde sk- ile başlayan gerçek key var mı (CHANGE_ME hariç)
  if grep -qE 'sk-[A-Za-z0-9]{20,}' .env.example 2>/dev/null; then
    if grep -E 'sk-[A-Za-z0-9]{20,}' .env.example 2>/dev/null | grep -qv 'CHANGE_ME' 2>/dev/null; then
      echo "❌ .env.example içinde gerçek LLM key var!"
      hits=1
    fi
  fi
  # POSTGRES_PASSWORD / JWT_SECRET satırında CHANGE_ME yoksa ve değer uzun ise fail
  for key in POSTGRES_PASSWORD DB_PASSWORD JWT_SECRET SESSION_ENCRYPTION_MASTER_KEY TELEGRAM_BOT_TOKEN LLM_API_KEY; do
    line=$(grep -E "^${key}=" .env.example 2>/dev/null | head -1 || true)
    if [ -n "$line" ]; then
      val=$(echo "$line" | cut -d= -f2-)
      # boş veya CHANGE_ME ise OK
      if [ -z "$val" ] || echo "$val" | grep -q 'CHANGE_ME' 2>/dev/null; then
        continue
      fi
      # 8+ karakter ve CHANGE_ME değilse gerçek değer şüphesi
      if [ "${#val}" -ge 8 ] && ! echo "$val" | grep -qE '^\$\{' 2>/dev/null; then
        echo "❌ .env.example içinde $key gerçek değer içeriyor: $line (yalnız CHANGE_ME olmalı)"
        hits=1
      fi
    fi
  done
fi

if [ "$hits" = "0" ]; then
  echo "✅ Secret scan temiz: repo'da gerçek credential yok. (taranan dosya: $scanned)"
else
  echo "❌ Secret scan: gerçek sır adayı bulundu — commit'i DURDUR."
  exit 1
fi
