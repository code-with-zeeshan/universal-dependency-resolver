# Universal Dependency Resolver - Architecture Documentation

## Dependency Flow Tree

```
┌──────────────────────────────────────────────────────────────────┐
│                       Desktop Layer                               │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  main.js (Electron main process)                         │    │
│  │    ├── backend-launcher.js                               │    │
│  │    └── preload.js                                        │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                         API Layer                                 │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  api/main.py                                             │    │
│  │    ├── api/schemas.py                                    │    │
│  │    ├── api/dependencies.py                               │    │
│  │    ├── api/middleware.py                                 │    │
│  │    ├── api/auth.py                                       │    │
│  │    ├── api/exceptions.py                                 │    │
│  │    ├── api/routes/packages.py                            │    │
│  │    ├── api/routes/system.py                              │    │
│  │    ├── api/routes/auth.py                                │    │
│  │    └── api/routes/scan.py                                │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                        Core Logic                                 │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  core/conflict_resolver.py  ◄── uses ──┐                │    │
│  │  core/data_aggregator.py  ◄─── uses ───┤                │    │
│  │  core/export_generator.py              │                │    │
│  │  core/system_scanner.py                │                │    │
│  │  core/cache.py ◄──────── used by all ──┤                │    │
│  │  core/utils.py ◄────────── used by all ┘                │    │
│  │  cli.py ◄────── command-line interface                   │    │
│  │  manifest_detector.py ◄─── scan uses                     │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
┌──────────────────────────┐ ┌──────────────────────────────────┐
│      Data Sources        │ │         Database                 │
│  ┌──────────────────┐    │ │  ┌──────────────────────────┐    │
│  │ base_client.py   │    │ │  │ database/models.py       │    │
│  │ pypi_client.py   │    │ │  │ database/compatibility_db│    │
│  │ npm_client.py    │    │ │  └──────────────────────────┘    │
│  │ conda_client.py  │    │ │            ▲                    │
│  │ maven_client.py  │    │ │            │                    │
│  │ crates_client.py │    │ │  ┌──────────────────────────┐    │
│  │ apt_client.py    │    │ │  │ alembic/env.py           │    │
│  │ gomodules_client │    │ │  └──────────────────────────┘    │
│  │   + 7 more         │    │                                  │                                  │
│  └──────────────────┘    │ │  SQLite (default) or PostgreSQL  │
└──────────────────────────┘ └──────────────────────────────────┘
```

## File Interconnection Matrix

| File | Imports/Uses | Imported By | Purpose |
|------|--------------|-------------|---------|

