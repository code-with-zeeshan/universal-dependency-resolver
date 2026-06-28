# Deployment

This is a CLI tool and Python library, not a server application. However, you can run the API server for programmatic access.

## Quick start

```bash
pip install ud-resolver
udr serve --host 0.0.0.0 --port 8000
```

## Production considerations

### Database

By default the server uses SQLite (`./udr.db`). For multi-user or higher-throughput scenarios, configure PostgreSQL:

```bash
export DATABASE_URL=postgresql://user:password@host:5432/udr
```

### Authentication

Auth is disabled by default. To enable:

```bash
export ENABLE_AUTH=true
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

### Caching

By default the server uses `DictCache` (in-memory, cleared on restart). For persistent caching across restarts, configure Redis:

```bash
export REDIS_URL=redis://host:6379
```

### Running as a service

```bash
# systemd service example
[Unit]
Description=UDR API Server
After=network.target

[Service]
Type=simple
User=udr
ExecStart=/usr/local/bin/udr serve --host 0.0.0.0 --port 8000
Environment=DATABASE_URL=postgresql://...
Environment=REDIS_URL=redis://...
Restart=always

[Install]
WantedBy=multi-user.target
```

### Environment variables

See `.env.example` in the repository root.

## Backup

For SQLite:

```bash
cp udr.db udr.db.backup
```

For PostgreSQL:

```bash
pg_dump -h $DB_HOST -U $DB_USER -d udr | gzip > udr_backup.sql.gz
```
