# Universal Dependency Resolver

[![PyPI version](https://img.shields.io/pypi/v/ud-resolver?color=blue)](https://pypi.org/project/ud-resolver/)
[![Python versions](https://img.shields.io/pypi/pyversions/ud-resolver)](https://pypi.org/project/ud-resolver/)
[![License](https://img.shields.io/pypi/l/ud-resolver)](https://github.com/code-with-zeeshan/universal-dependency-resolver/blob/main/LICENSE)
[![CI](https://github.com/code-with-zeeshan/universal-dependency-resolver/actions/workflows/ci.yml/badge.svg)](https://github.com/code-with-zeeshan/universal-dependency-resolver/actions/workflows/ci.yml)

Your Python backend needs PyPI. Your React frontend needs npm. Your Rust CLI needs crates.io. Your Go service needs Go modules. **One `udr lock` gives you one lock file for all of them.**

```bash
# Resolve across ecosystems in one command
udr resolve flask>=2.0 torch@pypi react@^18

# Lock your project across all manifests
udr lock

# Check system + CVE + deprecated packages — 18 ecosystems at once
udr check --cve --deprecated
```

---

## Install

```bash
pip install ud-resolver

# For full capacity — Rust-backed PubGrub + Z3 + richer system data:
pip install "ud-resolver[z3,pubgrub,system]"
```

The base install resolves dependencies, detects GPU/OS/CPU, and handles GPU variant selection — no extras needed. The extras add speed (Rust PubGrub on large graphs), conflict detection (Z3 for CUDA XOR rules), and richer telemetry (GPU temperature, per-process memory). All solvers fall back gracefully when an extra is missing.

### Optional extras

| Extra | What it adds |
|---|---|
| `[system]` | Richer system data via Python libs (pynvml → GPU temp/util, psutil → per-process memory, cpuinfo → detailed model). Base `ud-resolver` already detects GPU/OS/CPU via `nvidia-smi`/`lspci`/`platform` — no extra needed for constraint resolution. |
| `[z3]` | Z3 SAT solver (46MB) for CUDA XOR conflict rules + cross-eco constraints. GPU version filtering works without Z3 (pre-filtered before solver). |
| `[pubgrub]` | Rust-backed PubGrub solver (faster CDCL on 100+ package graphs). Falls back to pure-Python automatically if wheel unavailable / build fails. |
| `[postgres]` | PostgreSQL support |
| `[monitoring]` | OpenTelemetry, Sentry, Prometheus instrumentation |
| `[all]` | Everything above |

---

## Features

| Capability | Detail |
|---|---|
| **25 ecosystems** (18 resolvable + 7 query-only + 2 internal) | **Resolvable:** PyPI, Conda, npm, Crates.io, Maven, Go Modules, APT, APK, CocoaPods, Homebrew, NuGet, Packagist, RubyGems, Pub, Gradle, Swift, Hex, Haskell — **Query-only** (version info, manifest parsing, no SAT traversal): Nix, GNU Guix, Docker, Helm, Terraform, Vcpkg, Conan — **Internal:** Docs DB, Custom DB |
| **SAT-solver resolution** | AutoSolver (default, profiles graph → Z3/PubGrub/Hybrid per workload) with per-ecosystem isolation, CUDA-aware conflict detection, and DFS backtracking fallback |
| **System-aware** | Detects OS, CPU, GPU, CUDA, Python, Node.js, GCC, Java — resolution adapts to your environment |
| **GPU-aware** | Automatically selects CUDA variants (e.g. `torch 2.1.2+cu121`) when NVIDIA GPU detected |
| **15 export formats** | requirements.txt, package.json, Dockerfile, docker-compose.yml, pyproject.toml, environment.yml, Cargo.toml, build.gradle, pom.xml, CMakeLists.txt, install.sh, install.bat, Gemfile, composer.json, go.mod |
| **20 CLI commands** | serve, check, resolve, lock, scan, graph, verify, list-ecosystems, update, install, completion, why, outdated, diff, search, details, auth, index, sbom, tools |
| **56 REST API endpoints** | Full programmatic API with OpenAPI docs |
| **Desktop GUI** | Standalone Electron app — no Python or Node.js needed |
| **Zero config** | SQLite by default, in-memory cache, no Docker required |
| **Lock file** | Reproducible `udr.lock` with full system snapshot |

---

## Why UDR?

- **Cross-ecosystem resolution**: A Python package that transitively depends on an npm package gets solved in one pass, not two.
- **SAT-solver engine**: Real Z3/PubGrub CDCL solver, not greedy backtracking. Finds valid solutions dependency graph heuristics miss.
- **System-aware**: GPU type + CUDA version are resolution constraints — `torch 2.1.2+cu121` selected automatically when NVIDIA GPU detected.
- **Supply chain built-in**: CVE scanning, license compliance, deprecation checks, lock-file signing (Ed25519), SBOM export (SPDX/CycloneDX), policy engine.
- **3 solver backends**: AutoSolver profiles your graph and selects Z3, PubGrub, or Hybrid — with fallback chain if the first choice fails.

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

# List all supported ecosystems
udr list-ecosystems
```

---

## Use as a Python Library

```python
import asyncio
from backend.core.data_aggregator import DataAggregator
from backend.core.system_scanner import SystemScanner
from backend.orchestrator.resolve import create_solver

async def main():
    scanner = SystemScanner()
    system_info = await scanner.scan_all()

    aggregator = DataAggregator()
    info = await aggregator.get_package_info(
        "torch", ecosystem="pypi",
        include_dependencies=True, include_versions=True,
    )

    resolver = create_solver()
    result = resolver.resolve_dependencies(
        packages=[{"name": "flask", "version": ">=2.0"}],
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
               Resolve conflicts with AutoSolver (Z3 / PubGrub / Hybrid)
                      │
                      ▼
              Export to 15 formats or write lock file
```

---

## Links

- [GitHub](https://github.com/code-with-zeeshan/universal-dependency-resolver) — source, issues, releases
- [CLI Reference](https://github.com/code-with-zeeshan/universal-dependency-resolver/blob/main/docs/CLI.md)
- [Architecture](https://github.com/code-with-zeeshan/universal-dependency-resolver/blob/main/docs/ARCHITECTURE.md)
- [API Docs](https://github.com/code-with-zeeshan/universal-dependency-resolver/blob/main/docs/API.md)
- [Changelog](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases)
- [License: MIT](https://github.com/code-with-zeeshan/universal-dependency-resolver/blob/main/LICENSE)
