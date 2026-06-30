# Universal Dependency Resolver

[![PyPI version](https://img.shields.io/pypi/v/ud-resolver?color=blue)](https://pypi.org/project/ud-resolver/)
[![Python versions](https://img.shields.io/pypi/pyversions/ud-resolver)](https://pypi.org/project/ud-resolver/)
[![License](https://img.shields.io/github/license/code-with-zeeshan/universal-dependency-resolver)](LICENSE)
[![CI](https://github.com/code-with-zeeshan/universal-dependency-resolver/actions/workflows/ci.yml/badge.svg)](https://github.com/code-with-zeeshan/universal-dependency-resolver/actions/workflows/ci.yml)
[![Desktop Build](https://github.com/code-with-zeeshan/universal-dependency-resolver/actions/workflows/build-desktop.yml/badge.svg)](https://github.com/code-with-zeeshan/universal-dependency-resolver/actions/workflows/build-desktop.yml)
[![Type checked](https://img.shields.io/badge/mypy-0%20errors-brightgreen)](#)

Resolve dependencies across **14 ecosystems** — detect conflicts, check system compatibility, and export to any format.

```
  udr resolve torch@pypi express@npm serde@crates
  → Compatible versions across PyPI, npm, and Cargo
  → CUDA-aware: torch 2.1.2+cu121 (GPU) selected automatically
```

---

## The Problem

Your project pulls in packages from everywhere — Python scripts call Node services, Docker images need both `pip` and `apt` packages, and your CI pipeline has to pin every transitive dependency across all of them.

Existing tools only work within one ecosystem. `pip-compile` handles Python. `npm ls` handles JavaScript. Cross-ecosystem conflicts go undetected until something breaks at runtime. System compatibility — GPU drivers, CUDA versions, OS patches — is never checked.

**This tool fixes that.**

---

## Quick Start

```bash
pip install ud-resolver

# Resolve cross-ecosystem packages
udr resolve flask>=2.0 react@^18

# Lock all dependencies in your project
udr lock

# Check system compatibility
udr check

# Start the API server
udr serve --port 8000
```

---

## Features

| Capability | Detail |
|---|---|
| **14 ecosystems** | PyPI, Conda, npm, Crates.io (Rust), Maven (Java), Go Modules, APT (Debian), APK (Alpine), CocoaPods, Homebrew, NuGet, Packagist, RubyGems, Pub (Dart/Flutter) |
| **SAT-solver resolution** | Z3-based conflict resolver handles complex cross-ecosystem version constraints |
| **System-aware** | Detects OS, CPU, GPU, CUDA, Python, Node.js, GCC, Java — resolution adapts to your environment |
| **GPU-aware** | Automatically selects CUDA variants (e.g. `torch 2.1.2+cu121`) when NVIDIA GPU detected |
| **12 export formats** | requirements.txt, package.json, Dockerfile, docker-compose.yml, pyproject.toml, environment.yml, Cargo.toml, build.gradle, pom.xml, CMakeLists.txt, install.sh, install.bat |
| **13 CLI commands** | serve, check, resolve, info, lock, scan, graph, verify, list-ecosystems, update, install, restore, completion |
| **24 REST API endpoints** | Full programmatic API with OpenAPI docs |
| **Desktop GUI** | Standalone Electron app — no Python or Node.js needed |
| **Zero config** | SQLite by default, in-memory cache, no Docker required |
| **Lock file** | Reproducible `udr-lock.json` with full system snapshot |

---

## Components

| Component | What it is | How to get |
|---|---|---|
| **CLI / Library** | `udr` CLI tool + Python importable library + REST API server | `pip install ud-resolver` |
| **Desktop app** | Standalone app with built-in GUI, no setup required | Download from [Releases](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases) |

See [docs/COMPONENTS.md](docs/COMPONENTS.md) for a detailed comparison.

---

## CLI Examples

```bash
# Resolve packages from any ecosystem
udr resolve numpy pandas scikit-learn
udr resolve react vue -e npm
udr resolve serde tokio -e crates

# Lock a project's dependencies
udr lock
udr lock --manifest requirements.txt --manifest package.json --dry-run

# Validate a lock file
udr verify

# Show dependency graph
udr graph flask django

# Scan a GitHub repo without cloning
udr scan --github https://github.com/user/repo

# CUDA override on CPU-only machines
udr lock --cuda 12.1

# System information
udr check
udr info

# List supported ecosystems
udr list-ecosystems

# Re-resolve a single package
udr update flask

# Generate shell completion scripts
udr completion bash
```

---

## Python Library

```python
import asyncio
from backend.core.data_aggregator import DataAggregator
from backend.core.conflict_resolver import ConflictResolver
from backend.core.system_scanner import SystemScanner

async def main():
    scanner = SystemScanner()
    system_info = await scanner.scan_all()

    aggregator = DataAggregator()
    info = await aggregator.get_package_info(
        "torch", ecosystem="pypi",
        include_dependencies=True, include_versions=True,
    )

    resolver = ConflictResolver()
    result = resolver.resolve(
        [{"name": "flask", "version": ">=2.0"}],
        system_info=system_info,
    )

asyncio.run(main())
```

---

## API Server

```bash
udr serve --host 0.0.0.0 --port 8000
```

OpenAPI docs at `http://localhost:8000/api/v1/docs` (Swagger UI). Full reference in [docs/API.md](docs/API.md).

---

## Testing

```bash
# All tests
python -m pytest tests/                        # 760+ tests

# Unit only (fast, no deps)
python -m pytest tests/unit/

# CLI end-to-end (black-box subprocess tests)
python -m pytest tests/cli/

# Integration tests (SQLite, no Docker needed)
python -m pytest tests/integration/

# Desktop smoke tests
cd desktop && node --test tests/
```

---

## How It Works

```
Your request ──► Fetch metadata from registry APIs
                      │
                      ▼
              Scan target system (OS, GPU, CUDA, runtimes)
                      │
                      ▼
              Resolve conflicts with Z3 SAT solver
                      │
                      ▼
              Export to 12 formats or write lock file
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture.

---

## Documentation

| Guide | Description |
|---|---|
| [CLI Reference](docs/CLI.md) | All 13 commands with flags, examples, exit codes |
| [API Reference](docs/API.md) | 24 REST endpoints, request/response schemas |
| [Architecture](docs/ARCHITECTURE.md) | Codebase structure, layers, key decisions |
| [Development](docs/DEVELOPMENT.md) | Setup, running, testing, project structure |
| [Components](docs/COMPONENTS.md) | CLI vs Desktop vs Library comparison |
| [Deployment](docs/DEPLOYMENT.md) | Production deployment guide |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and solutions |
| [Contributing](CONTRIBUTING.md) | How to contribute |
| [Security](SECURITY.md) | Security policy |

---

## License

MIT — see [LICENSE](LICENSE).
