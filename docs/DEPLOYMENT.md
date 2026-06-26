# Deployment Guide

## Overview

| Method | Complexity | Best For |
|--------|------------|----------|
| Direct (no Docker) | Low | Desktop (manual), development, single-user |
| Docker Compose | Low-Medium | Development, small deployments |
| Cloud | Medium | Production, managed infrastructure |

## Prerequisites

**Minimum:**
- CPU: 2 cores, RAM: 4GB, Storage: 10GB

**For Docker:**
- Docker 20.10+ and Docker Compose v2

**For cloud:**
- Container registry (GitHub Container Registry, Docker Hub, etc.)

## Quick Start (No Docker)

```bash
pip install -e ".[dev]"
# SQLite by default, no config needed
uvicorn backend.api.main:app --reload
# → http://localhost:8000
```

## Docker Compose

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
curl http://localhost:8000/api/v1/health
```

PostgreSQL and Redis are optional. The backend defaults to SQLite + in-memory cache. Set `DATABASE_URL` and `REDIS_URL` in `.env` to use them.

### Production Compose

Create `docker-compose.prod.yml`:

```yaml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./frontend/nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on: [backend, frontend]
    restart: unless-stopped

  backend:
    build: ./backend
    env_file: .env.production
    depends_on:
      db: { condition: service_healthy }
    restart: unless-stopped
    deploy:
      replicas: 3
      resources:
        limits: { cpus: '1.0', memory: 1G }

  frontend:
    build: ./frontend
    environment:
      - VUE_APP_API_URL=https://api.example.com  # Replace with your domain
    restart: unless-stopped
    deploy:
      replicas: 2

  db:
    image: postgres:15-alpine
    env_file: .env.production
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $POSTGRES_USER"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 512mb
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]

networks:
  app-network:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
```

## Standalone Mode

Set `UDR_STANDALONE=true` to skip Redis validation. The app uses:
- SQLite (no PostgreSQL needed)
- DictCache (no Redis needed)

Ideal for desktop app, single-user, or CI environments.

> **Tip**: The [Desktop app](COMPONENTS.md#3-desktop-electron-standalone-app) uses standalone mode automatically — no configuration needed.

## Production Checklist

- [ ] HTTPS enabled (TLS certificate)
- [ ] CORS configured for your domain
- [ ] Rate limiting enabled (default: on)
- [ ] Auth enabled in production (`ENABLE_AUTH=true`)
- [ ] Database migrations applied
- [ ] Backups configured (see scripts/backup_database.sh)
- [ ] Monitoring (Prometheus metrics at `/metrics`)
- [ ] Sentry DSN configured for error tracking (optional)

## Environment Variables

```bash
# Database (default: sqlite:///./udr.db)
DATABASE_URL=postgresql://user:password@host:5432/depresolver

# Redis (optional — falls back to in-memory cache)
REDIS_URL=redis://host:6379

# Auth
SECRET_KEY=<generate-a-random-secret>  # python -c "import secrets; print(secrets.token_hex(32))"
ENABLE_AUTH=true

# CORS
ALLOWED_ORIGINS=https://example.com  # Replace with your frontend domain

# Standalone (skip Redis/Postgres checks)
UDR_STANDALONE=false
```

## Backup & Recovery

```bash
# Backup
pg_dump -h $DB_HOST -U $DB_USER -d depresolver | gzip > backup.sql.gz

# Restore
gunzip -c backup.sql.gz | psql -h $DB_HOST -U $DB_USER -d depresolver
```

For SQLite, just copy `udr.db`.
