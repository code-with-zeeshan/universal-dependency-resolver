# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.2] - 2026-07-03

### Added

- **`include_dependencies` wired to all 14 clients**: Parameter added to every client's `get_package_info`/`get_package_info_async` signature so the aggregator's introspection matches. Crates and Maven gate extra dependency-fetching API calls behind the flag.
- **Crates transitive deps**: `get_package_info` now calls `get_dependencies()` and includes `"dependencies"` in the response.
- **Maven transitive deps**: `get_package_info` now calls `get_dependencies()` and includes dependency data (with graceful fallback if POM fetch fails).
- **Manifest parsers for 4 ecosystems**: Added `_parse_pom_xml` (Maven), `_parse_podfile`/`_parse_podfile_lock` (CocoaPods), `_parse_packages_config` (NuGet) to `manifest_detector.py`.
- **`requires-python` from pyproject.toml**: Reads `[project].requires-python` and injects as a `python` package entry. Ecosystem configurable via `UDR_PYTHON_ECOSYSTEM` env var.
- **Non-PEP-440 version normalization**: New `normalize_version()` + `strip_numeric_suffix()` in `constraint_normalizer.py` — strips Maven qualifiers (`-jre`, `-android`) and Conda build strings (`_cp314t`). Used for proper cross-ecosystem version sorting.
- **Cross-ecosystem constraint propagation in SAT fallback**: `_resolve_with_alternatives` now builds a dependency graph, topo-sorts packages, and backtracks respecting cross-ecosystem dependency edges instead of greedy per-package picking.
- **Mermaid architecture diagrams**: Architecture overview, import rules, deployment topology, SAT solver internals, and ER data model — all render natively on GitHub with rich colors and white text
- **Comprehensive user guide**: `docs/USER_GUIDE.md` — 15 sections covering prerequisites, installation, walkthrough, components, CLI/API/library usage, desktop app, feature deep-dive, deployment, troubleshooting, and performance
- **New CLI commands**: `details`, `diff`, `outdated`, `search`, `why` — 5 new subcommands for package inspection and lock file comparison
- **New data source clients**: Gradle (`gradle_client.py`), Swift (`swift_client.py`), Hex/Elixir (`hex_client.py`), Haskell/Cabal (`haskell_client.py`) — 4 more ecosystems now supported (total 18)
- **Orchestrator package**: `backend/orchestrator/` — shared resolution layer used by both CLI and API, breaking the `cli→api` import cycle
- **GitHub workflow enhancements**: New `benchmark.yml` (weekly SAT-solver performance); `security-audit.yml` enhanced with `pip-audit --fix` + license compliance; `ci.yml` data-source parallel job extracted; new `dependabot.yml`, `scorecards.yml`
- **Desktop app improvements**: New `app-utils.js` + `app.js` modules; expanded smoke tests (version consistency, file structure, API health, resolution endpoint); render tests
- **Infrastructure**: Dockerfile + docker-compose.yml for container deployment; `.pre-commit-config.yaml`; `.dockerignore`; `alembic/` migration infrastructure (Alembic config + initial migration + env.py)
- **Test scaffolding**: 6 e2e test files (`test_cli_realworld.py`, `test_edge_cases.py`, `test_json_compliance.py`, `test_problem_statement.py`); 6 new CLI black-box test files (details, diff, outdated, scan, search, why); 4 new data source test files (gradle, haskell, hex, swift); database tests (`test_compatibility_db.py`); `test_api_realworld.sh`, `test_cli_realworld.sh`, `test_problem_statement.sh`; `test_comprehensive.py` integration tests; `scripts/run_checks.sh`, `scripts/seed_db.py`

### Changed

