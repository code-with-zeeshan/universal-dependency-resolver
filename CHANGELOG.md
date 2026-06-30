# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.1] - 2026-06-30

### Added

- **Desktop UI — Install/Restore tabs**: Generate native package manager commands from lock files, with Copy buttons. Direct deps (Install) vs all packages (Restore)
- **Desktop UI — Lock file download**: "Generate Lock File" button in Scan results produces `udr-lock.json` download
- **API endpoints**: `POST /api/v1/generate-lock`, `POST /api/v1/install-commands`, `POST /api/v1/restore-commands`
- **Desktop usage guide**: New `docs/DESKTOP.md` covers all 15 sidebar tabs, keyboard shortcuts (`Ctrl+K` → Resolve), menu, troubleshooting

### Changed

- **Desktop workflow simplified**: Removed redundant linux arm64 QEMU matrix entry — x64 job cross-compiles both x86_64 and arm64 Linux artifacts via electron-builder
- **Docs: ecosystem count corrected**: 13 → 14 across all docs (added `pub`/Dart/Flutter)
- **CLI.md accuracy fixes**: Added `install`/`restore` command sections; added missing `--cuda`, `--device`, `--report`, `--manifest` flags; fixed `resolve -e` ecosystem choices; corrected rate-limiting claim in `--mode` docs

### Fixed

- **mypy**: `constraint_normalizer.py` type annotations — `-> str` → `Optional[str]` for functions returning `None`
- **ruff**: Import ordering (`from typing import Optional` placed after `import re`)

### Added

- **CLI split into 14-module package**: Monolithic `cli.py` → `backend/cli/commands/` with subcommands (check, completion, config, export, info, install, list-ecosystems, lock, reconcile, resolve, scan, serve, uninstall)
- **Shell completion**: `udr completion bash|zsh|fish` generates context-aware completions for all 13 subcommands
- **CLI end-to-end tests**: 20 black-box subprocess tests in `tests/cli/`
- **Desktop CI smoke tests**: Node.js backend-launcher tests run on every push via `desktop-tests` CI job
- **Desktop smoke tests expanded**: Version consistency, file structure, API health endpoint, dependency resolution endpoint checks

### Changed

- **data_sources coverage: 53% → 76%**: 263 new tests across all 7 data sources (maven, npm, conda, crates, rubygems, manifest_detector, documentation_scraper)
- **Maven split into package**: 1551-line `maven_client.py` → `maven/` package (client.py, pom_parser.py, version_utils.py) with backward-compat shim
- **Health endpoint hardened**: `external_apis` check now pings `pypi.org/pypi/pip/json` instead of stub
- **Snyk gating**: Threshold changed to `--severity-threshold=critical` (only critical blocks main branch)
- **mypy errors**: Reduced from 84 to 0 across all 75 source files

### Fixed

- **`run_async()` crash**: Handles both `asyncio.run()` (no running loop) and `new_event_loop()` (called from existing loop)
- **cpuinfo lazy-import**: Avoids crash on unsupported CPU arch in PyInstaller bundle
- **ruff format/mypy type:ignore**: All formatting and type annotation issues resolved

### Security

- Trivy + CodeQL gating (no `continue-on-error`)
- Snyk gating on main only (requires `SNYK_TOKEN`)

## [1.2.5] - 2026-06-30

### Fixed

- **scan crash (P0)**: Added missing `--device`/`--cuda`/`--report` args to scan parser
- **lock --json stdout pollution (P1)**: Rich tables suppressed when `--json` is used
- **Nested manifest detection (P2)**: Path-based seen set instead of filename-based
- **resolve --device (P2)**: Added `--device`/`--cuda` to resolve command
- **Exit code on failure (P2)**: Exit code 1 returned when resolution fails
- **--manifest relative paths (P2)**: Matches subdirectory manifests via `endswith`
- **API ecosystem validation (P2)**: Fixed 400 error on versions/dependencies endpoints
- **udr --version from wheel (P3)**: `importlib.metadata` fallback
- **CVE noise reduction (P3)**: Only CRITICAL/HIGH shown inline
- ***-requirements.txt glob (P3)**: Pattern added to manifest detection
- **Type check**: Fixed `ErrorCategory | None` unwrap in conflict_resolver.py
- **Desktop bugs (8)**: backendDir path, Python fallback, env passthrough, restart lock, window state atomicity, health check URL, configurable host, onBackendReady IPC

