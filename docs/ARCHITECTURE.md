# Architecture

```
                         ┌──────────────────────┐
                         │    Desktop App        │
                         │  (Electron + GUI)     │
                         └────────┬─────────────┘
                                  │ localhost:PORT
                                  ▼
┌────────────────────────────────────────────────┐
│              API Layer (FastAPI)                │
│  main.py  middleware.py  exceptions.py         │
│  ┌──────────────────────────────────────────┐  │
│  │  routes/                                 │  │
│  │  packages.py   system.py  auth.py        │  │
│  │  scan.py       lock.py                   │  │
│  └──────────────────────────────────────────┘  │
└────────────────────┬───────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────┐
│               Core Logic                        │
│  conflict_resolver.py   data_aggregator.py     │
│  export_generator.py    system_scanner.py      │
│  cache.py               utils.py               │
│  cli.py                 manifest_detector.py   │
└────────┬───────────────────────────┬───────────┘
         │                           │
         ▼                           ▼
┌──────────────────┐  ┌──────────────────────────┐
│  Data Sources     │  │  Database                │
│  base_client.py   │  │  models.py               │
│  pypi_client.py   │  │  compatibility_db.py     │
│  npm_client.py    │  │                          │
│  conda_client.py  │  │  SQLite (default) or     │
│  + 9 more         │  │  PostgreSQL              │
└──────────────────┘  └──────────────────────────┘
```

## Layer breakdown

### API layer (`backend/api/`)

Entry point: `api/main.py` — creates the FastAPI app, registers middleware and routes.

- **Auth** (`api/auth.py`) — JWT + API key authentication. Only registered when `ENABLE_AUTH=true`. Default is anonymous access.
- **Middleware** (`api/middleware.py`) — request ID, CORS, security headers, rate limiting, request size limits, correlation ID, response time.
- **Schemas** (`api/schemas.py`) — Pydantic request/response models.
- **Dependencies** (`api/dependencies.py`) — FastAPI dependency injection (database session, data aggregator, resolver, scanner).

Routes:

| Path prefix | File | Endpoints |
|---|---|---|
| `/api/v1/packages` | `packages.py` | Search, info, details, versions, dependencies, compatibility, resolve, export, export-formats, ecosystems |
| `/api/v1/system` | `system.py` | Info, check-compatibility |
| `/api/v1/auth` | `auth.py` | Register, login, logout, token, refresh, profile, api-keys, verify |
| `/api/v1/scan` | `scan.py` | GitHub repo, upload archive, local directory |
| `/api/v1` | `lock.py` | Verify, graph, update |

### Core logic (`backend/core/`)

- **`conflict_resolver.py`** — Z3 SAT solver. All 13 data source clients loaded lazily via `importlib.import_module()`. `import z3` deferred to inside 7 methods.
- **`data_aggregator.py`** — Aggregates package data from all ecosystem clients. Uses `asyncio.gather` for concurrent fetching.
- **`export_generator.py`** — Jinja2 template-based export. 12 formats using `.j2` templates.
- **`system_scanner.py`** — Detects OS, CPU, GPU, CUDA, Python, Node.js, GCC, Java. Results cached with 5-min TTL.
- **`cache.py`** — `DictCache` (in-memory dict + TTL, no dependencies) with optional Redis fallback.
- **`manifest_detector.py`** — Scans project directories for 20+ manifest formats (requirements.txt, package.json, Cargo.toml, etc.)

### Data sources (`backend/data_sources/`)

13 ecosystem clients, all inheriting from `BaseClient`:

| Client | Ecosystem | Registry |
|---|---|---|
| `pypi_client.py` | PyPI | pypi.org |
| `npm_client.py` | npm | registry.npmjs.org |
| `conda_client.py` | Conda | repo.anaconda.com / conda-forge |
| `maven_client.py` | Maven | repo1.maven.org |
| `crates_client.py` | Crates.io | crates.io |
| `gomodules_client.py` | Go Modules | proxy.golang.org |
| `nuget_client.py` | NuGet | api.nuget.org |
| `rubygems_client.py` | RubyGems | rubygems.org |
| `packagist_client.py` | Packagist (PHP) | packagist.org |
| `homebrew_client.py` | Homebrew | formulae.brew.sh |
| `cocoapods_client.py` | CocoaPods | trunk.cocoapods.org |
| `apt_client.py` | APT (Debian) | deb.debian.org |
| `apk_client.py` | APK (Alpine) | dl-cdn.alpinelinux.org |

All clients are lazily registered — they are only imported when their ecosystem is first accessed.

### Database (`backend/database/`)

- **`models.py`** — SQLAlchemy ORM models. Schema created via `Base.metadata.create_all()` (no Alembic). SQLite by default, PostgreSQL optional.
- **`compatibility_db.py`** — Compatibility matrix operations.

## Key design decisions

- **Lazy loading**: `import z3` inside methods (not at module level), 13 data source clients via `_register_client()` with `importlib`. Saves ~1s on every CLI command that doesn't need resolution.
- **SQLite first**: No PostgreSQL or Redis required. SQLite + DictCache work for all standalone/desktop use cases.
- **Auth conditionally registered**: `ENABLE_AUTH=false` by default. Auth router only mounted when explicitly enabled.
- **Settings trimmed**: ~200 lines of core settings. Removed Celery, email, webhooks, monitoring, rate-limit-for-each-endpoint, and other server-only configs.
- **No Docker**: Tool ships as `pip install ud-resolver` and as a desktop app. Docker export templates (Dockerfile.j2, docker-compose.yml.j2) are user-facing features for exporting resolved dependencies.

## Testing

```
tests/
├── unit/         → 399 tests (CLI, API, core, data sources, settings)
├── integration/  → 69 tests (API + DB + data flow, uses SQLite)
│   conftest.py   → SQLite fallback, optional Redis
└── conftest.py   → shared fixtures
```

Integration tests default to SQLite (no PostgreSQL needed). Tests use `_patch_engine` to substitute the production database engine with the test engine.