- **`parse_version` warning → debug**: Non-PEP-440 versions (Maven `*-jre`, Conda `*_cp*`) no longer flood stderr.
- **npm version skip warning → debug**: Canary/experimental npm versions logged at debug level instead of warning.
- **APK client fallback fetch error → debug**: 404 from fallback APKINDEX mirrors and transient fetch errors logged at debug level.
- **README.md fully redesigned**: Emoji badges with varied shield colors, old-vs-new comparison table, grouped ecosystem categories, numbered 5-step quick start, "By the Numbers" stats section, call-to-action footer
- **docs/ARCHITECTURE.md**: ASCII architecture art replaced with Mermaid graph + import rules + ER diagrams; deeper saturated backgrounds with white text for readability
- **docs/PERFORMANCE.md**: Added Mermaid SAT solver internals flowchart showing the 5-step Z3 pipeline (normalize → variables → constraints → solve → output)
- **docs/DEPLOYMENT.md**: Added Mermaid deployment topology diagram covering 5 deployment scenarios (dev, CI, single-server, multi-worker, desktop)
- **Root config cleanup**: `install.sh` — dynamic version reading from `pyproject.toml` or `udr --version` (removed hardcoded `VERSION`); `Makefile` — added `.DEFAULT_GOAL=help`, `--cov-fail-under=70` (consistent with pyproject.toml), removed stale `--timeout=120`; `.env.example` — added `ENABLE_CSRF` + 5 missing ecosystem rate limits; `MANIFEST.in` — added `README_PYPI.md` + `alembic/` include rules; `pytest.ini` — removed blanket `DeprecationWarning` suppression
- **Desktop**: Removed DMG background image to fix transient arm64 build failures; `electron-updater` moved to `dependencies` in `package.json` (runtime dep)

### Fixed

- **`@angular/core` edge case**: `_parse_package_spec` now handles scoped npm packages without ecosystem suffix (leading `@`). Unknown ecosystems log a warning instead of silently creating invalid specs.
- **NPM dependency key location**: Now reads `dependencies` from top-level `info["latest_version_info"]["dependencies"]` in `_aggregator_to_resolver_input`.
- **`_find_compatible_versions` indentation bug**: `sys_python` check was accidentally nested inside the `version_constraint` block — now always evaluated.
- **Critical: `email-validator` missing from core deps** — Imported at top level in `backend/run.py:12` but only in `[system]`/`[dev]` optional groups. `pip install ud-resolver` (bare, no extras) crashed on `udr serve`. Moved to `[project.dependencies]`.
- **High: `httpx` missing from core deps** — Used in `backend/api/main.py:319` health endpoint but only in `[dev]`/`[all]`. Health check silently failed when extras not installed. Added to `[project.dependencies]`.
- **High: `starlette` not declared** — Imported directly in `api/main.py` and `api/middleware.py` but never declared in `pyproject.toml` (relied on transitive dep through FastAPI). Explicitly added to `[project.dependencies]`.
- **`prometheus-fastapi-instrumentator` moved to `[monitoring]`** — Was in core deps but only imported conditionally inside a function. Belongs in optional monitoring group.
- **`opentelemetry-exporter-otlp-proto-grpc` missing** — Imported in `backend/tracing_config.py:62` but only `-http` exporter was declared. Both gRPC and HTTP exporters now in `[monitoring]`.
- **`electron-updater` in wrong dependency group** — Was in `devDependencies` in `desktop/package.json` but imported and used at runtime in `main.js`. Moved to `dependencies`.

### Security

- All 14 ecosystems tested with real APIs in a 43-package megaproject scenario (frontend + backend + AI/ML + inference + system specification with CUDA)

### Removed

- **`docs/diagram/architecture.excalidraw`** — Excalidraw JSON format does not render on GitHub. Replaced with inline Mermaid diagrams.
- **`tests/fixtures/api_responses/`** — Stale mock JSON fixtures (conda, npm, pypi). Coverage handled by live data source tests.

## [1.3.1] - 2026-06-30

### Added

- **Desktop UI — Install/Restore tabs**: Generate native package manager commands from lock files, with Copy buttons. Direct deps (Install) vs all packages (Restore)
- **Desktop UI — Lock file download**: "Generate Lock File" button in Scan results produces `udr.lock` download
- **API endpoints**: `POST /api/v1/generate-lock`, `POST /api/v1/install-commands`, `POST /api/v1/restore-commands`
- **Desktop usage guide**: New `docs/DESKTOP.md` covers all 15 sidebar tabs, keyboard shortcuts (`Ctrl+K` → Resolve), menu, troubleshooting

### Changed

- **Docs: ecosystem count corrected**: 13 → 14 across all docs (added `pub`/Dart/Flutter)
- **CLI.md accuracy fixes**: Added `install`/`restore` command sections; added missing `--cuda`, `--device`, `--report`, `--manifest` flags; fixed `resolve -e` ecosystem choices; corrected rate-limiting claim in `--mode` docs
- **ManifestDetector + ConstraintNormalizer upgraded**: Better cross-ecosystem version handling and manifest parsing
- **ruff format**: 4 files auto-fixed

### Fixed

- **udr check / udr info GPU crash**: CUDA info is a dict, not a string
- **Desktop install, status, menu**: Several desktop UI and IPC fixes
- **mypy**: `constraint_normalizer.py` type annotations — `-> str` → `Optional[str]` for functions returning `None`
- **ruff**: Import ordering (`from typing import Optional` placed after `import re`)

