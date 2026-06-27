# Components

Universal Dependency Resolver ships as two components. Each targets a different audience and use case. This document explains what each component is, when to use it, and how.

## Quick Decision Guide

| You want to... | Use |
|---|---|
| Resolve dependencies in a CI/CD pipeline or script | **CLI** (installed via `pip install ud-resolver`) |
| Call the resolver from Python code | **Python library** (same pip package) |
| Deploy the resolver as a service (Docker, cloud) | **Backend API** (same pip package + `uvicorn`) |
| Use the resolver through a web interface | **Desktop app** (builds-in a GUI) or `udr serve` (API + Swagger) |
| Use the resolver offline without any setup | **Desktop app** (Electron, bundled) |
| Kick the tires / learn the tool quickly | **Desktop app** (no CLI knowledge needed) |

---

## 1. Backend (`pip install ud-resolver`)

### What it is
The core resolver engine — a Python FastAPI application with:
- REST API for resolving, scanning, exporting
- CLI entry point for scripting and CI/CD
- Python library for programmatic use
- SAT-based conflict resolver (Z3), system scanner, 13 ecosystem data sources

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
udr serve --host 0.0.0.0 --port 8000
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
| `[postgres]` | PostgreSQL + Redis + Celery |
| `[all]` | Everything |

> **Note:** Auth (JWT, passlib, bcrypt) is now a core dependency — no `[security]` extra needed. Auth is disabled by default (`UDR_MODE=local`); enable with `UDR_MODE=saas`.

### API docs
Once running: `http://localhost:8000/api/v1/docs` (Swagger UI)

---

## 2. Desktop (Electron standalone app)

### What it is
A cross-platform desktop application (Windows .exe, macOS .dmg, Linux .AppImage) that bundles:
- The **backend** (compiled to a standalone binary via PyInstaller — no Python install needed)
- A **built-in GUI** (`desktop/index.html` — inline CSS/JS, no build step)
- An **Electron shell** that spawns the backend on launch and opens the GUI

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
┌─────────────────────────────────────────────┐
│               Desktop App                   │
│  ┌──────────────┐  ┌─────────────────────┐  │
│  │  Electron    │  │  Backend (PyIn-     │  │
│  │  shell       │  │  staller binary)    │  │
│  │  (main.js)   │  │                     │  │
│  │  + GUI       │  │  REST API on        │  │
│  │  (index.html)│  │  localhost:port     │  │
│  └──────┬───────┘  └──────────┬──────────┘  │
│         │                     │              │
│         └─────────────────────┘              │
│                    │                         │
│    1. Electron loads index.html (built-in)   │
│    2. Spawns backend binary on a free port   │
│    3. GUI polls backend at that port         │
│    4. Ready: resolve packages via GUI        │
└─────────────────────────────────────────────┘
```

### Fallback chain
If the bundled binary fails (antivirus, missing system libraries), the desktop app falls back to system Python:

1. **PyInstaller binary** (bundled, preferred — no Python needed)
2. **System Python** (`udr serve`) — requires `pip install ud-resolver` and Python 3.11+

### Desktop-specific features
- **Auto-update**: In production builds, the app checks for updates on launch and notifies you when a new version is available
- **System tray**: Minimize to tray with quick-access menu (Show / Quit)
- **Desktop notifications**: Alerts when backend starts and when updates are ready

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
                                       │
                                       ▼
GitHub Releases  ────►  Desktop app (backend binary + built-in GUI)
```

## Where to find each component

| Component | Published to | How to get |
|---|---|---|
| Backend (PyPI) | [pypi.org/project/ud-resolver](https://pypi.org/project/ud-resolver/) | `pip install ud-resolver` |
| Backend (GHCR) | `ghcr.io/...-backend` | `docker pull` |
| Desktop | [GitHub Releases](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases) | Download `.zip` from release assets |
