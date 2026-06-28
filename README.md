# Universal Dependency Resolver

Resolve dependencies across **PyPI**, **npm**, **Cargo**, **Go**, **Conda**, **Maven**, and more — detect conflicts, check system compatibility, and export to any format.

```
udr resolve numpy@pypi torch@pypi
  → numpy 1.26.2, torch 2.1.2+cu121 (CUDA 12.1)
```

## The Problem

Your project pulls in packages from everywhere — Python scripts call Node services, Docker images need both `pip` and `apt` packages, and your CI pipeline has to pin every transitive dependency across all of them.

Existing tools only work within one ecosystem. `pip-compile` handles Python. `npm ls` handles JavaScript. Cross-ecosystem conflicts go undetected until something breaks at runtime. System compatibility — GPU drivers, CUDA versions, OS patches — is never checked.

This tool fixes that.

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

## Two Components

| Component | What it is | How to get |
|---|---|---|
| **CLI / Library** | `udr` CLI tool + Python importable library + REST API server | `pip install ud-resolver` |
| **Desktop app** | Standalone app with built-in GUI, no setup required | Download from [Releases](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases) |

See [docs/COMPONENTS.md](docs/COMPONENTS.md) for a detailed comparison.

## Features

- **13 ecosystems** — PyPI, npm, Cargo, Go, Conda, Maven, NuGet, RubyGems, Packagist, Homebrew, APT, APK, CocoaPods
- **SAT-solver resolution** — Z3-based conflict resolver handles complex version constraints
- **System scanning** — Detects OS, CPU, GPU, CUDA, Python, Node.js, GCC, Java
- **GPU-aware resolution** — Automatically resolves CUDA variants (e.g., `torch` → `torch 2.1.2+cu121`)
- **12 export formats** — requirements.txt, package.json, Dockerfile, docker-compose.yml, pyproject.toml, environment.yml, Cargo.toml, build.gradle, pom.xml, CMakeLists.txt, install.sh, install.bat
- **10 CLI commands** — `serve`, `check`, `resolve`, `info`, `lock`, `scan`, `graph`, `verify`, `list-ecosystems`, `update`
- **24 API endpoints** — Full REST API for programmatic use
- **Desktop GUI** — 14 tabbed views, formatted tables, loading states, auto-update

## CLI Examples

```bash
# Resolve packages from multiple ecosystems
udr resolve numpy pandas scikit-learn
udr resolve react vue -e npm
udr resolve serde tokio -e crates

# Lock a project's dependencies
udr lock
udr lock --manifest requirements.txt --manifest package.json --dry-run

# Validate a lock file
udr verify
udr verify --lock-file udr-lock.json

# Show dependency graph
udr graph flask django

# List supported ecosystems
udr list-ecosystems

# Re-resolve a single package and update lock
udr update flask

# Scan a GitHub repo without cloning
udr scan --github https://github.com/user/repo

# Override CUDA version for GPU packages on CPU-only machines
udr lock --cuda 12.1
udr scan --github https://github.com/user/repo --cuda 11.8

# System information
udr check
udr info
```

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
        include_dependencies=True, include_versions=True
    )

    resolver = ConflictResolver()
    result = resolver.resolve([
        {"name": "flask", "version": ">=2.0"},
        {"name": "django", "version": ">=4.0"},
    ], system_info=system_info)

asyncio.run(main())
```

## API Server

```bash
udr serve --host 0.0.0.0 --port 8000
```

The API is documented at `http://localhost:8000/api/v1/docs` (Swagger UI). See [docs/API.md](docs/API.md) for a full reference.

## Desktop App

Download from [GitHub Releases](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases) — no Python or Node.js required. See [docs/COMPONENTS.md](docs/COMPONENTS.md) for details.

## Testing

```bash
python -m pytest tests/unit/        # 399 unit tests
python -m pytest tests/integration/ # 69 integration tests (SQLite, no Docker needed)
```

## How It Works

```
Your request → Fetch metadata from registry APIs
                   ↓
            Scan target system (OS, GPU, Python, CUDA)
                   ↓
            Resolve conflicts with Z3 SAT solver
                   ↓
            Export to 12 formats
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture.

## Links

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — codebase architecture
- [docs/COMPONENTS.md](docs/COMPONENTS.md) — component guide
- [docs/CLI.md](docs/CLI.md) — CLI command reference
- [docs/API.md](docs/API.md) — API reference
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — development setup
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — common issues
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute
- [LICENSE](LICENSE) — MIT