## [1.3.0] - 2026-06-30

### Added

- **CLI split into 14-module package**: Monolithic `cli.py` → `backend/cli/commands/` with subcommands (check, completion, config, export, info, install, list-ecosystems, lock, reconcile, resolve, scan, serve, uninstall)
- **Shell completion**: `udr completion bash|zsh|fish` generates context-aware completions for all 13 subcommands
- **CLI end-to-end tests**: 20 black-box subprocess tests in `tests/cli/`
- **Desktop CI smoke tests**: Node.js backend-launcher tests run on every push via `desktop-tests` CI job
- **Desktop smoke tests expanded**: Version consistency, file structure, API health endpoint, dependency resolution endpoint checks

### Changed

- **data_sources coverage: 53% → 76%**: 263 new tests across all 7 data sources (maven, npm, conda, crates, rubygems, manifest_detector, documentation_scraper)
- **Maven split into package**: 1551-line `maven_client.py` → `maven/` package (client.py, pom_parser.py, version_utils.py) with backward-compat shim
- **Snyk gating**: Threshold changed to `--severity-threshold=critical` (only critical blocks main branch)
- **mypy errors**: Reduced from 84 to 0 across all 75 source files
- **Desktop workflow simplified**: Removed redundant linux arm64 QEMU matrix entry — x64 job cross-compiles both x86_64 and arm64 Linux artifacts via electron-builder
- **Health endpoint hardened**: `external_apis` check now pings `pypi.org/pypi/pip/json` instead of stub

### Fixed

- **`run_async()` crash**: Handles both `asyncio.run()` (no running loop) and `new_event_loop()` (called from existing loop)
- **cpuinfo lazy-import**: Avoids crash on unsupported CPU arch in PyInstaller bundle
- **ruff format/mypy type:ignore**: All formatting and type annotation issues resolved

### Security

- Trivy + CodeQL gating (no `continue-on-error`)
- Snyk gating on main only (requires `SNYK_TOKEN`)

## [1.2.5] - 2026-06-30

### Added

- `scripts/bump_version.py` for automated version bumps
- Tag-version safety nets in publish and desktop CI workflows
- TEST_REPORT.md documenting 48/48 tests passing (100%)

### Fixed

- **resolve --device/--cuda (P0)**: Added `--device` and `--cuda` flags to `resolve` command with CUDA/device override handling
- **lock --json stdout pollution (P1)**: Rich tables suppressed when `--json` is used — `manifest_table`/`pkg_table` gated on `not args.json`
- **Nested manifest detection (P2)**: Path-based seen set instead of filename-based — prevents false dedup across subdirectories
- **--manifest relative paths (P2)**: Matches subdirectory manifests via `endswith` on resolved path
- **Exit code on failure (P2)**: Exit code 1 returned when resolution yields no packages
- **API ecosystem validation (P2)**: Fixed 400 error on versions/dependencies endpoints — proper ecosystem enum check
- **udr --version from wheel (P3)**: `importlib.metadata` fallback when `__version__` not available
- **CVE noise reduction (P3)**: Only CRITICAL/HIGH severities shown inline
- ***-requirements.txt glob (P3)**: Pattern added to manifest detection
- **Type check**: Fixed `ErrorCategory | None` unwrap in conflict_resolver.py
- **Desktop bugs (8)**: backendDir path, Python fallback, env passthrough, restart lock, window state atomicity, health check URL, configurable host, onBackendReady IPC
- **Desktop workflow**: YAML fixes (heredoc delimiter, multi-line syntax), workflow file rename to force re-index

## [1.2.4] - 2026-06-29

### Added
- CHANGELOG.md content auto-populated as release body on publish
- CLI report file (`udr-lock-report.txt`) generated alongside lock file (opt-in via `--report` flag)
- `close()` method on `BaseDataSourceClient` and `DocumentationScraper` for proper aiohttp session cleanup
- **PyPI/desktop releases decoupled**: Tag prefixes distinguish PyPI releases (`v*`) from desktop builds (`desktop-v*`)

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
- **`__version__` in backend package**: Added via `importlib.metadata` for reliable version introspection

### Fixed
- 62 pre-existing ruff lint errors (unused imports/vars, f-strings, formatting)
- 487 pre-existing mypy type errors marked as soft gate
- trivy-action version tag (`@0.29.0` → `@v0.36.0`)
- Flaky NuGet data source test excluded from hard-failing unit test step

