# Deployment Guide

## Topology

```mermaid
flowchart TD
    LB["Load Balancer<br/>nginx / haproxy"] --> W1
    LB --> W2
    LB --> WN["API Worker N"]

    subgraph WORKERS["API Workers"]
        W1["API Worker 1<br/>uvicorn"]
        W2["API Worker 2<br/>uvicorn"]
        WN["API Worker N<br/>uvicorn"]
    end

    W1 --> DB
    W2 --> DB
    WN --> DB
    W1 --> REDIS
    W2 --> REDIS
    WN --> REDIS

    DB[("PostgreSQL<br/>packages · users · reports<br/>Alembic migrations")]
    REDIS[("Redis<br/>cache · rate limiting<br/>session store")]

    style LB fill:#1a237e,color:#fff
    style WORKERS fill:#004d40,color:#fff
    style DB fill:#e65100,color:#fff
    style REDIS fill:#c62828,color:#fff

    classDef box fill:#1a237e,color:#fff
    class W1,W2,WN box
```

---

## Deployment Scenarios

### 1. Single Developer (Local)

```bash
pip install ud-resolver[z3,system]
udr serve
# → http://127.0.0.1:8000, SQLite, in-memory cache
```

No external services. SQLite at `~/.cache/udr/udr.db`.

### 2. Single-User Server

```bash
# Start in background
udr serve --host 0.0.0.0 --port 8000 --log-level warning &
```

PostgreSQL for better concurrency (optional):

```bash
export DATABASE_URL=postgresql://user:pass@localhost/udr
pip install ud-resolver[postgres]
udr serve --host 0.0.0.0
```

### 3. Production Multi-Worker

```bash
# Install all extras
pip install ud-resolver[all]

# Set up PostgreSQL
createdb udr
export DATABASE_URL=postgresql://user:pass@localhost/udr

# Set up Redis
export REDIS_URL=redis://localhost:6379

# Start multiple workers
udr serve --workers 4 --mode saas --log-level warning
```

Place behind nginx reverse proxy:

```nginx
server {
    listen 80;
    server_name udr.example.com;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 4. Desktop App

```bash
# Download the .AppImage/.dmg/.exe from Releases
# The backend is bundled via PyInstaller — no Python needed.
./udr-desktop.AppImage
```

The desktop app starts an embedded backend server on `127.0.0.1:8000`.

### 5. Web Frontend

The web frontend (`frontend/`) is a **static, no-build vanilla JS SPA** — pure HTML/CSS/JS, no npm step, no CDN dependencies. It talks to the backend REST API.

Serve it with any static file server and point its API base URL at a running backend:

```bash
# Start the backend API first
python run.py                      # or: udr serve --port 8199

# Serve the frontend (any static server works)
cd frontend
python -m http.server 3000
# or: npx serve .
```

The frontend reads the backend origin from the `ApiClient` base URL in `frontend/js/api.js` (default `http://localhost:8199`). For production, serve the static files with the same nginx host as the API so both share an origin (no CORS needed):

```nginx
server {
    listen 80;
    server_name udr.example.com;

    root /var/www/udr-frontend;                # frontend/ directory
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxied on the same origin -> same-origin fetch, no CORS
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location /healthz {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

### 6. VS Code Extension

The VS Code extension (`vscode-extension/`) is TypeScript and targets VS Code `^1.85.0`. Install from the packaged VSIX, or run it in the Extension Development Host:

```bash
cd vscode-extension
npm install
npm run compile          # tsc -> out/extension.js
code --install-extension ./out/udr-vscode.vsix   # packaged file
```

For development / testing the extension live:

```bash
cd vscode-extension
npm run watch             # tsc --watch
# then run "Extension Development Host" from VS Code (F5)
```

The extension integrates the `udr` CLI (lock file viewer, CVE diagnostics, manifest editing) — the CLI must be on `PATH` and `udr` installed:

```bash
pip install ud-resolver[z3]
```

### 7. CI/CD

```yaml
# GitHub Actions — install and check
- name: Install UDR
  run: pip install ud-resolver[z3]
- name: Check lock drift
  run: udr lock --check
```

```yaml
# GitLab CI
udr-lock-check:
  image: python:3.13
  script:
    - pip install ud-resolver[z3]
    - udr lock --check
  only:
    - merge_requests
