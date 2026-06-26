# Developer Onboarding Guide

## System Overview

Multi-ecosystem dependency resolver supporting PyPI, NPM, Conda, Maven, Crates.io, and 8 more — with Z3 SAT-based conflict resolution.

### Key Features
- **Multi-Ecosystem**: Python, JavaScript, Java, Rust, Conda, and more
- **Conflict Resolution**: Z3 theorem prover for dependency solving
- **System Compatibility**: OS, CPU, GPU, runtime scanning
- **12 Export Formats**: requirements.txt, package.json, Dockerfile, etc.
- **Desktop App**: Electron wrapper with bundled Python backend, system tray, notifications, and auto-update (see [COMPONENTS.md](COMPONENTS.md))
- **CI/CD Ready**: GitHub Actions, Docker, K6 load testing

### Architecture
The project is split into **three distributable components**:

- **Backend** (PyPI: `ud-resolver`) — Python FastAPI app with CLI, REST API, and Python library
- **Frontend** (Vue.js 3) — browser-based GUI, served via Docker or bundled in desktop app
- **Desktop** (Electron) — standalone app bundling back end + frontend, no setup required

See [COMPONENTS.md](COMPONENTS.md) for the full component guide with prerequisites and usage examples.

## Development Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose v2 (optional)

### Quick Start

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
uvicorn backend.api.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run serve

# Open http://localhost:8080
```

No PostgreSQL or Redis needed. SQLite + DictCache work out of the box.

### Using Docker

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
# Frontend: http://localhost:8080, API: http://localhost:8000
```

### Running Tests

```bash
# Backend (422 tests)
pytest -v

# Frontend (65 tests)
cd frontend && npm run test

# Desktop (19 tests)
cd desktop && npm test

# All 506 tests pass
```

### Code Quality

```bash
pip install -e ".[dev]"
black backend/
ruff check backend/
mypy backend/ --ignore-missing-imports
cd frontend && npm run lint
```

## Basic Usage

### Via Web UI
1. Open http://localhost:8080
2. Add packages (e.g., "tensorflow", "react")
3. Click Resolve
4. Export as requirements.txt, Dockerfile, etc.

### Via CLI

```bash
python -m backend.cli resolve flask>=2.0.0 django>=4.0.0
python -m backend.cli lock flask>=2.0.0
python -m backend.cli scan /path/to/project
```

### Via API

```bash
# Search
curl http://localhost:8000/api/v1/packages/search?q=flask

# Resolve
curl -X POST http://localhost:8000/api/v1/packages/resolve \
  -H "Content-Type: application/json" \
  -d '{"packages": [{"name": "flask", "ecosystem": "pypi", "version": ">=2.0.0"}]}'

# Health
curl http://localhost:8000/api/v1/health
```

## Project Structure

```
backend/         → Python FastAPI app
  api/           → REST API layer
  core/          → Business logic (solver, cache, scanner)
  data_sources/  → 13 ecosystem API clients
  database/      → SQLAlchemy models
  cli.py         → CLI interface
desktop/         → Electron shell
frontend/        → Vue.js web UI
tests/           → 422 backend tests
```

## Contributing

- PRs from `feature/*` branches to `main`
- Tests required for new functionality
- Type hints required for all Python code
- CI must pass (lint + 506 tests)
