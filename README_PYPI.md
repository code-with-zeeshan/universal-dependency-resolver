# Universal Dependency Resolver

[![PyPI version](https://img.shields.io/pypi/v/ud-resolver?color=blue)](https://pypi.org/project/ud-resolver/)
[![Python versions](https://img.shields.io/pypi/pyversions/ud-resolver)](https://pypi.org/project/ud-resolver/)
[![License](https://img.shields.io/pypi/l/ud-resolver)](https://github.com/code-with-zeeshan/universal-dependency-resolver/blob/main/LICENSE)
[![CI](https://github.com/code-with-zeeshan/universal-dependency-resolver/actions/workflows/ci.yml/badge.svg)](https://github.com/code-with-zeeshan/universal-dependency-resolver/actions/workflows/ci.yml)

Resolve dependencies across **14 ecosystems** — detect conflicts, check system compatibility, and export to any format.

```bash
# From any ecosystem, resolve together
udr resolve flask>=2.0 torch@pypi react@^18

# Lock your project's dependencies
udr lock

# Check system compatibility
udr check

# Start the API server
udr serve --port 8000
```

---

## Install

```bash
pip install ud-resolver
```

### Optional extras

| Extra | What it adds |
|---|---|
| `[system]` | GPU & system scanning (psutil, pynvml, cpuinfo) |
| `[postgres]` | PostgreSQL support |
| `[monitoring]` | OpenTelemetry, Sentry, Prometheus instrumentation |
| `[all]` | Everything above |

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

## Quick Start

```bash
# Resolve cross-ecosystem packages
udr resolve numpy pandas scikit-learn
udr resolve react vue -e npm
udr resolve serde tokio -e crates

# Lock a project's dependencies
udr lock
udr lock --manifest requirements.txt --dry-run

# Validate lock file
udr verify

# Show dependency tree
udr graph flask django

# Scan a GitHub repo without cloning
udr scan --github https://github.com/user/repo

# System info
udr check
udr info

# List all supported ecosystems
udr list-ecosystems
```

---

## Use as a Python Library

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

---

## Links

- [GitHub](https://github.com/code-with-zeeshan/universal-dependency-resolver) — source, issues, releases
- [CLI Reference](https://github.com/code-with-zeeshan/universal-dependency-resolver/blob/main/docs/CLI.md)
- [Architecture](https://github.com/code-with-zeeshan/universal-dependency-resolver/blob/main/docs/ARCHITECTURE.md)
- [API Docs](https://github.com/code-with-zeeshan/universal-dependency-resolver/blob/main/docs/API.md)
- [Changelog](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases)
- [License: MIT](https://github.com/code-with-zeeshan/universal-dependency-resolver/blob/main/LICENSE)
