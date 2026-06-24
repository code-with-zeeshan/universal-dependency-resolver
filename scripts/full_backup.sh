#!/bin/bash
set -e
source "$(dirname "$0")/../.env"

source "$(dirname "$0")/common.sh"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_ROOT="./backups/full_backup_${TIMESTAMP}"

echo "Starting full system backup..."
mkdir -p "$BACKUP_ROOT"/{database,redis,uploads,configs,logs}

# Database backup
echo "Backing up database..."
./scripts/backup_database.sh
for f in ./backups/postgres_backup_*.sql.gz; do
    [ -f "$f" ] && cp "$f" "$BACKUP_ROOT/database/"
done

# Redis backup (if using persistent Redis)
if [ -n "$REDIS_URL" ] && [[ "$REDIS_URL" != *"upstash"* ]]; then
    docker-compose exec -T redis redis-cli BGSAVE
    sleep 5
    docker cp $(docker-compose ps -q redis):/data/dump.rdb "$BACKUP_ROOT/redis/"
fi

# Environment files (without secrets)
for env_file in .env.development .env.staging .env.production; do
    [ -f "$env_file" ] && sed -E 's/(PASSWORD|SECRET|KEY|TOKEN)=.*/\1=REDACTED/g' "$env_file" > "$BACKUP_ROOT/configs/$env_file"
done

# Uploaded files
[ -d "uploads" ] && cp -r uploads "$BACKUP_ROOT/"

# Logs
for log_dir in logs backend/logs frontend/logs; do
    [ -d "$log_dir" ] && cp -r "$log_dir" "$BACKUP_ROOT/logs/"
done

# Backup manifest
cat > "$BACKUP_ROOT/manifest.json" << EOF
{
  "timestamp": "$TIMESTAMP",
  "version": "$(git describe --tags --always)",
  "git_commit": "$(git rev-parse HEAD)",
  "backup_method": "full"
}
EOF

# Compress
tar -czf "$BACKUP_ROOT.tar.gz" -C "$(dirname $BACKUP_ROOT)" "$(basename $BACKUP_ROOT)"

upload_to_cloud "$BACKUP_ROOT.tar.gz" "udr-backups/full"

rm -rf "$BACKUP_ROOT"

echo "Full backup completed: $BACKUP_ROOT.tar.gz"
echo "Size: $(ls -lh $BACKUP_ROOT.tar.gz | awk '{print $5}')"

ls -t backups/full_backup_*.tar.gz 2>/dev/null | tail -n +4 | xargs -r rm
echo "Backup process complete!"
