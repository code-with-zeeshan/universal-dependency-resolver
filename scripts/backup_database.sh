#!/bin/bash
# scripts/backup_database.sh
# Flexible backup script that works with both self-hosted and cloud databases

set -e

# Load environment
source .env

# Configuration
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/postgres_backup_${TIMESTAMP}.sql.gz"

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo "Starting database backup..."

# Detect database type
if [[ "$DATABASE_URL" == *"neon.tech"* ]]; then
    echo "Detected Neon database"
    # Neon supports standard pg_dump
    pg_dump "$DATABASE_URL" --no-owner --no-acl | gzip > "$BACKUP_FILE"
    
elif [[ "$DATABASE_URL" == *"supabase"* ]]; then
    echo "Detected Supabase database"
    # Supabase also supports pg_dump
    pg_dump "$DATABASE_URL" --no-owner --no-acl | gzip > "$BACKUP_FILE"
    
elif [[ "$DATABASE_URL" == *"render.com"* ]]; then
    echo "Detected Render database"
    pg_dump "$DATABASE_URL" | gzip > "$BACKUP_FILE"
    
else
    echo "Using standard PostgreSQL backup"
    pg_dump "$DATABASE_URL" | gzip > "$BACKUP_FILE"
fi

# Backup to cloud storage (if configured)
if [ -n "$BACKUP_STORAGE" ]; then
    case "$BACKUP_STORAGE" in
        "cloudflare-r2")
            echo "Backing up to Cloudflare R2..."
            rclone copy "$BACKUP_FILE" cloudflare-r2:udr-backups/postgres/
            ;;
        "github")
            # Only if file is under 100MB
            if [ $(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE") -lt 104857600 ]; then
                echo "Backing up to GitHub..."
                git add "$BACKUP_FILE"
                git commit -m "Automated backup $TIMESTAMP"
                git push
            else
                echo "File too large for GitHub (>100MB)"
            fi
            ;;
        "gdrive")
            echo "Backing up to Google Drive..."
            rclone copy "$BACKUP_FILE" gdrive:udr-backups/
            ;;
    esac
fi

# Clean up old local backups (keep last 7 days)
find "$BACKUP_DIR" -name "postgres_backup_*.sql.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_FILE"