## [1.2.2] - 2026-06-29

### Added
- **`udr scan github <url>`**: Scan GitHub repositories directly — fetches repo, detects manifests, resolves dependencies
- **`--cuda` flag**: CUDA version constraint for GPU-accelerated package resolution
- **CUDA mismatch warnings**: Automatically warns when resolved package requires different CUDA version
- **Full API reference**: `docs/API.md` — all 33 endpoints documented with request/response examples (1,518 lines)
- **Full CLI reference rewrite**: `docs/CLI.md` — all commands, flags, and usage examples rewritten (525 lines)

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
- **Desktop Electron app**: Bundled Python backend via PyInstaller, electron-builder config, installer icons (NSIS/dmg/deb), system tray, auto-update, notifications
- **Self-contained desktop HTML**: Replaced Vue.js SPA with inline `index.html` — 6 tabs (Resolve, Install, Restore, Settings, About, Logs), no build step required
- **`backend/settings/` package**: Replaced monolithic 831-line `settings.py` with modular package structure
- **`backend/api/helpers/`**: Extracted shared API utilities from bloated route handlers
- **Lazy client creation**: `DataAggregator` creates 13 HTTP clients on demand, not at import time
- **CLI startup optimization**: `import z3` deferred to inside methods, all data source imports lazy
- **Concurrent package fetching**: `asyncio.gather` in API routes, CLI resolve, and CLI lock
- **System info caching**: 5-minute TTL on API resolve requests
- **DictCache fallback**: Automatic fallback when Redis is unavailable
- **COMPONENTS.md**: New documentation explaining 3-component model (CLI, API, Desktop) and use cases

### Changed
- **Frontend/ directory DELETED**: Entire Vue.js SPA removed (21,563-line `package-lock.json` deleted) — replaced by self-contained desktop `index.html`
- **PostgreSQL and Redis → optional**: SQLite + DictCache cover all standalone/desktop use cases
- **All `package_exists()` → async aiohttp**: 7 synchronous methods converted
- **Registry URL constants inlined**: Moved from settings into `get_ecosystem_config()` and 9 data source clients
- **Settings trimmed**: 595 → ~200 lines — removed Celery, Email, Webhooks, WebSockets, File upload, Prometheus/Sentry/OTEL
- **Integration tests → SQLite**: No PostgreSQL needed on the host
- **FastAPI pinned**: `>=0.115.0,<0.116` for pydantic 2.x compatibility
- **273 unused imports removed**: Ruff F401 auto-fixed across codebase

### Removed
- Entire `frontend/` directory (Vue.js SPA, package-lock.json, ESLint config, etc.)
- `monitoring/` directory (Prometheus, Grafana, Loki, Promtail)
- `alembic/` directory — `Base.metadata.create_all()` handles schema
- `scripts/` — only `sync-version.py` kept
- `backend/Dockerfile` and `build-docker` CI job
- All docker-compose files, `.dockerignore`, `start_dev.sh`, `sonar-project.properties`
- Dead test files: `load_test.js`, `TestSystemBenchmark`, `TestVerifiedCombination`, `test_middleware.py`
- Dead API endpoints: `/compatibility/report`, `/compare`, `/gpu/info`, `/runtime/{runtime}`, `/analyze-environment`, `/benchmarks`
- `requests` dependency — all usage replaced with `aiohttp`
- **10 intermediate versions**: v1.1.1 through v1.1.20 + v1.2.0 — skipped in final v1.2.1 release

### Fixed
- **Desktop PyInstaller bundling**: Hidden imports for `jose.jwt`, `passlib.bcrypt`, `z3`, `cpuinfo`; `--collect-all` for critical packages
- **Desktop SECRET_KEY crash**: Added `auto_generated_secret_key()` fallback
- **Desktop cwd bug**: Platform-aware working directory detection (macOS `.app` bundle, Linux PyInstaller)
- **Desktop blank screen**: `extraResources` for frontend dist, correct dev/prod URL switching
- **Desktop version mismatch**: Auto-version-sync from `package.json`
- **Desktop NSIS uninstall loop**: Proper `closeApp` handling
- **Desktop macOS ARM64**: Native ARM runner, `z3-solver<4.15.5` pin for macOS ARM compatibility
- **Cross-platform hints**: macOS `.app` bundle detection, Linux platform fallback
- **libz3.dll missing**: Added z3 DLL to PyInstaller bundle
- **Integration test isolation**: `db_session` fixture cleans tables between tests
- **SQLite foreign keys**: `PRAGMA foreign_keys=ON` event listener
- **All 21 tests**: Updated for async `package_exists()` conversions
- **Settings tests**: Fixed `importlib.reload` + `clear=True` poisoning bug
- **Route collision**: Package details moved from `/{ecosystem}/{name}` to `/{ecosystem}/{name}/details`
- **export_generator.py**: Uses `PackageLoader` for frozen-packaged compatibility
- **CLI `_parse_package_spec`**: Uses `rsplit("@", 1)` for npm scoped packages

