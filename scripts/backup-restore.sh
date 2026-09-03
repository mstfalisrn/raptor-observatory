#!/usr/bin/env bash
# LUMI — veritabanı yedekleme (PostgreSQL dump) ve restore helper
# Yedekler /var/backups/lumi-observatory altına timestamp'li yazılır.
set -euo pipefail

BACKUP_DIR="${LUMI_BACKUP_DIR:-/var/backups/lumi-observatory}"
CONTAINER="lumi-postgres"
DB_USER="${POSTGRES_USER:-lumi}"
DB_NAME="${POSTGRES_DB:-lumi}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD gerekiyor}"

mkdir -p "$BACKUP_DIR"
chmod 0700 "$BACKUP_DIR"

action="${1:-backup}"
TS=$(date +%Y%m%d-%H%M%S)

case "$action" in
  backup)
    OUT="$BACKUP_DIR/lumi-$TS.dump"
    docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" "$CONTAINER" \
      pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$OUT"
    chmod 0600 "$OUT"
    echo "✅ Yedek: $OUT ($(du -h "$OUT" | cut -f1))"
    ;;
  restore)
    SRC="${2:?restore için kaynak dump dosyası gerekir}"
    # Restore to backup DB (without overwriting production DB)
    docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" "$CONTAINER" \
      createdb -U "$DB_USER" -O "$DB_USER" lumi_restore_test 2>/dev/null || true
    docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" "$CONTAINER" \
      pg_restore -U "$DB_USER" -d lumi_restore_test --no-owner --no-privileges < "$SRC"
    echo "✅ Restore testi tamam: lumi_restore_test veritabanına yüklendi"
    echo "   (üretim veritabanına dokunulmadı)"
    ;;
  *)
    echo "Kullanım: $0 backup|restore <dosya>"
    exit 1
    ;;
esac