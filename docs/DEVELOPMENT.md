# Development Guide

## Setup

```bash
git clone https://github.com/code-with-zeeshan/universal-dependency-resolver.git
cd universal-dependency-resolver
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

No PostgreSQL, Redis, or Docker required. SQLite + in-memory cache work out of the box.

## Running

```bash
# Start the API server
udr serve --reload

# Or run as a module
python -m backend.cli serve --reload
```

## Tests

```bash
# All tests
python -m pytest tests/

# Unit only
python -m pytest tests/unit/

# CLI end-to-end (black-box subprocess tests)
python -m pytest tests/cli/

# Data source tests only
python -m pytest tests/unit/ -k "data_source"

# Integration tests (uses SQLite by default)
python -m pytest tests/integration/

# With coverage
python -m pytest --cov=backend tests/
```

Total: **760+ tests** (215 unit non-data-source + 543 data-source + CLI e2e + integration). Integration tests default to SQLite and optionally use Redis if available. No PostgreSQL needed.

## Code quality

```bash
ruff check backend/
ruff format backend/
```

## Project structure

```
backend/
├── api/               # FastAPI routes, middleware, auth, schemas
│   └── routes/        # packages.py, system.py, auth.py, scan.py, lock.py
├── cli/               # CLI package (14 modules, 1 per command)
│   ├── main.py        # Parser setup + dispatch
│   ├── shared.py      # Shared helpers (parse, resolve, output)
│   └── commands/      # One file per command (serve, check, lock, resolve, …)
├── core/              # Business logic
│   ├── conflict_resolver.py   # Z3 SAT solver
│   ├── data_aggregator.py     # Aggregates data from all sources
│   ├── export_generator.py    # 12 export formats (Jinja2)
│   ├── system_scanner.py      # OS/CPU/GPU/runtime detection
│   ├── cache.py               # DictCache + optional Redis
│   ├── constraint_normalizer.py # Version constraint normalization
│   └── utils.py
├── manifest_detector.py  # Auto-detect manifest files
├── data_sources/      # 13 ecosystem API clients
├── database/          # SQLAlchemy models
├── settings/          # Configuration (~200 lines)
├── tracing_config.py  # OpenTelemetry setup
└── logging_config.py  # Structured logging
desktop/
├── main.js            # Electron main process
├── preload.js         # IPC bridge
├── backend-launcher.js# Spawns Python backend
├── index.html         # GUI (inline HTML/CSS/JS)
└── package.json
tests/
├── conftest.py        # Shared fixtures
├── unit/              # 399 tests
└── integration/       # 69 tests
```

## Desktop development

```bash
cd desktop
npm install
npm run build          # Build desktop binary (PyInstaller + electron-builder)
npm run start          # Dev mode (uses system Python backend)
```

## Adding an ecosystem

1. Create `backend/data_sources/<name>_client.py` inheriting from `BaseClient`
2. Implement `get_package_info`, `get_version_info`, `search_packages`, `get_dependencies`
3. Add config in `backend/settings/__init__.py` `get_ecosystem_config()`
4. Register in `backend/data_sources/__init__.py`
5. Add tests in `tests/unit/data_sources/`

## Adding an export format

1. Add a Jinja2 template in `backend/core/templates/`
2. Register the format in `backend/core/export_generator.py`
3. Add tests in `tests/unit/test_export_generator.py`

## Commit messages

Use conventional commits:

```
feat(api): add support for Go modules
fix(cli): resolve crash on empty package list
docs(readme): update installation instructions
```
