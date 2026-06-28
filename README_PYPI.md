# Universal Dependency Resolver

Resolve dependencies across **PyPI**, **npm**, **Cargo**, **Go**, **Conda**, **Maven**, and more — detect conflicts, check system compatibility, and export to any format.

```
udr resolve numpy pandas scikit-learn
udr resolve react vue -e npm
```

## Install

```bash
pip install ud-resolver
```

With extras:

| Install flag | Adds |
|---|---|
| `[system]` | GPU & system scanning (`psutil`, `pynvml`, `cpuinfo`) |
| `[postgres]` | PostgreSQL support (`psycopg2-binary`, `asyncpg`) |
| `[monitoring]` | OpenTelemetry & Sentry instrumentation |
| `[all]` | Everything |

## Quick Start

```bash
# Resolve dependencies
udr resolve numpy pandas scikit-learn
udr resolve react vue -e npm

# Lock a project's dependencies
udr lock
udr lock --manifest requirements.txt --manifest package.json

# Check system compatibility
udr check
udr info

# Start API server
udr serve --port 8000
```

## Python Library

```python
import asyncio
from backend.core.data_aggregator import DataAggregator
from backend.core.conflict_resolver import ConflictResolver

async def main():
    aggregator = DataAggregator()
    info = await aggregator.get_package_info("flask", ecosystem="pypi")
    print(info["versions"])

    resolver = ConflictResolver()
    result = resolver.resolve([{"name": "flask", "version": ">=2.0"}])

asyncio.run(main())
```

## Features

| Feature | What it does |
|---|---|
| **13 ecosystems** | PyPI, npm, Cargo, Go, Conda, Maven, NuGet, RubyGems, Packagist, Homebrew, APT, APK, CocoaPods |
| **SAT-solver resolution** | Z3-based conflict resolver for complex version constraints |
| **System scanning** | OS, CPU, GPU, CUDA, Python, Node.js, GCC, Java detection |
| **GPU-aware resolution** | Automatically resolves CUDA variants |
| **12 export formats** | requirements.txt, package.json, Dockerfile, docker-compose.yml, pyproject.toml, environment.yml, Cargo.toml, build.gradle, pom.xml, CMakeLists.txt, install.sh, install.bat |
| **CLI + API** | 9 CLI commands + 24 REST API endpoints |
| **Desktop app** | Standalone GUI (download from GitHub Releases) |
| **SAT conflict resolution** | Z3 theorem prover for dependency solving |

## How It Works

```
Your request → Fetch metadata from registry APIs
                   ↓
            Scan target system (OS, GPU, CUDA)
                   ↓
            Resolve conflicts with Z3 SAT solver
                   ↓
            Export to 12 formats
```

## Links

Full documentation at [github.com/code-with-zeeshan/universal-dependency-resolver](https://github.com/code-with-zeeshan/universal-dependency-resolver)
