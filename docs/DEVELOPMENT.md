# Development Guide

## Prerequisites

- Python 3.11–3.13
- Git
- No external services required (SQLite, in-memory cache by default)

---

## Setup

```bash
git clone https://github.com/code-with-zeeshan/universal-dependency-resolver
cd universal-dependency-resolver

python3 -m venv venv
source venv/bin/activate

pip install -e ".[dev,z3,system,postgres]"
```

---

## Pre-commit Hooks

```bash
pre-commit install
```

The pre-commit hook runs:

1. `ruff check backend/` — lint (no violations allowed)
2. `ruff format --check backend/` — format check
3. `mypy backend/` — type checking (strict mode)
4. Architecture import rules — no violations allowed
5. Check for large files, private keys, merge conflicts, debug statements

---

## Development Server

```bash
udr serve --reload
# → http://127.0.0.1:8000
```

Auto-reloads on Python file changes (dev only).

---

## Tests

```bash
# Run all tests
python -m pytest

# By category
python -m pytest tests/unit          # 3739 tests
python -m pytest tests/integration   # 96 tests
python -m pytest tests/e2e           # 383 tests

# With coverage
python -m pytest --cov=backend --cov-report=term-missing --cov-fail-under=57

# Specific test file
python -m pytest tests/unit/test_cli.py -v

# Fast fail
python -m pytest -x

# Parallel (needs pytest-xdist)
python -m pytest -n auto
```

**Current totals:** 4301 tests (3739 unit + 96 integration + 383 e2e + others)

---

## Code Quality

```bash
# Lint (ruff)
ruff check backend/

# Auto-fix
ruff check backend/ --fix

# Format check
ruff format --check backend/

# Format
ruff format backend/

# Type check (mypy)
mypy backend/
```

---

## Project Structure

```
universal-dependency-resolver/
├── backend/
│   ├── __init__.py
│   ├── py.typed              # PEP 561 marker
│   ├── api/                  # FastAPI application
│   │   ├── main.py           # App factory, middleware, exception handlers
│   │   ├── dependencies.py   # FastAPI dependency injection
│   │   ├── middleware.py     # Auth, CSRF, rate limiting, logging
│   │   └── routes/           # 9 route modules (59 endpoints)
│   │       ├── auth.py       # Registration, login, API keys, signing keys
│   │       ├── check.py      # CVE, license, deprecated, policy
│   │       ├── completion.py # Shell completion scripts
│   │       ├── index.py      # Offline SQLite index management
│   │       ├── lock.py       # Lock generation, verification, signing, etc.
│   │       ├── packages.py   # Search, details, versions, resolve, export
│   │       ├── sbom.py       # SPDX / CycloneDX generation
│   │       ├── scan.py       # GitHub, local, upload scanning
│   │       └── system.py     # System info, compatibility check
│   ├── cli/                  # Command-line interface
│   │   ├── main.py           # Argparse entry point (24 subparsers)
│   │   ├── shared.py         # Shared helpers (lock path, manifest updaters)
│   │   ├── completion.py     # Shell completion (bash/zsh/fish)
│   │   └── commands/         # 24 command modules
│   │       ├── auth.py install.py lock.py scan.py serve.py ...
│   ├── core/                 # Core business logic
│   │   ├── conflict_resolver.py  # Z3 SAT solver
│   │   ├── pubgrub_solver.py     # PubGrub solver (Rust/pure Python)
│   │   ├── data_aggregator.py    # Registry data fetching + caching
│   │   ├── system_scanner.py     # OS/CPU/GPU/CUDA/Runtime detection
│   │   ├── license_checker.py    # SPDX license compliance
│   │   ├── export_generator.py   # requirements.txt / Dockerfile export
│   │   ├── markers.py            # PEP 508 platform marker evaluation
│   │   ├── vers.py               # Cross-ecosystem version parsing
│   │   ├── content_cache.py      # SHA256-verified blob cache
│   │   ├── cache.py              # DictCache (in-memory JSON)
│   │   ├── utils.py              # Shared utilities
│   │   └── fetchers.py           # Async HTTP fetching
│   ├── data_sources/         # 25 ecosystem plugins
│   │   ├── base_client.py    # Base HTTP client with caching, retry, auth
│   │   ├── pypi_client.py npm_client.py crates_client.py ...
│   │   └── hex_plugin.py haskell_plugin.py nix_plugin.py ...
│   ├── database/             # Persistence layer
│   │   ├── models.py         # 9 SQLAlchemy ORM models
│   │   ├── connection.py     # Engine + session management
│   │   └── queries.py        # Query helpers
│   ├── orchestrator/         # Resolution orchestration
│   │   ├── resolve.py        # BFS dep discovery, solver factory
│   │   └── __init__.py
│   └── settings/             # Configuration
│       └── __init__.py       # Env var loading (PEP 562 lazy eval)
├── frontend/                 # Web SPA (vanilla JS, no build step)
│   ├── index.html            # 255 lines — SPA shell
│   ├── css/style.css         # 632 lines — Dark theme
│   ├── js/
│   │   ├── app.js            # 836 lines — Router + state + pages
│   │   ├── api.js            # 175 lines — BackendAPI fetch wrapper
│   │   └── utils.js          # 480 lines — Formatting, OSV, policy, SBOM
│   ├── tests/
│   │   ├── api.test.js       # 315 lines — 21+ BackendAPI tests
│   │   └── utils.test.js     # 722 lines — Utility/SBOM/policy tests
│   └── package.json          # Jest dev dependency only
├── desktop/                  # Electron app
│   ├── main.js               # Electron main process
│   ├── app.js                # Renderer logic (17 tabs)
│   ├── index.html            # GUI shell
│   └── package.json
├── vscode-extension/         # VS Code extension (TypeScript, 13 commands)
│   ├── package.json          # 169 lines — extension manifest
│   ├── src/
│   │   ├── extension.ts      # 61 lines — activate/deactivate
│   │   ├── cliRunner.ts      # 58 lines — spawnSync udr CLI
│   │   ├── cveDiagnostics.ts # 75 lines — CVE problem markers
│   │   ├── lockFileProvider.ts # 86 lines — UDR Lock tree view
│   │   └── manifestEditor.ts # 124 lines — dep editing (req.txt, pyproject, pkg.json)
│   └── test/
│       └── extension.test.ts # 23 lines — 3 smoke tests
├── tests/
│   ├── unit/                 # 3739 unit tests
│   ├── integration/          # 96 integration tests
│   └── e2e/                  # 383 end-to-end tests
├── docs/                     # Documentation
├── alembic/                  # Database migrations
├── pyproject.toml
└── AGENTS.md
```

