#!/bin/bash
# scripts/restore_database.sh
# Restore database from backup

set -e

# Check arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup_file> [database_url]"
    echo "Example: $0 backups/postgres_backup_20240115_120000.sql.gz"
    exit 1
fi

BACKUP_FILE=$1
DATABASE_URL=${2:-$DATABASE_URL}

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "WARNING: This will DROP and RECREATE the database!"
echo "Database: $DATABASE_URL"
echo "Backup file: $BACKUP_FILE"
read -p "Are you sure? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Restoration cancelled"
    exit 0
fi

# Extract database name from URL
DB_NAME=$(echo $DATABASE_URL | sed -n 's/.*\/\([^?]*\).*/\1/p')

echo "Restoring database..."

# For cloud databases, we can't drop/create, so we clean instead
if [[ "$DATABASE_URL" == *"neon.tech"* ]] || [[ "$DATABASE_URL" == *"supabase"* ]]; then
    echo "Cloud database detected - cleaning existing data..."
    
    # Generate cleanup script
    cat > cleanup.sql << 'EOF'
DO $$ 
DECLARE
    r RECORD;
BEGIN
    -- Drop all tables
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
        EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;
EOF
    
    psql "$DATABASE_URL" < cleanup.sql
    rm cleanup.sql
else
    # Local database - can drop and recreate
    psql "$DATABASE_URL" -c "DROP DATABASE IF EXISTS $DB_NAME;"
    psql "$DATABASE_URL" -c "CREATE DATABASE $DB_NAME;"
fi

# Restore from backup
gunzip -c "$BACKUP_FILE" | psql "$DATABASE_URL"

echo "Database restoration completed successfully!"

# Run migrations to ensure schema is up to date
if [ -f "alembic/alembic.ini" ]; then
    echo "Running database migrations..."
    alembic -c alembic/alembic.ini upgrade head
fi

echo "Restoration process complete!"