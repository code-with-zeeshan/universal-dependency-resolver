# Universal Dependency Resolver

Resolve dependencies across **PyPI (pip)**, **npm**, **Cargo**, **Go**, and more — detect conflicts, check system compatibility, and export to any format.

```
udr resolve numpy@pypi torch@pypi
  → numpy 1.26.2, torch 2.1.2+cu121 (CUDA 12.1)
```

## Components

This project ships as **two components** — pick the one that fits your use case:

| Component | What it is | Install / Download |
|---|---|---|
| **Backend** | Core resolver engine — CLI, Python library, REST API | `pip install ud-resolver` |
| **Desktop** | Standalone app — backend binary + built-in GUI, no setup | `.exe` / `.dmg` / `.AppImage` from [Releases](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases) |

See [docs/COMPONENTS.md](docs/COMPONENTS.md) for detailed prerequisites, use cases, and examples.

---

## The Problem

Your project pulls in packages from everywhere — Python scripts call Node services, Docker images need both `pip` and `apt` packages, and your CI pipeline has to pin every transitive dependency across all of them.

Existing tools only work within one ecosystem. `pip-compile` handles Python. `npm ls` handles JavaScript. But cross-ecosystem conflicts go undetected until something breaks at runtime. And system compatibility — GPU drivers, CUDA versions, OS patches — is never checked at all.

This tool fixes that.

## What It Does

```
Input:  ["requests>=2.25", "torch==2.0", "express@^4.18"]
                                ↓
               Fetch metadata from PyPI / npm / Conda / ...
               Detect target system (OS, GPU, Python, CUDA)
               Resolve conflicts with SAT solver
                                ↓
Output: Locked dependency tree + export (Dockerfile, requirements.txt, ...)
```

## Quick Example

```bash
curl -X POST http://localhost:8000/api/v1/packages/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "packages": [
      {"name": "requests", "ecosystem": "pypi"},
      {"name": "express", "ecosystem": "npm"}
    ],
    "auto_detect_system": true
  }'
```

| Feature | What it does |
|---------|--------------|
| **Multi-ecosystem** | PyPI (pip), npm, Cargo, Go, Conda, Maven, NuGet, RubyGems, Linux packages, Homebrew |
| **GPU-aware resolution** | Scans CUDA, cuDNN, GPU memory — resolves CUDA variants automatically |
| **System scan** | Detects OS, CPU, GPU, Python, Node.js, GCC, Java |
| **12 export formats** | Dockerfile, requirements.txt, package.json, docker-compose.yml, install.sh, install.bat, CMakeLists.txt, pyproject.toml, environment.yml, Cargo.toml, build.gradle, pom.xml |
| **CI/CD ready** | CLI for pipelines, health check endpoint, structured logging |

## Quick Start

### CLI (from `pip install ud-resolver`)

```bash
# Resolve packages
udr resolve numpy pandas scikit-learn
udr resolve react vue -e npm

# Lock dependencies
udr lock
udr lock --manifest requirements.txt --manifest package.json --dry-run

# Check system
udr check
udr info

# Start API server
udr serve --port 8000
```

### Python library (same `pip install ud-resolver`)

```python
import asyncio
from backend.core.data_aggregator import DataAggregator
from backend.core.conflict_resolver import ConflictResolver
from backend.core.system_scanner import SystemScanner
from backend.manifest_detector import ManifestDetector

async def main():
    scanner = SystemScanner()
    system_info = await scanner.scan_all()
    print(system_info["platform"]["system"], system_info["cpu"]["brand"])

    aggregator = DataAggregator()
    data = await aggregator.get_package_info("torch", ecosystem="pypi",
                                              include_dependencies=True,
                                              include_versions=True)
    print(data["name"], data["versions"])

    detector = ManifestDetector("./my-project")
    manifests = detector.detect()
    packages = detector.normalize(detector.parse_all(manifests))
    print(f"{len(packages)} packages found")

asyncio.run(main())
```

### Docker

```bash
docker pull ghcr.io/code-with-zeeshan/universal-dependency-resolver-backend:latest
```

Or build and run locally:

```bash
cp .env.example .env
docker compose up -d
docker compose exec backend alembic upgrade head
# API: http://localhost:8000
```

### Desktop

Download the installer from [GitHub Releases](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases) — no Python or Node.js required. Features built-in GUI, system tray, notifications, and auto-update. See [docs/COMPONENTS.md](docs/COMPONENTS.md#2-desktop-electron-standalone-app) for details.

## API Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/` | GET | API metadata |
| `/api/v1/health` | GET | Health check |
| `/api/v1/packages/search` | GET | Search across ecosystems |
| `/api/v1/packages/ecosystems` | GET | List supported ecosystems |
| `/api/v1/packages/{ecosystem}/{name}` | GET | Get package info |
| `/api/v1/packages/{ecosystem}/{name}/details` | GET | Rich package details with metrics |
| `/api/v1/packages/{ecosystem}/{name}/versions` | GET | List versions |
| `/api/v1/packages/{ecosystem}/{name}/dependencies` | GET | Get dependencies |
| `/api/v1/packages/{ecosystem}/{name}/compatibility` | GET | Compatibility info |
| `/api/v1/packages/{ecosystem}/{name}/compatibility/report` | POST | Submit compatibility report |
| `/api/v1/packages/compare` | GET | Compare packages |
| `/api/v1/packages/resolve` | POST | Resolve dependencies |
| `/api/v1/packages/export` | POST | Export to any format |
| `/api/v1/packages/export-formats` | GET | Available export formats |
| `/api/v1/system/info` | GET | System information |
| `/api/v1/system/check-compatibility` | POST | Check dependency-system fit |
| `/api/v1/system/gpu/info` | GET | GPU details |
| `/api/v1/system/runtime/{runtime}` | GET | Runtime version info |
| `/api/v1/system/analyze-environment` | POST | Analyze manifest file |
| `/api/v1/system/benchmarks` | GET | Run system benchmarks |
| `/api/v1/scan/github` | POST | Scan a GitHub repo |
| `/api/v1/scan/upload` | POST | Scan an uploaded archive |
| `/api/v1/scan/local` | POST | Scan a local directory |
| `/api/v1/auth/*` | * | Register, login, profile, API keys |

Full reference in [docs/API.md](docs/API.md).

## Testing

```bash
# Backend
python -m pytest tests/unit/

# Desktop
cd desktop && npm test
```

## How It Works

```
Your request → Fetch metadata from ecosystem registries
                   ↓
            Scan target system (OS, GPU, Python, CUDA)
                   ↓
            Resolve conflicts with SAT solver
                   ↓
            Export to 12 formats
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture.

---

- [docs/COMPONENTS.md](docs/COMPONENTS.md) — component guide (backend / desktop)
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — production deployment
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute
- [LICENSE](LICENSE) — MIT
