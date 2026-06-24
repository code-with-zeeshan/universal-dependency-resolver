# Universal Dependency Resolver

Resolve dependencies across **PyPI (pip)**, **npm**, **Cargo**, **Go**, and more — detect conflicts, check system compatibility, and export to any format.

```
udr resolve numpy torch torchvision --gpu
  → numpy 1.26.2, torch 2.1.2+cu121 (CUDA 12.1), torchvision 0.16.2+cu121
```

---

## The Problem

You have a project that depends on packages from multiple ecosystems. A Python script calls a Node service. A Docker image needs both `pip` and `apt` packages. A CI pipeline must pin every transitive dependency across all of them.

Existing tools only work within one ecosystem (`pip-compile`, `npm ls`, `bundler`). Cross-ecosystem conflicts go undetected until runtime. System compatibility (GPU, CUDA, OS version) is never checked.

This tool solves that.

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
| **Multi-ecosystem** | PyPI (pip), npm, Cargo, Go, Conda, Maven, NuGet, RubyGems, Dart, Linux packages, Homebrew |
| **GPU-aware resolution** | Scans CUDA, cuDNN, GPU memory — resolves compatible versions automatically |
| **System scan** | Detects OS, CPU, GPU, Python, Node.js, GCC, Java |
| **14+ export formats** | Dockerfile, requirements.txt, package.json, docker-compose.yml, install.sh, CMakeLists.txt, Nix, Guix, Spack, YAML, TOML, JSON, CycloneDX, SPDX |
| **CI/CD ready** | CLI for pipelines, health check endpoint, structured logging |
| **Data science stack** | Resolve PyTorch + CUDA + Conda + pip dependencies with GPU compatibility checks |

## Use Cases

| Scenario | What this does |
|----------|----------------|
| **Container build** | Generate a Dockerfile with exact `pip install` + `apt-get` + `npm ci` pinned versions, verified compatible on the target base image |
| **Multi-language monorepo** | One `resolve` call covers all `requirements.txt`, `package.json`, `environment.yml`, and `Cargo.toml` dependencies at once |
| **Platform migration** | Before upgrading the OS or Python version, validate every dependency still resolves without conflict |
| **CI/CD pipeline** | Lock all transitive deps across ecosystems on every build; fail the pipeline on new conflicts |
| **Data science stack** | Resolve PyTorch + CUDA + Conda + pip dependencies with GPU compatibility checks |
| **Export to any format** | Same resolution → generate Dockerfile, package.json, requirements.txt, docker-compose.yml, install.sh, CMakeLists.txt, and more |

## Quick Start

### Install

From source (package not yet on PyPI):

```bash
git clone https://github.com/code-with-zeeshan/universal-dependency-resolver.git
cd universal-dependency-resolver
pip install -e .[all]
```

Once published to PyPI:
```bash
pip install ud-resolver[all]         # All extras
pip install ud-resolver              # Core only
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
udr resolve serde tokio -e cargo

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
    data = await aggregator.fetch_package_data("torch", "pypi")
    print(data["version"], data["dependencies"])

    resolver = ConflictResolver()
    result = resolver.resolve([data])
    print(result)

    # Detect and parse manifests from a project directory
    detector = ManifestDetector()
    manifests = detector.scan_directory("./my-project")
    for name, packages in manifests.items():
        print(f"{name}: {len(packages)} deps found")

asyncio.run(main())
```

### Docker (production)

```bash
cp .env.example .env
docker compose up -d
docker compose exec backend alembic upgrade head

# Frontend:  http://localhost:8080
# API Docs:  http://localhost:8000/api/v1/docs
# Grafana:   http://localhost:3000 (admin/admin)
# Jaeger:    http://localhost:16686
```

## How It Works

```
Your request → Fetch metadata from ecosystem registries
                   ↓
            Scan target system (OS, GPU, Python, CUDA)
                   ↓
            Resolve conflicts with SAT solver
                   ↓
            Export to 14+ formats
```

The system runs as a FastAPI service with optional PostgreSQL, Redis, and a Vue.js frontend.

## API Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/packages/search` | GET | Search across ecosystems |
| `/api/v1/packages/{ecosystem}/{name}` | GET | Get package info |
| `/api/v1/packages/{ecosystem}/{name}/details` | GET | Detailed info + compatibility |
| `/api/v1/packages/{ecosystem}/{name}/versions` | GET | List versions |
| `/api/v1/packages/resolve` | POST | Resolve dependencies |
| `/api/v1/packages/export` | POST | Export to any format |
| `/api/v1/packages/export-formats` | GET | Available export formats |
| `/api/v1/system/info` | GET | System information |
| `/api/v1/system/check-compatibility` | POST | Check dependency-system fit |
| `/api/v1/system/analyze-environment` | POST | Parse env files |
| `/api/v1/health` | GET | Health check |

Full reference in [docs/API.md](docs/API.md).

## Testing

```bash
# Unit tests
cd backend && pytest tests/unit/

# Integration tests (requires Docker)
docker compose exec backend pytest tests/integration/

# Frontend tests
cd frontend && npm run test:unit
npm run test:e2e          # requires Chromium
```

## Roadmap

| Priority | Feature | Status |
|----------|---------|--------|
| 🔴 High | Python SDK with async support | ✅ Done |
| 🔴 High | CLI tool for CI/CD | ✅ Done |
| 🟡 Medium | JavaScript/TypeScript SDK | Planned |
| 🟡 Medium | CI/CD integration examples (GitHub Actions, GitLab CI) | Planned |
| 🟡 Medium | SBOM export (CycloneDX, SPDX) | Planned |
| 🟢 Low | WebSocket real-time resolution updates | Researching |
| 🟢 Low | Visual dependency graphs | Researching |
| 🟢 Low | Plugin system for custom ecosystems | Researching |

---

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for production deployment,
[CONTRIBUTING.md](CONTRIBUTING.md) to contribute,
and [LICENSE](LICENSE) for licensing (MIT).
