# Components

Universal Dependency Resolver ships in two forms. Each targets a different use case.

| You want to... | Use |
|---|---|
| Resolve deps in a CI/CD pipeline or script | **CLI** (`pip install ud-resolver`, then `udr resolve ...`) |
| Call the resolver from Python code | **Python library** (same `pip install ud-resolver`) |
| Use a web GUI, no terminal | **Desktop app** (download from Releases) |
| Expose the resolver as a service | **`udr serve`** (same pip package, starts a FastAPI server) |

---

## 1. Backend (CLI / Library / API)

### What it is

The core resolver engine — a Python application with:

- **CLI** — 19 commands for resolving, locking, checking, installing, exporting, searching, indexing, auth, and completion
- **Python library** — import `backend.*` directly
- **REST API** — FastAPI server with Swagger docs

### Install

```bash
pip install ud-resolver
```

Extras:

| Flag | Adds |
|---|---|
| `[system]` | GPU & system scanning (`psutil`, `pynvml`, `cpuinfo`) |
| `[postgres]` | PostgreSQL support |
| `[monitoring]` | OpenTelemetry & Sentry |
| `[all]` | Everything |

### Prerequisites

Python 3.11 – 3.13. No other services required — SQLite + in-memory cache work out of the box.

### Quick start

```bash
udr resolve numpy pandas scikit-learn
udr serve --port 8000
# API docs at http://localhost:8000/api/v1/docs
```

### Use cases

**CLI — CI/CD pipelines, ad-hoc resolution:**

```bash
udr resolve flask>=2.0 react@^18
udr lock
udr check
```

**Python library — embed in your own tools:**

```python
from backend.orchestrator import create_solver
from backend.core.data_aggregator import DataAggregator

async def check_deps():
    agg = DataAggregator()
    info = await agg.get_package_info("torch", ecosystem="pypi")
    resolver = create_solver()
    result = resolver.resolve_dependencies(packages=[{"name": "torch", "version": ">=2.0"}])
```

**API server — programmatic access:**

```bash
curl -X POST http://localhost:8000/api/v1/packages/resolve \
  -H "Content-Type: application/json" \
  -d '{"packages": [{"name": "flask", "ecosystem": "pypi", "version": ">=2.0"}]}'
```

---

## 2. Desktop (Electron app)

### What it is

A cross-platform desktop application (Windows .exe, macOS .dmg, Linux .AppImage) that bundles:

- The backend compiled to a standalone binary via PyInstaller
- A GUI (`desktop/index.html` — inline CSS/JS, no framework)
- An Electron shell that spawns the backend on launch

No Python, Node.js, or any runtime required.

### Download

Download from [GitHub Releases](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases):

| Platform | File |
|---|---|
| Windows 10+ | `udr-desktop-windows-latest.zip` → run installer `.exe` |
| macOS 11+ | `udr-desktop-macos-latest.zip` → mount `.dmg`, drag to Applications |
| Linux (x86_64) | `udr-desktop-ubuntu-latest.zip` → run `.AppImage` |

### How it works

```
1. Electron loads index.html (built-in GUI)
2. Spawns backend binary on a free port
3. GUI communicates with backend via REST API
4. Ready: resolve packages, view results, export
```

If the bundled binary fails (antivirus, missing system libraries), the app falls back to system Python (`udr serve` from `pip install ud-resolver`).

### Desktop features

- 14 tabbed views: Resolve, Lock, Verify, Graph, Scan, Export, System Info, etc.
- Formatted HTML tables — no raw JSON shown to users
- Loading spinners and human-readable error messages
- System tray with quick-access menu
- Auto-update checks on launch
- Desktop notifications

### Platform notes

- **Windows**: Antivirus may flag the PyInstaller binary. Add an exclusion if needed.
- **macOS**: Not signed. If Gatekeeper blocks: right-click → Open, or System Settings → Privacy & Security → "Open Anyway".
- **Linux**: AppImages require FUSE. If unavailable: `./UDR-*.AppImage --appimage-extract && ./squashfs-root/AppRun`.