| **Backend API** | | | |
| `api/main.py` | All routes, middleware, auth | - | FastAPI app entry point |
| `api/schemas.py` | - | routes | Pydantic schemas |
| `api/dependencies.py` | schemas, database | routes | FastAPI DI |
| `api/middleware.py` | exceptions | main.py | Request/response middleware |
| `api/auth.py` | settings, models | routes | JWT + API key auth |
| `api/exceptions.py` | - | middleware | Custom exception handlers |
| `api/routes/packages.py` | core/*, database/* | main.py | Package endpoints |
| `api/routes/system.py` | system_scanner | main.py | System endpoints |
| `api/routes/auth.py` | auth, models | main.py | Auth endpoints |
| `api/routes/scan.py` | manifest_detector, cli | main.py | Scan endpoints |
| `settings/` | - | All modules | Config management |
| **Core Logic** | | | |
| `core/conflict_resolver.py` | utils, cache, models | routes | Z3 SAT solver |
| `core/data_aggregator.py` | data_sources/*, utils | routes | Aggregates package data |
| `core/export_generator.py` | utils | routes | Generates exports |
| `core/system_scanner.py` | utils | routes | System package scanner |
| `core/cache.py` | - | All core | DictCache / Redis |
| `cli.py` | core/* | scan | CLI interface |
| `manifest_detector.py` | - | scan | Manifest file parser |
| **Data Sources** | | | |
| `data_sources/base_client.py` | utils, settings | *_client | Base HTTP client |
| `data_sources/pypi_client.py` | base_client | data_aggregator | PyPI API |
| `data_sources/npm_client.py` | base_client | data_aggregator | NPM registry |
| `data_sources/conda_client.py` | base_client | data_aggregator | Conda Forge |
| `data_sources/maven_client.py` | base_client | data_aggregator | Maven Central |
| `data_sources/crates_client.py` | base_client | data_aggregator | Crates.io |
| + 8 more clients | base_client | data_aggregator | apt, apk, nuget, etc. |
| **Database** | | | |
| `database/models.py` | - | All modules | SQLAlchemy models |
| `database/compatibility_db.py` | models | conflict_resolver | Compatibility matrix |

## Key Integration Points

| Integration | Components | Protocol |
|-------------|------------|----------|
| Desktop → Backend | backend-launcher → FastAPI routes | REST API + JWT |
| API → Core | Routes → Core modules | Python imports |
| Core → Data Sources | data_aggregator → *_client | Python async/await |
| Core → Database | All modules → models | SQLAlchemy ORM |
| Core → Cache | All modules → cache.py | DictCache / Redis |

## Module Dependencies Graph

```
                    .env.example
                         │
settings/ ──────────────┴─────────┐
     │                             │
     ├──────────────┐              │
     ▼              ▼              ▼
utils.py        cache.py      database/
     │              │         models.py
     ▼              ▼              │
data_sources/*  (used by)          │
     │              │              │
     ▼              ▼              ▼
data_aggregator ────────► compatibility_db
     │                             │
     ├─────────────┐               │
     ▼             ▼               ▼
conflict_resolver  export_generator  system_scanner  cli.py
     │                   │              │               │
     └─────────┬─────────┴──────────────┘               │
               ▼                                        │
          dependencies.py    ◄───  manifest_detector.py │
               │                           │            │
          schemas.py                       │            │
               │                           │            │
          auth.py                          ▼            │
               │                    routes/scan.py ─────┘
               │
    ┌──────────┴──────────┐
    ▼                     ▼
routes/packages     routes/system  routes/auth
    │                     │              │
    └──────────┬──────────┴──────────────┘
               │
       exceptions.py  middleware.py
               │         │
               └────┬────┘
                    ▼
               api/main.py
                    │
                     ▼
              Desktop App (Electron)
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
   Resolve GUI  System Info  Scan Project  Export
         │           │           │           │
         ▼           ▼           ▼           ▼
         index.html — inline HTML/CSS/JS (no framework)
  ResolvePanel  SystemPanel
                SystemInfo.vue
```





## Configuration and Environment Setup

```
.env.example
     │
     ├── Database
     │   └── DATABASE_URL (default: sqlite:///./udr.db)
     │
     ├── Optional Redis
     │   └── REDIS_URL (falls back to DictCache)
     │
     ├── Auth (UDR_MODE=saas)
     │   ├── SECRET_KEY
     │   ├── UDR_MODE
     │   └── ENABLE_CSRF
     │
     ├── Desktop / Standalone
     │   ├── UDR_DESKTOP
     │   └── UDR_STANDALONE
     │
     └── Monitoring (optional)
         ├── SENTRY_DSN
         └── PROMETHEUS_ENABLED
```

## Docker Container Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  docker-compose.yml                        │
├──────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌────────────────┐  │
│  │   Backend    │  │   Database     │  │
│  │  python:3.11 │  │  postgres:15   │  │
│  │  Port: 8000  │  │  Port: 5432    │  │
│  └──────┬───────┘  └────────────────┘  │
│         │                               │
│    ┌────┴───────┐                       │
│    │   Redis    │ (optional)            │
│                    │  redis:7     │                       │
│                    └──────────────┘                       │
└──────────────────────────────────────────────────────────┘
```

Without Docker: run directly with `DATABASE_URL=sqlite:///./udr.db` — no PostgreSQL, no Redis needed.

## Database Schema Relationships

```
┌──────────────────────────────────────────────┐
│              Database Models                  │
├──────────────────────────────────────────────┤
│                                              │
│  ┌──────────────┐       ┌────────────────┐   │
│  │    Users     │       │    APIKeys     │   │
│  ├──────────────┤       ├────────────────┤   │
│  │ id (PK)      │──1:N──│ id (PK)        │   │
│  │ username     │       │ user_id (FK)   │   │
│  │ email        │       │ key            │   │
│  │ hashed_pw    │       │ name           │   │
│  └──────────────┘       │ is_active      │   │
│                         └────────────────┘   │
│  ┌──────────────┐       ┌────────────────┐   │
│  │  Packages    │       │Compatibility...│   │
│  ├──────────────┤       ├────────────────┤   │
│  │ id (PK)      │──1:N──│ package_id (FK)│   │
│  │ name         │       │ constraint     │   │
│  │ ecosystem    │       │ compatible     │   │
│  │ description  │       └────────────────┘   │
│  └──────────────┘                            │
└──────────────────────────────────────────────┘
```

## Error Handling Flow

```
Backend:
  exceptions.py → Custom exception classes
  middleware.py → Global error handler (consistent {error: {message, type, ...}} format)
  Route handlers → Try/except with HTTPException
  Core modules → Raise ValueError / custom exceptions
```

## Caching Strategy

```
Multi-Level Cache:
┌─────────────────────────────────────┐
│  Backend Cache (cache.py)           │
│  ┌─────────────────────────────┐    │
│  │  DictCache (default)        │    │
│  │  - Pure Python dict + TTL   │    │
│  │  - Works without Redis      │    │
│  └─────────────────────────────┘    │
│  ┌─────────────────────────────┐    │
│  │  Redis Cache (optional)     │    │
│  │  - Falls back to DictCache  │    │
│  │  - aiocache based caching   │    │
│  │  - Cluster/connection pool  │    │
│  └─────────────────────────────┘    │
└─────────────────────────────────────┘
```

## Testing Structure

```
├── Desktop Tests (Node --test, 19 tests)
│   └── backend-launcher.test.js
│
└── Backend Tests (pytest, 422 tests)
    ├── Unit
    │   ├── Core module tests
    │   ├── Data source tests (13 files)
    │   ├── API route tests
    │   ├── CLI tests (16 tests)
    │   └── Settings tests (6 tests)
    ├── Integration (3 files, ~550 lines, SQLite fallback)
    └── Performance (K6 load test)
```

## Security Layers

```
API Security (auth.py):
  - JWT authentication (access + refresh tokens)
  - API key authentication (X-API-Key header)
  - Scope-based authorization
  - Optional: disable auth for development

Backend:
  - SQL injection protection (ORM)
  - Password hashing (bcrypt)
  - Rate limiting (slowapi)
  - Security headers (HSTS, CSP, XFO)
  - Correlation ID middleware
  - Auth: opt-in via UDR_MODE=saas
```

## Infrastructure Pipeline

```
Git Push → CI Workflow → Tests → Build → Deploy
               │                       │
               └── Docker ─────────────┘
                   (Desktop + Backend)
```

## Project Directory

```
universal-dependency-resolver/
├── .env.example
├── .github/workflows/
│   ├── ci.yml
│   ├── publish.yml
│   └── release-desktop.yml
├── alembic/
│   ├── env.py
│   └── versions/
├── backend/
│   ├── api/
│   │   ├── auth.py
│   │   ├── dependencies.py
│   │   ├── exceptions.py
│   │   ├── main.py
│   │   ├── middleware.py
│   │   ├── schemas.py
│   │   └── routes/
│   │       ├── auth.py
│   │       ├── packages.py
│   │       ├── scan.py
│   │       └── system.py
│   ├── cli.py
│   ├── core/
│   │   ├── cache.py
│   │   ├── conflict_resolver.py
│   │   ├── data_aggregator.py
│   │   ├── export_generator.py
│   │   ├── system_scanner.py
│   │   └── utils.py
│   ├── data_sources/
│   │   ├── base_client.py
│   │   ├── pypi_client.py
│   │   ├── npm_client.py
│   │   ├── conda_client.py
│   │   ├── maven_client.py
│   │   ├── crates_client.py
│   │   └── ... (9 more ecosystem clients)
│   ├── database/
│   │   ├── models.py
│   │   └── compatibility_db.py
│   ├── logging_config.py
│   ├── manifest_detector.py
│   ├── settings/
│   ├── tracing_config.py
│   └── utils/
│       └── errors.py
├── desktop/
│   ├── backend-launcher.js
│   ├── main.js
│   ├── preload.js
│   ├── package.json
│   ├── assets/ (tray icon)
│   └── tests/ (backend-launcher.test.js)
├── docs/ (this directory)
├── monitoring/
│   ├── prometheus.yml
│   ├── alert_rules.yml
│   └── setup_monitoring.sh
├── scripts/ (setup, deploy, backup, tests)
├── tests/
│   ├── conftest.py
│   ├── unit/ (CLI, API, core, data sources, settings)
│   ├── integration/ (API + DB + data flow, SQLite)
│   └── fixtures/
├── docker-compose.yml
├── docker-compose.prod.yml
├── pyproject.toml
├── install.sh
├── CHANGELOG.md
├── README.md
└── docs/ (this directory)
```