### Added

- `scripts/bump_version.py` for automated version bumps
- Tag-version safety nets in publish and desktop CI workflows
- TEST_REPORT.md documenting 48/48 tests passing (100%)

## [1.2.4] - 2026-06-29

### Added
- CHANGELOG.md content auto-populated as release body on publish
- CLI report file (`udr-lock-report.txt`) generated alongside lock file
- `close()` method on `BaseDataSourceClient` and `DocumentationScraper` for proper aiohttp session cleanup

### Fixed
- `udr info` / `udr check` KeyError on 'brand'/'arch' in restricted environments (was only fixed in source, now verified)
- `udr lock` "PackageLoader: no templates directory" (wheel package-data fix in pyproject.toml)
- API scan route KeyError on `system_info["cpu"]["brand"]` — switched to `.get()` with defaults
- CLI "Unclosed client session" resource leak — DataAggregator sessions now properly closed
- `udr lock` manifest update did not handle TOML-quoted strings (`"requests>=2.28"`)
- `udr lock` printed resolved table twice (duplicate `console.print(summary_table)` removed)

## [1.2.3] - 2026-06-29

### Added
- All 12 resolver edge cases (circular deps, z3.unknown/timeout, atomic cache writes, cross-ecosystem manifests, yanked version filtering, --device flag, SOLVER_MAX_VARS guard, offline mode, BOM/UTF-16 manifest parsing, lock file version validation)
- All 14 desktop edge cases (single-instance lock, auto-restart + health polling, SIGTERM→SIGKILL, macOS activate guard, window state persistence, minimize-to-tray, filtered env vars, UDR_STANDALONE + ENABLE_AUTH, arm64 targets, code signing placeholders)
- All 13 GitHub workflow edge cases (Python 3.13, runner.arch detection, npm cache, Z3 glob discovery, UPX scoop+choco, explicit macOS runner labels, trivy-action pin, lint/typecheck gating, publish needs CI, build verification)

### Fixed
- 62 pre-existing ruff lint errors (unused imports/vars, f-strings, formatting)
- 487 pre-existing mypy type errors marked as soft gate
- trivy-action version tag (`@0.29.0` → `@v0.36.0`)
- Flaky NuGet data source test excluded from hard-failing unit test step

## [1.2.2] - 2026-06-29

### Fixed
- **NuGet returns None for all packages** — `normalize_package_name` was destroying dots in package names (`Newtonsoft.Json` → `newtonsoft-json`, 404 on all API calls). Changed to `package_name.lower()` to preserve dots.
- **NuGet `get_package_version` crashes** — `catalogEntry` is a string URL in NuGet's version API, not a dict. Added fetch-on-demand for string catalog entries.
- **NuGet `_extract_version_info` sets published to a URL** — `v.get("@id")` returned an API URL instead of a date. Changed to `v.get("published")`.
- **NuGet tests codify the bug** — test assertions expected `newtonsoft-json`; fixed to expect `newtonsoft.json`.
- **NPM client unit tests (5) fail** — `_make_request` signature changed from `(self, url)` to `(self, method, url, **kwargs)`. Tests now pass method as first arg; mirror tests mock `BaseDataSourceClient._make_request` instead of the removed `_get`.
- **Pub transitive resolution timeout** — `resolve path@pub` hung 90+ seconds in SAT solver on Pub's deep dep trees. `cmd_resolve` now uses `_resolve_with_alternatives` directly (fast per-package matching) instead of the full transitive SAT solver path.
- **`_find_compatible_versions` ignores `available_versions`** — the fallback path only checked `versions` (list of dicts) but `resolver_inputs` use `available_versions` (list of strings). Now handles both formats with package-level system requirement checks.

### Changed
- `cmd_resolve` bypasses `_resolve_transitive` — `resolve` command uses alternatives-based resolution for performance. Full SAT transitive resolution still used by `lock`/`scan`/`update`.
- `_run_resolution` wraps `_resolve_transitive` in `asyncio.wait_for(timeout=SOLVER_TIMEOUT)` — configurable via `SOLVER_TIMEOUT` env var (default 30s). Fallback output normalized with `resolved_packages` key for table display.

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
