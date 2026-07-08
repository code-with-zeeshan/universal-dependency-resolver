# Deployment

## Topology

```mermaid
graph TB
    subgraph Users["👤 Users"]
        DEV["💻 Developer<br/><code>udr resolve</code>"]
        CI["🤖 CI/CD<br/><code>udr lock</code>"]
        APP["🌐 Web App<br/><code>HTTP API</code>"]
        DESKTOP["🖥️ Desktop App<br/><code>Electron GUI</code>"]
    end

    subgraph LB["⚖️ Load Balancer"]
        NGINX["nginx / haproxy"]
    end

    subgraph API["🌐 API Servers"]
        S1["udr serve<br/>Worker 1"]
        S2["udr serve<br/>Worker 2"]
        S3["udr serve<br/>Worker N"]
    end

    subgraph Cache["⚡ Cache Layer"]
        REDIS["Redis<br/>Rate limiting · Caching"]
        DICTCACHE["DictCache<br/>(in-memory, single worker)"]
    end

    subgraph DB["🗄️ Database"]
        PG["PostgreSQL<br/>Primary"]
        PG_REPLICA["PostgreSQL<br/>Read replica"]
        SQLITE["SQLite<br/>(single-user default)"]
    end

    subgraph External["🌍 External Registries"]
        PYPI_REG["PyPI"]
        NPM_REG["npm"]
        CRATES_REG["Crates.io"]
        MORE_REG["+ 13 more registries"]
    end

    DEV -->|"direct CLI"| API
    CI -->|"direct CLI"| API
    DESKTOP -->|"localhost:PORT"| S1
    APP --> NGINX
    NGINX --> S1
    NGINX --> S2
    NGINX --> S3
    S1 --> REDIS
    S2 --> REDIS
    S3 --> REDIS
    S1 --> PG
    S2 --> PG
    S3 --> PG
    PG -.->|"replication"| PG_REPLICA
    S1 -.->|"fallback"| DICTCACHE
    S2 -.->|"fallback"| DICTCACHE
    S3 -.->|"fallback"| DICTCACHE
    S1 -.->|"single-user"| SQLITE
    API -.->|"async HTTP"| External

    style DEV fill:#2e7d32,color:#fff,stroke:#1b5e20,stroke-width:2px
    style CI fill:#2e7d32,color:#fff,stroke:#1b5e20,stroke-width:2px
    style APP fill:#1565c0,color:#fff,stroke:#0d47a1,stroke-width:2px
    style DESKTOP fill:#e65100,color:#fff,stroke:#bf360c,stroke-width:2px
    style PG fill:#00695c,color:#fff,stroke:#004d40,stroke-width:2px
    style REDIS fill:#c62828,color:#fff,stroke:#b71c1c,stroke-width:2px
    style SQLITE fill:#424242,color:#fff,stroke:#212121,stroke-width:2px
```

**Key deployment paths:**

| Scenario | Path | Database | Cache |
|---|---|---|---|
| **Single dev** | `udr resolve flask` (direct CLI) | None needed | DictCache |
| **Single-user server** | `udr serve` | SQLite (`udr.db`) | DictCache |
| **Production multi-worker** | nginx → 2+ workers → PostgreSQL | PostgreSQL | Redis |
| **Desktop app** | Electron → localhost backend | SQLite (`~/.udr/`) | DictCache |
| **CI/CD pipeline** | `udr lock`, `udr verify` | None (lock file only) | DictCache |

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

Auth is enabled by default (ENABLE_AUTH=true). To disable: set ENABLE_AUTH=false.

```bash
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
