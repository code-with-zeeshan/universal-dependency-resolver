# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-06-25

### Added
- **Desktop Electron app** (`desktop/`) — spawns Python backend, IPC bridge, electron-builder
- **Project scan feature** — GitHub repo / zip upload / local directory manifest detection and dependency resolution
- **CLI tool** (`backend/cli.py`) — `resolve`, `lock`, `scan` commands with Z3 SAT solver
- **DictCache fallback** — pure-Python in-memory cache when Redis is unavailable
- **SQLite default** — `DATABASE_URL` defaults to `sqlite:///./udr.db`, no PostgreSQL required
- **Manifest detection** (`manifest_detector.py`) — detects requirements.txt, package.json, Dockerfile, Cargo.toml, and 20+ manifest formats
- **Lazy client creation** in `data_aggregator.py` — 15 HTTP clients no longer created eagerly
- **`install.sh`** — one-command bootstrap (Docker or manual)
- **4 new workflow files** — `integration-test.yml`, `release-desktop.yml`, `publish.yml`, `deploy.yml`

### Changed
- PostgreSQL and Redis are now **optional** — SQLite + DictCache cover all standalone/desktop use cases
- FastAPI pinned to `>=0.115.0,<0.116` for pydantic 2.x compatibility
- `prometheus-fastapi-instrumentator` pinned to `>=6.1,<7` (avoids starlette 1.x breaking changes)
- `validate_environment()` reads `settings.DATABASE_URL` instead of raw `os.getenv`
- `export_generator.py` uses `PackageLoader` for Electron/frozen-packaged compatibility
- CLI `_parse_package_spec` uses `rsplit("@", 1)` for npm scoped packages (`@angular/core@npm`)
- All GitHub workflows audited and fixed: 12 issues resolved (env vars, pip install, YAML, `|| true`, etc.)

### Removed
- WebSocket / SocketIO API (real-time module was aspirational, never wired)
- `grafana/` monitoring dashboards (overkill for pre-v2 project)
- `monitoring/grafana/` directory and provisioning configs
- 3 aspirational `backend/api/realtime/` files
- Redis as a hard dependency — now optional with graceful fallback

### Fixed
- `test_settings.py` no longer poisons other tests (`importlib.reload` + `clear=True` bug)
- Integration tests default to SQLite — no PostgreSQL needed on the host
- `backend/api/main.py`: `validate_environment()` skips Redis check under `UDR_STANDALONE=true`
- All 14 pre-existing test failures fixed (mock/data-shape mismatches, aiohttp cleanup, PostgreSQL requirement)
- `release-desktop.yml`: `npm ci` → `npm install` (no lockfile)
- `ci.yml`: removed `|| true` (was masking test failures)
- `integration-test.yml`: fixed YAML multi-line `:` parsing
- CSRF env var poisoning: `ENABLE_CSRF` must be set in every `os.environ` patch

### Security
- Auth guard prevents production startup with `ENABLE_AUTH=false`
- `desktop/main.js`: `dialog.showErrorBox()` on backend failure
- All 5 workflow YAMLs validated via `yaml.safe_load`

## [Unreleased]

### Added
- **Middleware & Observability**:
  - `CorrelationIDMiddleware` — incoming/preserve `X-Correlation-ID`, binds to structlog contextvars
  - `AuditLogMiddleware` — structured audit events on mutating methods
  - `CSRFProtectionMiddleware` — double-submit cookie pattern, Bearer auth bypass
  - `SecurityHeadersMiddleware` — HSTS, CSP, XFO, nosniff, XSS protection
  - `RequestSizeLimitMiddleware` — configurable max request body size
  - Prometheus SLI recording rules (p99 latency, error rates, availability)
  - Jaeger auto-provisioning via docker-compose monitoring profile
  - Grafana Jaeger datasource auto-provisioned
- **Infrastructure**:
  - `scripts/validate_k8s.sh` — kind cluster creation, manifest validation, cleanup (planned — not committed)
  - `pyproject.toml` — project build metadata