```

---

## Database Configuration

### SQLite (Default)

```bash
# Location: ~/.cache/udr/udr.db
# No configuration needed
```

### PostgreSQL

```bash
# Install
pip install ud-resolver[postgres]

# Set connection string
export DATABASE_URL=postgresql://user:password@host:5432/udr

# Optional: connection pool
export DATABASE_POOL_SIZE=20
export DATABASE_MAX_OVERFLOW=40
```

Alembic migrations run automatically on first start.

---

## Authentication

Auth is **enabled by default** (`ENABLE_AUTH=true`). In local mode, auth endpoints are not mounted but the API key middleware is still active.

### Disable auth (local-only)

```bash
export ENABLE_AUTH=false
udr serve
```

### API key authentication

```bash
# Set a shared API key
export API_KEY=my-secret-key
udr serve

# Clients pass it as header
curl -H "X-API-Key: my-secret-key" http://localhost:8000/api/v1/system/info
```

### Full auth stack (SaaS)

```bash
udr serve --mode saas
# JWT tokens from /auth/login
# API keys from /auth/api-keys
# Rate limiting via Redis (or in-memory fallback)
```

---

## Caching

| Cache | Default | Production | Purpose |
|---|---|---|---|
| DictCache | In-memory | In-memory | Registry API response cache (TTL: 1h) |
| ContentAddressedCache | `~/.cache/udr/cac/` | Same | SHA256-verified blob store |
| Offline indexes | `~/.cache/udr/indexes/` | Same | SQLite per-ecosystem indexes |
| Redis | Disabled | Required for multi-worker | Rate limiting, cross-worker cache |

---

## Environment Variables

### Server

| Variable | Default | Description |
|---|---|---|
| `ENABLE_AUTH` | `true` | Enable authentication stack |
| `API_KEY` | `None` | Shared API key for header auth |
| `DATABASE_URL` | `None` (SQLite) | PostgreSQL connection string |
| `REDIS_URL` | `None` | Redis connection string |
| `SOLVER_TIMEOUT` | `120` | Resolution timeout (seconds) |
| `SOLVER_API_TIMEOUT` | `60` | API endpoint resolution timeout |
| `SOLVER_MAX_VARIABLES` | `50000` | Max SAT variables before abort |

### Solver

| Variable | Default | Description |
|---|---|---|
| `USE_PUBGRUB_SOLVER` | `false` | Use PubGrub instead of Z3 |
| `USE_Z3_OPTIMIZE` | `false` | Enable Z3 optimization (prefers latest) |
| `SOLVER_REJECT_DEPRECATED` | `false` | Reject deprecated/yanked packages |
| `SOLVER_PRERELEASE_PENALTY` | `100000` | Prerelease version penalty weight |
| `SOLVER_MAX_CLUSTERS` | `auto` | Max version clusters per package |
| `SOLVER_MAX_VERSIONS_PER_PKG` | `50` | Max versions to feed to SAT solver |

### Performance

| Variable | Default | Description |
|---|---|---|
| `NPM_CONCURRENCY` | `10` | Concurrent npm API requests |
| `GOMODULES_CONCURRENCY` | `20` | Concurrent Go module proxy requests |
| `BFS_BATCH_SIZE` | `20` | Batch size for BFS dep discovery |
| `SCANNER_MAX_WORKERS` | `10` | System scanner thread pool |
| `CACHE_TTL` | `3600` | Default cache TTL (seconds) |
| `CACHE_TTL_SHORT` | `300` | Rate-limited endpoint cache TTL |
| `CACHE_TTL_VERSIONS` | `600` | Version listing cache TTL |
| `DETECT_ECOSYSTEMS_TIMEOUT` | `15` | Ecosystem detection timeout |

---

## Systemd Service

```ini
[Unit]
Description=Universal Dependency Resolver API
After=network.target

[Service]
Type=simple
User=udr
WorkingDirectory=/opt/udr
Environment=ENABLE_AUTH=true
Environment=API_KEY=change-me
Environment=DATABASE_URL=postgresql://udr:pass@localhost/udr
Environment=SOLVER_TIMEOUT=120
ExecStart=/usr/local/bin/udr serve --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## Backup

```bash
# SQLite
cp ~/.cache/udr/udr.db /backup/udr-$(date +%Y%m%d).db
cp -r ~/.cache/udr/indexes /backup/indexes-$(date +%Y%m%d)

# PostgreSQL
pg_dump -U udr udr > /backup/udr-$(date +%Y%m%d).sql
```
