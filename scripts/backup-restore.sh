#!/usr/bin/env bash
# RAPTOR — veritabanı yedekleme (PostgreSQL dump) ve restore helper
# Yedekler /var/backups/raptor-observatory altına timestamp'li yazılır.
set -euo pipefail

BACKUP_DIR="${RAPTOR_BACKUP_DIR:-/var/backups/raptor-observatory}"
CONTAINER="raptor-postgres"
DB_USER="${POSTGRES_USER:-raptor}"
DB_NAME="${POSTGRES_DB:-raptor}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD gerekiyor}"

mkdir -p "$BACKUP_DIR"
chmod 0700 "$BACKUP_DIR"

action="${1:-backup}"
TS=$(date +%Y%m%d-%H%M%S)

case "$action" in
  backup)
    OUT="$BACKUP_DIR/raptor-$TS.dump"
    docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" "$CONTAINER" \
      pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$OUT"
    chmod 0600 "$OUT"
    echo "✅ Yedek: $OUT ($(du -h "$OUT" | cut -f1))"
    ;;
  restore)
    SRC="${2:?restore için kaynak dump dosyası gerekir}"
    # Yedek DB'ye geri yükle (üretim DB'sini ezmeden)
    docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" "$CONTAINER" \
      createdb -U "$DB_USER" -O "$DB_USER" raptor_restore_test 2>/dev/null || true
    docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" "$CONTAINER" \
      pg_restore -U "$DB_USER" -d raptor_restore_test --no-owner --no-privileges < "$SRC"
    echo "✅ Restore testi tamam: raptor_restore_test veritabanına yüklendi"
    echo "   (üretim veritabanına dokunulmadı)"
    ;;
  *)
    echo "Kullanım: $0 backup|restore <dosya>"
    exit 1
    ;;
esac