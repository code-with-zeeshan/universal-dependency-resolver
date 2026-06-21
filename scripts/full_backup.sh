#!/bin/bash
# scripts/full_backup.sh
# Complete backup of all services and data

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_ROOT="./backups/full_backup_${TIMESTAMP}"

echo "Starting full system backup..."

# Create backup structure
mkdir -p "$BACKUP_ROOT"/{database,redis,uploads,configs,logs}

# 1. Database backup
echo "Backing up database..."
./scripts/backup_database.sh
cp ./backups/postgres_backup_*.sql.gz "$BACKUP_ROOT/database/"

# 2. Redis backup (if using persistent Redis)
if [ -n "$REDIS_URL" ]; then
    echo "Backing up Redis..."
    
    if [[ "$REDIS_URL" == *"upstash"* ]]; then
        # Upstash backup via REST API
        echo "Backing up Upstash Redis..."
        # Note: Upstash provides automatic backups in paid plans
        echo "Upstash free tier doesn't support dumps - skipping"
    else
        # Local Redis backup
        docker-compose exec -T redis redis-cli BGSAVE
        sleep 5
        docker cp $(docker-compose ps -q redis):/data/dump.rdb "$BACKUP_ROOT/redis/"
    fi
fi

# 3. Environment files (without secrets)
echo "Backing up configurations..."
for env_file in .env.development .env.staging .env.production; do
    if [ -f "$env_file" ]; then
        # Remove sensitive data
        sed -E 's/(PASSWORD|SECRET|KEY|TOKEN)=.*/\1=REDACTED/g' "$env_file" > "$BACKUP_ROOT/configs/$env_file"
    fi
done

# 4. Uploaded files (if any)
if [ -d "uploads" ]; then
    echo "Backing up uploaded files..."
    cp -r uploads "$BACKUP_ROOT/"
fi

# 5. Application logs
echo "Backing up logs..."
for log_dir in logs backend/logs frontend/logs; do
    if [ -d "$log_dir" ]; then
        cp -r "$log_dir" "$BACKUP_ROOT/logs/"
    fi
done

# 6. Create backup manifest
cat > "$BACKUP_ROOT/manifest.json" << EOF
{
  "timestamp": "$TIMESTAMP",
  "version": "$(git describe --tags --always)",
  "components": {
    "database": "$(ls -lh $BACKUP_ROOT/database/*.sql.gz | awk '{print $5}')",
    "redis": "$(ls -lh $BACKUP_ROOT/redis/dump.rdb 2>/dev/null | awk '{print $5}' || echo 'N/A')",
    "configs": "$(ls -1 $BACKUP_ROOT/configs | wc -l) files",
    "logs": "$(du -sh $BACKUP_ROOT/logs 2>/dev/null | cut -f1 || echo '0')"
  },
  "git_commit": "$(git rev-parse HEAD)",
  "backup_method": "full"
}
EOF

# 7. Compress everything
echo "Compressing backup..."
tar -czf "$BACKUP_ROOT.tar.gz" -C "$(dirname $BACKUP_ROOT)" "$(basename $BACKUP_ROOT)"

# 8. Upload to cloud storage
if [ -n "$BACKUP_STORAGE" ]; then
    case "$BACKUP_STORAGE" in
        "cloudflare-r2")
            rclone copy "$BACKUP_ROOT.tar.gz" cloudflare-r2:udr-backups/full/
            ;;
        "gdrive")
            rclone copy "$BACKUP_ROOT.tar.gz" gdrive:udr-backups/full/
            ;;
        "backblaze")
            rclone copy "$BACKUP_ROOT.tar.gz" b2:udr-backups/full/
            ;;
    esac
fi

# 9. Cleanup
rm -rf "$BACKUP_ROOT"

echo "Full backup completed: $BACKUP_ROOT.tar.gz"
echo "Size: $(ls -lh $BACKUP_ROOT.tar.gz | awk '{print $5}')"

# Keep only last 3 full backups locally
ls -t backups/full_backup_*.tar.gz | tail -n +4 | xargs -r rm

echo "Backup process complete!"