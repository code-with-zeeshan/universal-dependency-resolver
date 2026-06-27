# Troubleshooting Guide

## Startup Issues

### Database Connection Failed

**Solutions:**
1. Check `DATABASE_URL` in `.env` (default: `sqlite:///./udr.db`)
2. For PostgreSQL: verify it's running and credentials are correct
3. For SQLite: ensure the parent directory is writable
4. Reset: `rm -f udr.db && alembic upgrade head`

### Redis Connection Failed

Redis is **optional**. If `REDIS_URL` is not set, the app uses DictCache (in-memory) and runs fine.

If Redis is set but unreachable:
- Check connection with `redis-cli ping`
- The app logs a warning and falls back to DictCache automatically

### Port Already in Use

```bash
lsof -i :8000  # Backend (or whatever UDR_PORT is set to)
```

## Database Issues

### SQLite Performance
SQLite is fine for single-user/desktop use. For multi-user production, use PostgreSQL.

### PostgreSQL Connection Pool Exhausted

```bash
# Increase pool size in .env
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30
```

## Test Issues

### PostgreSQL Requirement

Integration tests default to SQLite (`sqlite:////tmp/test_integration.db`) — no PostgreSQL is required to run tests.

```bash
# Run all tests (no Docker needed)
pytest -v

# With coverage
pytest --cov=backend
```


## API Issues

### 429 Too Many Requests

Rate limits:
- Search: 60/min
- Resolve: 10/min
- Export: 20/min
- Auth (login): 10/min

Wait for reset or increase via environment variables.

### Authentication Errors

- Auth is **disabled by default** (`UDR_MODE=local` or `--mode local`)
- For SaaS deployment: run with `UDR_MODE=saas` or `--mode saas` to enable JWT + API key auth
- Tokens expire after configurable minutes (default: 30)

## Performance

### High Memory Usage
- SQLite is memory-efficient for single-user
- For multi-user, use PostgreSQL
- Monitor with `docker stats` or health endpoint

### Cache Hit Rate Low
- DictCache has no persistence (cleared on restart)
- For persistent cache, configure Redis
- Tune `CACHE_TTL` in environment

## Desktop App

### Backend Fails to Start
- The Electron app spawns the Python backend automatically
- Check the error dialog for details
- Ensure Python 3.11+ is available on PATH
- On Windows, use the bundled Python from install

## Getting Help

- **API Docs**: `http://localhost:8000/api/v1/docs`
- **Health Check**: `http://localhost:8000/api/v1/health`
- **GitHub Issues**: Report bugs and feature requests
