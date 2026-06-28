# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.1] - 2026-06-28

### Added
- Desktop Electron app (`desktop/`) — bundled Python backend via PyInstaller, GUI, system tray, auto-update, notifications
- CLI tool (`backend/cli.py`) — 9 commands: serve, check, resolve, info, lock, graph, verify, list-ecosystems, update
- SAT-based conflict resolution via Z3
- System scanner: OS, CPU, GPU, CUDA, Python, Node.js, GCC, Java detection
- Export generator: 12 formats (requirements.txt, package.json, Dockerfile, docker-compose.yml, pyproject.toml, environment.yml, Cargo.toml, build.gradle, pom.xml, CMakeLists.txt, install.sh, install.bat)
- Manifest detector: auto-detects 20+ manifest formats
- Lazy client creation in data_aggregator.py — 13 HTTP clients loaded on demand
- CLI startup optimization: `import z3` moved to inside methods, all data source imports deferred
- Concurrent package fetching via `asyncio.gather` in API routes, CLI resolve, and CLI lock
- System info caching with 5-minute TTL on API resolve requests
- DictCache fallback when Redis is unavailable
- SQLite as default database, no PostgreSQL required

### Changed
- PostgreSQL and Redis are now optional — SQLite + DictCache cover all standalone/desktop use cases
- All 7 synchronous `package_exists()` methods converted to async aiohttp
- Registry URL constants inlined from settings into `get_ecosystem_config()` and 9 data source clients
- Settings trimmed from 595 → ~200 lines: removed Celery, Email, Webhooks, WebSockets, File upload, Prometheus/Sentry/OTEL settings
- Integration tests default to SQLite — no PostgreSQL needed on the host
- FastAPI pinned to `>=0.115.0,<0.116` for pydantic 2.x compatibility

### Removed
- `monitoring/` directory (Prometheus, Grafana, Loki, Promtail — server infra)
- `alembic/` directory and `alembic` dependency — `Base.metadata.create_all()` handles schema
- `scripts/` directory — only `sync-version.py` kept
- `backend/Dockerfile` and `build-docker` CI job — Docker is not a distribution channel
- All docker-compose files, `.dockerignore`, `start_dev.sh`, `sonar-project.properties`
- Dead test files: `load_test.js`, `TestSystemBenchmark`, `TestVerifiedCombination`, `test_middleware.py`
- Dead API endpoints: `/compatibility/report`, `/compare`, `/gpu/info`, `/runtime/{runtime}`, `/analyze-environment`, `/benchmarks`
- `requests` dependency (all usage replaced with `aiohttp`)

### Fixed
- Integration test isolation: `db_session` fixture cleans tables between tests, preventing data leakage from API tests
- SQLite foreign key enforcement: `PRAGMA foreign_keys=ON` event listener added for SQLite connections
- All 21 tests updated for async `package_exists()` conversions
- Settings tests no longer poison other tests (fixed `importlib.reload` + `clear=True` bug)
- Route path collision: package details moved from `/{ecosystem}/{name}` to `/{ecosystem}/{name}/details`
- `export_generator.py` uses `PackageLoader` for frozen-packaged compatibility
- CLI `_parse_package_spec` uses `rsplit("@", 1)` for npm scoped packages

## [1.1.0] - 2026-06-25

### CI & Deploy
- CI pipeline: all 11 jobs fixed and passing
- Backend: lazy opentelemetry imports, defensive system info, DataAggregator/CompatibilityDB fixes
- Integration tests: 5 pre-existing failures fixed
- Desktop: Electron blank screen fix (extraResources for frontend dist)
- Removed `deploy.yml` (all jobs disabled)

### Publishing
- Publishes to PyPI (`pip install ud-resolver`) via trusted publishing
- Uploads `.whl` to release assets on publish
- Loosened version pins (fastapi, uvicorn, packaging) to avoid Colab conflicts

### Documentation cleanup
- Removed internal audit docs (CODEREVIEW.md, weaknesses.md)
- Fixed placeholders, emails, contradictory instructions
- Removed PyPI defensive note, star-the-repo plea, empty Hall of Fame