- **Testing**:
  - Middleware tests: 29 tests covering CorrelationID, CSRF, AuditLog, SecurityHeaders, Logging, RequestSizeLimit, GetClientIP
  - Settings validation tests: 6 tests for `validate_settings()`
  - Playwright E2E tests: 20 tests (login, add/remove package, resolve, export, error handling, keyboard, retry)
  - SQLite fallback for integration tests (auto-detects Postgres/Redis availability)
- **Security**:
  - Auth guard in `validate_environment()` — production startup refused without `ENABLE_AUTH=true`
- **Code Quality**:
  - `run_async()` helper to eliminate sync wrapper boilerplate across 10 data source clients
  - `ResolverErrorCode` enum with `ErrorCategory` mapping

### Changed
- Route `/{ecosystem}/{package_name}` → `/{ecosystem}/{package_name}/details` to fix collision with `get_package_info`
- `validate_settings()` performs 6 config checks on startup
- `.env.example` `ENABLE_AUTH` default: `false` with comment about production guard
- `ARRAY(String)` → `JSON` for scopes columns in User/APIKey models (SQLite-compatible)
- `setup_middleware(app)` called at app startup registering all middleware in correct order
- `log_requests` middleware no longer overwrites `X-Request-ID`

### Removed
- Redundant `add_request_id` middleware (replaced by `CorrelationIDMiddleware`)
- Pydantic `BaseSettings` dependency (replaced by `os.getenv()` + `validate_settings()`)
- Dead Pydantic `BaseSettings` import
- `RequirementsTxtFormat`/`PackageJsonFormat` import from export generator tests
- Stale `# MOVED FROM main.py` comments
- Empty `_analyze_compatibility_reports` body

### Fixed
- Route path collision (both `get_package_info` and `get_package_details` bound to `/{ecosystem}/{name}`)
- 118 bare `except:` → `except Exception:` across 20 files (silent swallow of KeyboardInterrupt/SystemExit)
- 18 F821 undefined-name errors across 6 files
- `get_current_user` import path in integration conftest (`dependencies` → `auth`)
- CSRF test DB dependency: overrode `get_data_aggregator`/`get_conflict_resolver`/`get_system_scanner` to avoid PostgreSQL requirement
- gRPC OTLP exporter import wrapped in `try/except ImportError`

### Security
- Auth guard prevents production startup with authentication disabled
- CSRF protection with double-submit cookie pattern
- Security headers on all API routes

## [1.0.0] - 2024-01-15

### Added
- Initial release of Universal Dependency Resolver
- Package search across multiple ecosystems
- Intelligent conflict resolution using SAT solver
- System compatibility checking
- Export to 14+ different formats
- Real-time system scanning
- Comprehensive API documentation
- Docker deployment support
- Production-ready monitoring setup

### Features
- **Multi-Ecosystem Support**: PyPI, NPM, Conda, Maven, Crates.io
- **Conflict Resolution**: Advanced SAT-solver based dependency resolution
- **System Scanning**: Comprehensive OS, CPU, GPU, and runtime detection
- **Export Formats**: Requirements.txt, package.json, Dockerfile, and more
- **Performance**: Redis caching, async operations, optimized queries
- **Security**: Rate limiting, authentication, input validation

### Technical Stack
- **Frontend**: Vue 3, Tailwind CSS, Axios
- **Backend**: FastAPI, SQLAlchemy, Alembic
- **Database**: PostgreSQL, Redis
- **Infrastructure**: Docker, Nginx, Prometheus, Grafana
- **Testing**: Jest, Pytest, Playwright

---

## How to Update This Changelog

When making changes to the project:

1. Add new entries under `[Unreleased]` section
2. Use the following categories:
   - `Added` for new features
   - `Changed` for changes in existing functionality
   - `Deprecated` for soon-to-be removed features
   - `Removed` for now removed features
   - `Fixed` for any bug fixes
   - `Security` for security improvements

3. When releasing a new version:
   - Move unreleased changes to a new version section
   - Add the release date
   - Create a new empty `[Unreleased]` section

### Example Entry Format:
```markdown
### Added
- New package ecosystem support for Go modules
- Real-time dependency resolution updates via WebSocket
- Package vulnerability scanning integration

### Fixed
- Fixed memory leak in package caching system
- Resolved CORS issues with frontend authentication