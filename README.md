# Universal Dependency Resolver

Resolve dependencies across **PyPI (pip)**, **npm**, **Cargo**, **Go**, and more — detect conflicts, check system compatibility, and export to any format.

```
udr resolve numpy@pypi torch@pypi
  → numpy 1.26.2, torch 2.1.2+cu121 (CUDA 12.1)
```

## Package availability

| Source | Install | Published via |
|--------|---------|---------------|
| **PyPI** | `pip install ud-resolver` | GitHub Actions on release |
| **GitHub Releases** | `pip install ud-resolver-*.whl` from [Releases](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases) | CI on release |
| **GHCR (Docker)** | `docker pull ghcr.io/code-with-zeeshan/universal-dependency-resolver-backend:latest` | CI on every push |

> **PyPI note**: The package is published on PyPI as **`ud-resolver`** — install with `pip install ud-resolver`, *not* `universal-dependency-resolver`.

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

Returns a resolved dependency tree with all transitive deps, conflict status, and system compatibility notes.

| Feature | What it does |
|---------|--------------|
| **Multi-ecosystem** | PyPI (pip), npm, Cargo, Go, Conda, Maven, NuGet, RubyGems, Linux packages, Homebrew |
| **GPU-aware resolution** | Scans CUDA, cuDNN, GPU memory — resolves CUDA variants automatically |
| **System scan** | Detects OS, CPU, GPU, Python, Node.js, GCC, Java |
| **12 export formats** | Dockerfile, requirements.txt, package.json, docker-compose.yml, install.sh, CMakeLists.txt, pyproject.toml, environment.yml, Cargo.toml, build.gradle, pom.xml, Gemfile |
| **CI/CD ready** | CLI for pipelines, health check endpoint, structured logging |
| **Desktop app** | Cross-platform Electron app with integrated Python backend |

## Quick Start

### PyPI (recommended)

```bash
pip install ud-resolver
```

Install with extras for additional features:
```bash
pip install "ud-resolver[system]"       # GPU & system scanning
pip install "ud-resolver[monitoring]"   # OpenTelemetry & Sentry
pip install "ud-resolver[security]"     # Auth & JWT support
pip install "ud-resolver[postgres]"     # PostgreSQL + Redis + Celery
pip install "ud-resolver[all]"          # Everything
```

### From source

```bash
git clone https://github.com/code-with-zeeshan/universal-dependency-resolver.git
cd universal-dependency-resolver
pip install -e .
```

### Use as CLI

```bash
# Start the API server
udr serve --port 8000

# Check system compatibility
udr check

# Resolve dependencies
udr resolve numpy pandas scikit-learn

# Resolve from other ecosystems
udr resolve react vue -e npm
udr resolve serde tokio -e crates

# Show system info
udr info

# Auto-detect manifests in project dir and lock all deps
udr lock

# Lock with explicit manifest
udr lock --manifest requirements.txt --manifest package.json

# Dry-run lock (no files written)
udr lock --dry-run

# Resolve with JSON output
udr resolve torch torchvision --format json
```

### Desktop app

```bash
cd desktop
npm install
npm start
```

The Electron app spawns the Python backend automatically and opens the Vue.js UI. Binary downloads are available from GitHub Releases.

### Web UI

```bash
cd frontend && npm install && npm run serve
# → http://localhost:8080
```

The frontend connects to the backend at `http://localhost:8000` (configurable via `VUE_APP_API_URL`).

### Use as Python Library

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

### Docker (production)

Pre-built images are available on **GitHub Container Registry (GHCR)**:

```bash
docker pull ghcr.io/code-with-zeeshan/universal-dependency-resolver-backend:latest
docker pull ghcr.io/code-with-zeeshan/universal-dependency-resolver-frontend:latest
```

Or build and run locally:

```bash
cp .env.example .env
docker compose up -d
docker compose exec backend alembic upgrade head

# Frontend:  http://localhost:8080
# API Docs:  http://localhost:8000/api/v1/docs
```

> **Note**: The Docker images are published automatically via CI on every push to `main` and on tags (`v*`).

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

The system runs as a FastAPI service with optional PostgreSQL, Redis, and a Vue.js frontend.

## API Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/packages/search` | GET | Search across ecosystems |
| `/api/v1/packages/{ecosystem}/{name}` | GET | Get package info |
| `/api/v1/packages/versions` | GET | List versions |
| `/api/v1/packages/resolve` | POST | Resolve dependencies |
| `/api/v1/packages/export` | POST | Export to any format |
| `/api/v1/packages/export-formats` | GET | Available export formats |
| `/api/v1/system/info` | GET | System information |
| `/api/v1/system/check-compatibility` | POST | Check dependency-system fit |
| `/api/v1/scan/github` | POST | Scan a GitHub repo |
| `/api/v1/scan/upload` | POST | Scan an uploaded archive |
| `/api/v1/scan/local` | POST | Scan a local directory |
| `/api/v1/health` | GET | Health check |

Full reference in [docs/API.md](docs/API.md).

## Testing

```bash
# Unit tests
python -m pytest tests/unit/

# Frontend tests
cd frontend && npm run test:unit

# E2E tests (requires Chromium)
cd frontend && npm run test:e2e
```

## Roadmap

| Priority | Feature | Status |
|----------|---------|--------|
| 🔴 High | Python SDK with async support | ✅ Done |
| 🔴 High | CLI tool for CI/CD | ✅ Done |
| 🟡 Medium | JavaScript/TypeScript SDK | Planned |
| 🟡 Medium | CI/CD integration examples (GitHub Actions, GitLab CI) | ✅ Done |
| 🟡 Medium | SBOM export (CycloneDX, SPDX) | Planned |
| 🟡 Medium | Visual dependency graphs | Planned |
| 🟢 Low | Plugin system for custom ecosystems | Researching |

---

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for production deployment,
[CONTRIBUTING.md](CONTRIBUTING.md) to contribute,
and [LICENSE](LICENSE) for licensing (MIT).
