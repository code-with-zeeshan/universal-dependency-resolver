# Universal Dependency Resolver

Resolve dependencies across **PyPI (pip)**, **npm**, **Cargo**, **Go**, and more — detect conflicts, check system compatibility, and export to any format.

```
udr resolve numpy@pypi torch@pypi
  → numpy 1.26.2, torch 2.1.2+cu121 (CUDA 12.1)
```

## The Problem

Your project pulls in packages from everywhere — Python scripts call Node services, Docker images need both `pip` and `apt` packages, and your CI pipeline has to pin every transitive dependency across all of them.

Existing tools only work within one ecosystem. `pip-compile` handles Python. `npm ls` handles JavaScript. But cross-ecosystem conflicts go undetected until something breaks at runtime. And system compatibility — GPU drivers, CUDA versions, OS patches — is never checked at all.

This tool fixes that.

## Quick Start

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

## CLI Usage

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

## Python Library Usage

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

## Features

| Feature | What it does |
|---------|--------------|
| **Multi-ecosystem** | PyPI (pip), npm, Cargo, Go, Conda, Maven, NuGet, RubyGems, Linux packages, Homebrew |
| **GPU-aware resolution** | Scans CUDA, cuDNN, GPU memory — resolves CUDA variants automatically |
| **System scan** | Detects OS, CPU, GPU, Python, Node.js, GCC, Java |
| **12 export formats** | Dockerfile, requirements.txt, package.json, docker-compose.yml, install.sh, CMakeLists.txt, pyproject.toml, environment.yml, Cargo.toml, build.gradle, pom.xml, Gemfile |
| **CI/CD ready** | CLI for pipelines, health check endpoint, structured logging |

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

The system runs as a FastAPI service with optional PostgreSQL and Redis.

## Also available

This package is the **backend component**. The project also ships:

- **Web UI** — a browser-based GUI (Vue.js), available as a Docker image or bundled in the desktop app
- **Desktop app** — standalone cross-platform application (Windows, macOS, Linux) with backend + frontend bundled, no Python or Node.js required

See the [full documentation](https://github.com/code-with-zeeshan/universal-dependency-resolver) for details.