---

## VS Code Extension Development

The VS Code extension shells out to the `udr` CLI — no Python API calls.

```bash
cd vscode-extension
npm install                  # installs TypeScript + @vscode/test-electron
npm run compile              # tsc -p ./
npm test                     # @vscode/test-electron (3 smoke tests)
```

**Test files:** `test/extension.test.ts` (23 lines, 3 tests — extension presence, command count, tree view).

### Extension structure

```
vscode-extension/
  package.json              (169 lines)  — 13 commands, 4 settings, 7 activation events
  src/
    extension.ts            ( 61 lines)  — activate/deactivate, registers all commands
    cliRunner.ts            ( 58 lines)  — spawnSync wrapper for `udr` CLI
    cveDiagnostics.ts       ( 75 lines)  — CVE problem markers in lock file
    lockFileProvider.ts     ( 86 lines)  — "UDR Lock" tree view (sidebar)
    manifestEditor.ts       (124 lines)  — Add/update/remove deps in manifest files
```

**Total:** 13 files, 719 lines (including config/docs).

### Key design notes

- **CLI-only communication**: No REST API calls — everything runs `udr` via `child_process.spawnSync()`
- **Lock file tree view**: Parses `udr.lock` directly for grouped-by-ecosystem display
- **CVE diagnostics**: Inline squiggly underlines on vulnerable package names in the lock file
- **Manifest editing**: Supports `requirements.txt`, `pyproject.toml`, and `package.json` (18+ manifest types show informational message to edit manually)
- **13 commands** from Command Palette: check, update, SBOM, verify, policies, fix CVEs, lock, lock check, graph, refresh, add/update/remove dependency
- **4 settings**: `udr.cliPath`, `udr.lockFileName`, `udr.autoCheckOnSave`, `udr.cveSeverityThreshold`
- **7 activation events**: workspace contains `udr.lock`, `requirements.txt`, `package.json`, etc.

---

## Frontend Development

The web frontend is a vanilla JS SPA (no framework, no build step).

```bash
# Serve frontend separately (backend must be running)
cd frontend
python -m http.server 3000

# Run frontend tests
cd frontend
npm install            # installs Jest (dev only)
npm test               # 21+ tests (api.test.js + utils.test.js)

# Alternatively with backend auto-served:
udr serve              # serves both API + frontend at http://localhost:8000
```

**Test files:** `frontend/tests/api.test.js` (315 lines, BackendAPI tests) + `frontend/tests/utils.test.js` (722 lines, utility/SBOM/policy/OSV tests).

---

## Desktop Development

```bash
cd desktop
npm install
npm run build       # Compile backend via PyInstaller
npm run start       # Launch Electron with built backend
npm run dev         # Dev mode (separate backend + Electron)
```

---

## Adding a New Ecosystem

1. **Create a data source plugin** in `backend/data_sources/` (inherit `BaseDataSourceClient`)
2. **Register the plugin** in `backend/core/data_aggregator.py` (`_register_builtin()`)
3. **Add manifest patterns** in `backend/manifest_detector.py` (`MANIFEST_PATTERNS`)
4. **Add a manifest parser** in `backend/manifest_detector.py` (if needed)
5. **Add settings** in `backend/settings/__init__.py` (rate limits, URL templates)
6. **Add ecosystem entry** in `backend/core/utils.py` (`sanitize_ecosystem_name`, aliases)
7. **Write tests** in `tests/unit/` (contract tests in `test_plugin_contract.py`)
8. **Update the manifest updater** in `backend/cli/shared.py` (`_get_manifest_updater`)

## Adding a New Export Format

1. **Add a Jinja2 template** in `backend/core/templates/export/`
2. **Register the format** in `backend/core/export_generator.py` (`__init__` or `register_format`)
3. **Write tests** for the new format

## Commit Messages

```
<type>: <short description>

<optional body>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`, `ci`
