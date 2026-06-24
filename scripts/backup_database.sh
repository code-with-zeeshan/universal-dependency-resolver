#!/bin/bash
set -eo pipefail
source "$(dirname "$0")/../.env"

source "$(dirname "$0")/common.sh"

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/postgres_backup_${TIMESTAMP}.sql.gz"
mkdir -p "$BACKUP_DIR"

echo "Starting database backup..."
pg_dump "$DATABASE_URL" --no-owner --no-acl 2>/dev/null | gzip > "$BACKUP_FILE" \
    || pg_dump "$DATABASE_URL" | gzip > "$BACKUP_FILE"

upload_to_cloud "$BACKUP_FILE" "udr-backups/postgres"

find "$BACKUP_DIR" -name "postgres_backup_*.sql.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_FILE"
