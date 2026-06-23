# Universal Dependency Resolver

Resolve dependencies across PyPI, npm, Conda, Maven, Crates.io, and more — detect conflicts, check system compatibility, and export to any format.

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

```bash
git clone https://github.com/yourusername/universal-dependency-resolver.git
cd universal-dependency-resolver

cp .env.example .env

# Core services
docker-compose up -d

# Monitoring stack (optional)
docker-compose --profile monitoring up -d

docker-compose exec backend alembic upgrade head

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
| `/packages/search` | GET | Search across ecosystems |
| `/packages/{ecosystem}/{name}` | GET | Get package info |
| `/packages/{ecosystem}/{name}/details` | GET | Detailed info + compatibility |
| `/packages/{ecosystem}/{name}/versions` | GET | List versions |
| `/packages/resolve` | POST | Resolve dependencies |
| `/packages/export` | POST | Export to any format |
| `/packages/export-formats` | GET | Available export formats |
| `/system/info` | GET | System information |
| `/system/check-compatibility` | POST | Check dependency-system fit |
| `/system/analyze-environment` | POST | Parse env files |
| `/health` | GET | Health check |

Full reference in [docs/API.md](docs/API.md).

## Testing

```bash
# Unit tests
cd backend && pytest tests/unit/

# Integration tests (requires Docker)
docker-compose up -d
docker-compose exec backend pytest tests/integration/

# Frontend tests
cd frontend && npm run test:unit
npm run test:e2e          # requires Chromium
```

## Roadmap

| Priority | Feature | Status |
|----------|---------|--------|
| 🔴 High | Python SDK with async support | In development |
| 🔴 High | CLI tool for CI/CD | In development |
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
