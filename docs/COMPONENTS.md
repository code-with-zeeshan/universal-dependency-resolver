# Components

Universal Dependency Resolver ships as three components. Each targets a different audience and use case. This document explains what each component is, when to use it, and how.

## Quick Decision Guide

| You want to... | Use |
|---|---|
| Resolve dependencies in a CI/CD pipeline or script | **CLI** (installed via `pip install ud-resolver`) |
| Call the resolver from Python code | **Python library** (same pip package) |
| Deploy the resolver as a service (Docker, cloud) | **Backend API** (same pip package + `uvicorn`) |
| Browse and resolve deps through a web interface | **Frontend** (Vue.js SPA) |
| Use the resolver offline without any setup | **Desktop app** (Electron, bundled) |
| Kick the tires / learn the tool quickly | **Desktop app** (no CLI knowledge needed) |

---

## 1. Backend (`pip install ud-resolver`)

### What it is
The core resolver engine — a Python FastAPI application with:
- REST API for resolving, scanning, exporting
- CLI entry point for scripting and CI/CD
- Python library for programmatic use
- SAT-based conflict resolver (Z3), system scanner, 14 ecosystem data sources

### Where to get it
```bash
pip install ud-resolver
```

Or from source:
```bash
git clone https://github.com/code-with-zeeshan/universal-dependency-resolver.git
cd universal-dependency-resolver
pip install -e .
```

### Prerequisites
- Python 3.11 – 3.13

### Use cases

#### CLI — CI/CD pipelines, ad-hoc resolution
```bash
# Resolve cross-ecosystem dependencies
udr resolve flask>=2.0 react@^18

# Lock a project's dependencies
udr lock

# Check system compatibility
udr check

# Start the API server
udr serve --port 8000
```

#### Python library — embed in your own tools
```python
from backend.core.conflict_resolver import ConflictResolver
from backend.core.data_aggregator import DataAggregator

async def check_deps():
    agg = DataAggregator()
    info = await agg.get_package_info("torch", ecosystem="pypi")
    print(info["versions"])

    resolver = ConflictResolver()
    result = resolver.resolve([{"name": "torch", "version": ">=2.0"}])
    return result
```

#### API server — production deployment
```bash
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```

Or with Docker:
```bash
docker pull ghcr.io/code-with-zeeshan/universal-dependency-resolver-backend:latest
docker run -p 8000:8000 ghcr.io/code-with-zeeshan/universal-dependency-resolver-backend:latest
```

### Extras
| Install flag | Adds |
|---|---|
| `[system]` | GPU & system scanning |
| `[monitoring]` | OpenTelemetry & Sentry |
| `[security]` | Auth & JWT |
| `[postgres]` | PostgreSQL + Redis + Celery |
| `[all]` | Everything |

### API docs
Once running: `http://localhost:8000/api/v1/docs` (Swagger UI)

---

## 2. Frontend (Vue.js SPA)

### What it is
A browser-based graphical interface built with Vue.js 3 and Tailwind CSS. Connects to the backend API and provides a visual way to:
- Search packages across ecosystems
- Resolve dependency trees
- Export to 12 formats
- Scan projects and GitHub repos
- View system info (OS, GPU, CUDA)

### Where to get it

**From source** (development):
```bash
cd frontend
npm install
npm run serve
# → http://localhost:8080
```

**Docker** (production):
```bash
docker pull ghcr.io/code-with-zeeshan/universal-dependency-resolver-frontend:latest
```

**Bundled** — the Desktop app (below) includes the frontend automatically.

### Prerequisites
- Node.js 18+ (only if running from source)
- A running backend instance (default: expects `http://localhost:8000`)

### How it connects to the backend
```
┌─────────────────┐      REST API       ┌──────────────────┐
│   Frontend      │ ◄──────────────────► │   Backend API    │
│   Vue.js SPA    │   /api/v1/*         │   FastAPI server │
│   Port 8080     │                      │   Port 8000      │
└─────────────────┘                      └──────────────────┘
```

The frontend is a static SPA. It does not run any resolver logic — all computation happens in the backend.

---

## 3. Desktop (Electron standalone app)

### What it is
A cross-platform desktop application (Windows .exe, macOS .dmg, Linux .AppImage) that bundles:
- The **backend** (compiled to a standalone binary via PyInstaller — no Python install needed)
- The **frontend** (built as static files)
- An **Electron shell** that spawns the backend on launch and opens the frontend

The result: a single offline application with no server setup, no Python install, no terminal commands.

### Where to get it
Download from [GitHub Releases](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases):

| Platform | File |
|---|---|
| Windows 10+ | `udr-desktop-windows-latest.zip` → run the installer `.exe` |
| macOS 11+ | `udr-desktop-macos-latest.zip` → mount `.dmg`, drag to Applications |
| Linux (x86_64) | `udr-desktop-ubuntu-latest.zip` → run the `.AppImage` |

### Prerequisites
- **None.** The app is self-contained. No Python, Node.js, or other runtime required.

### How it works
```
┌─────────────────────────────────────────────────────┐
│                  Desktop App                        │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │  Electron    │  │  Frontend    │  │  Backend  │ │
│  │  shell       │  │  (bundled    │  │  (PyIn-   │ │
│  │  (main.js)   │  │   dist/)     │  │  staller) │ │
│  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘ │
│         │                  │                │       │
│         └──────────────────┴────────────────┘       │
│                    │                                 │
│    1. Electron loads frontend (dist/index.html)      │
│    2. Spawns backend binary on a free port           │
│    3. Frontend polls backend at that port            │
│    4. Ready: all interaction goes through REST API   │
└─────────────────────────────────────────────────────┘
```

### Fallback chain
If the bundled binary fails (antivirus, missing system libraries), the desktop app falls back to system Python:

1. **PyInstaller binary** (bundled, preferred — no Python needed)
2. **System Python** (`python3 -m uvicorn backend.api.main:app`) — requires Python 3.11+

### Known platform notes
- **Windows**: Antivirus may flag the PyInstaller binary. Add an exclusion for the app directory if needed.
- **macOS**: The app is not signed. If Gatekeeper blocks it: right-click → Open, or go to System Settings → Privacy & Security → "Open Anyway".
- **Linux**: AppImages require FUSE. If unavailable: `./UDR-*.AppImage --appimage-extract && ./squashfs-root/AppRun`.

---

## Relationship diagram

```
PyPI / GitHub Releases  ────►  ud-resolver (backend package)
                                      │
                                      ├──►  CLI (udr resolve, udr lock, ...)
                                      ├──►  Python library (import backend.*)
                                      └──►  API server (uvicorn)
                                               │
                                               ▼
GitHub Packages (GHCR)  ────►  Backend Docker image
                               Frontend Docker image
                                      │
                                      ▼
GitHub Releases  ────►  Desktop app (backend + frontend bundled)
```

## Where to find each component

| Component | Published to | How to get |
|---|---|---|
| Backend (PyPI) | [pypi.org/project/ud-resolver](https://pypi.org/project/ud-resolver/) | `pip install ud-resolver` |
| Backend (GHCR) | `ghcr.io/...-backend` | `docker pull` |
| Frontend | `ghcr.io/...-frontend` | `docker pull` or bundled in desktop |
| Desktop | [GitHub Releases](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases) | Download `.zip` from release assets |