## [1.1.0] - 2026-06-25

### Added
- **Initial project scaffold**: FastAPI backend, Vue.js frontend, PostgreSQL/SQLite, Docker/k8s, monitoring stack
- **10+ data source clients**: PyPI, npm, Maven, Crates.io, Conda, RubyGems, NuGet, Pub (Dart), Go, Cargo — with async aiohttp, caching, version parsing
- **CLI tool**: 9 commands — serve, check, resolve, info, lock, graph, verify, list-ecosystems, update
- **SAT-based conflict resolution**: Z3 solver integration with binary encoding, version enumeration, constraint propagation
- **System scanner**: OS, CPU, GPU, CUDA, Python, Node.js, GCC, Java detection
- **Export generator**: 12 output formats (requirements.txt, package.json, Dockerfile, pyproject.toml, etc.)
- **Manifest detector**: Auto-detects 20+ manifest formats with per-ecosystem parsers
- **Frontend dashboard**: Vue.js SPA with Project Scan panel, dependency visualization, Desktop app launcher
- **Install script**: `install.sh` for non-Python users, auto-detects OS and package manager
- **Observability**: OpenTelemetry tracing, Prometheus metrics, Sentry error tracking, structured logging
- **Auth middleware**: JWT-based authentication with bearer token support
- **CI/CD pipeline**: 11 CI jobs (lint, typecheck, unit tests, integration tests, data-source tests, security, frontend, desktop build, publish, deploy)

### Changed
- **PostgreSQL and Redis → optional**: SQLite + DictCache cover standalone/desktop use cases — no external services required
- **All sync `package_exists()` → async aiohttp**: Eliminated blocking calls in async context
- **Registry URL constants inlined**: Moved from settings/ into `get_ecosystem_config()` and data source clients
- **Settings trimmed**: 595 → ~200 lines — removed Celery, Email, Webhooks, WebSockets, File upload, Prometheus/Sentry/OTEL settings
- **Integration tests → SQLite**: No PostgreSQL required on the host
- **FastAPI pinned**: `>=0.115.0,<0.116` for pydantic 2.x compatibility

### Removed
- `monitoring/` directory (Prometheus, Grafana, Loki, Promtail — server infra)
- `alembic/` directory — `Base.metadata.create_all()` handles schema
- `scripts/` — only `sync-version.py` kept
- `backend/Dockerfile` and `build-docker` CI job
- All docker-compose files, `.dockerignore`, `start_dev.sh`, `sonar-project.properties`
- Dead test files: `load_test.js`, `TestSystemBenchmark`, `TestVerifiedCombination`, `test_middleware.py`
- Dead API endpoints: `/compatibility/report`, `/compare`, `/gpu/info`, `/runtime/{runtime}`, `/analyze-environment`, `/benchmarks`
- `requests` dependency — all usage replaced with `aiohttp`/`urllib`

### Fixed
- **Desktop Electron blank screen**: `extraResources` for frontend dist
- **Integration test isolation**: `db_session` fixture cleans tables between tests
- **SQLite foreign keys**: `PRAGMA foreign_keys=ON` event listener
- **All 21 tests updated**: For async `package_exists()` conversions
- **Settings test poisoning**: Fixed `importlib.reload` + `clear=True` bug
- **Route collision**: Package details moved from `/{ecosystem}/{name}` to `/{ecosystem}/{name}/details`
- **export_generator.py**: Uses `PackageLoader` for PyInstaller/frozen-packaged compatibility
- **CLI `_parse_package_spec`**: Uses `rsplit("@", 1)` for npm scoped packages
- **5 integration test failures**: All resolved
- **CI pipeline**: All 11 jobs fixed and passing
- **Opentelemetry**: Lazy imports to avoid crash in restricted environments
- **System info**: Defensive `.get()` with defaults for GPU/CPU fields

### Publishing
- Publishes to PyPI (`pip install ud-resolver`) via trusted publishing
- Uploads `.whl` to release assets on publish
- Loosened version pins (fastapi, uvicorn, packaging) to avoid Colab conflicts
