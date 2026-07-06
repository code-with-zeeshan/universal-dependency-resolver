# User Guide

## Table of Contents

1. [Introduction](#1-introduction)
2. [Prerequisites](#2-prerequisites)
3. [Installation](#3-installation)
4. [Quick Start](#4-quick-start)
5. [How It Works](#5-how-it-works)
6. [Components](#6-components)
7. [CLI Usage](#7-cli-usage)
8. [API Usage](#8-api-usage)
9. [Python Library Usage](#9-python-library-usage)
10. [Desktop App](#10-desktop-app)
11. [Features in Detail](#11-features-in-detail)
12. [Deployment](#12-deployment)
13. [Troubleshooting](#13-troubleshooting)
14. [Performance](#14-performance)
15. [Where to Go Next](#15-where-to-go-next)

---

## 1. Introduction

**Universal Dependency Resolver (UDR)** is a cross-ecosystem dependency resolution tool. It resolves, locks, and exports dependencies across **20 package ecosystems** using a Z3 SAT-solver engine that finds compatible versions even across ecosystem boundaries.

### The problem it solves

Your project pulls in packages from everywhere — Python scripts call Node services, Docker images need both `pip` and `apt` packages, and your CI pipeline has to pin every transitive dependency across all of them.

Existing tools only work within one ecosystem. `pip-compile` handles Python. `npm ls` handles JavaScript. Cross-ecosystem conflicts go undetected until something breaks at runtime. System compatibility — GPU drivers, CUDA versions, OS patches — is never checked.

**UDR fixes that.**

---

## 2. Prerequisites

### CLI / Library / API Server

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11 – 3.13 | 3.10 may work but is not tested |
| pip | 23+ | `pip install --upgrade pip` if older |
| OS | Linux, macOS, Windows | All features tested on Linux; macOS/Windows have full support |

No other services required. SQLite + in-memory cache work out of the box.

### Desktop App

No prerequisites. The desktop app bundles everything — Python backend, all dependencies, and the GUI — into a single installable package.

### Optional dependencies

| Extra | Adds | Used for |
|---|---|---|
| `[system]` | psutil, py-cpuinfo, distro, gputil, nvidia-ml-py | GPU detection, CPU info, OS details |
| `[postgres]` | psycopg2-binary, redis, celery, aiocache | PostgreSQL + Redis + async task queue |
| `[monitoring]` | OpenTelemetry, Sentry, Prometheus | Tracing, error tracking, metrics |
| `[all]` | Everything above | Full install |

### Build tools (for compiling native extensions)

If `z3-solver` or other packages fail to compile:

| OS | Command |
|---|---|
| Ubuntu/Debian | `sudo apt-get install build-essential pkg-config python3-dev` |
| macOS | `xcode-select --install` |
| Windows | Install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) |

---

## 3. Installation

### Install from PyPI

```bash
pip install ud-resolver
```

With extras:

```bash
pip install "ud-resolver[system,postgres,monitoring]"
pip install "ud-resolver[all]"     # everything
```

### Install from source (development)

```bash
git clone https://github.com/code-with-zeeshan/universal-dependency-resolver.git
cd universal-dependency-resolver
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### Verify installation

```bash
udr --version
udr list-ecosystems
```

---

## 4. Quick Start

```bash
# Resolve cross-ecosystem packages
udr resolve flask>=2.0 react@^18
udr resolve numpy@pypi express@npm serde@crates

# Lock all dependencies in your project
udr lock

# Check system compatibility
udr check

# Start the API server
udr serve --port 8000
```

---

## 5. How It Works

```mermaid
sequenceDiagram
    participant User as 👤 User
    participant CLI as 🖥️ CLI
    participant Agg as 📊 DataAggregator
    participant Scanner as 🔍 SystemScanner
    participant Solver as 🧠 ConflictResolver
    participant Export as 📤 ExportGenerator

    User->>CLI: udr resolve flask>=2.0 react@npm
    Note over CLI,Agg: Step 1 — Fetch metadata from registry APIs
    CLI->>Agg: get_package_info("flask", "pypi")
    Agg->>Agg: Query PyPI API
    Agg-->>CLI: versions + dependencies
    CLI->>Agg: get_package_info("react", "npm")
    Agg->>Agg: Query npm registry
    Agg-->>CLI: versions + dependencies
    Note over CLI,Scanner: Step 2 — Scan target system
    CLI->>Scanner: scan_all()
    Scanner-->>CLI: OS, CPU, GPU, CUDA, runtimes
    Note over CLI,Solver: Step 3 — SAT resolution
    CLI->>Solver: resolve(packages, system_info)
    Solver->>Solver: Z3 solver optimizes<br/>cross-ecosystem constraints
    Solver-->>CLI: compatible versions
    Note over CLI,Export: Step 4 — Export / Lock
    CLI->>Export: export(packages, "requirements.txt")
    Export-->>CLI: formatted output
    CLI-->>User: ✅ Resolution complete
```

### Step by step

1. **Metadata fetch** — Queries registry APIs (PyPI, npmjs.org, crates.io, etc.) for each package's versions, dependencies, and system requirements
2. **System scan** — Detects OS, CPU, GPU, CUDA version, Python version, Node.js, GCC, Java
3. **SAT resolution** — Z3 solver finds a set of mutually compatible versions across all packages and ecosystems. Handles cross-ecosystem constraints (e.g. `torch` on PyPI depending on `nvidia-cublas`). GPU-aware: selects CUDA variants when NVIDIA GPU detected
4. **Export / Lock** — Writes `udr.lock` or exports to any of 15 formats

### Architecture overview

```mermaid
graph TB
    subgraph UserLayer["👤 User Interfaces"]
        CLI["🖥️ CLI<br/><code>backend/cli/</code><br/>18 commands"]
        DESKTOP["🖥️ Desktop App<br/><code>Electron + GUI</code>"]
    end

    subgraph APILayer["🌐 API Layer (FastAPI)"]
        API["<code>main.py</code><br/>App + middleware + routes<br/>packages · system · auth · scan · lock"]
    end

    subgraph CoreLayer["🧠 Core Logic"]
        CR["<code>conflict_resolver.py</code><br/>Z3 SAT solver"]
        DA["<code>data_aggregator.py</code><br/>Async aggregation"]
        EG["<code>export_generator.py</code><br/>15 export formats"]
        SS["<code>system_scanner.py</code><br/>OS · GPU · CUDA · runtimes"]
        MD["<code>manifest_detector.py</code><br/>47+ manifest/lock patterns"]
        CACHE["<code>cache.py</code><br/>DictCache + Redis"]
    end

    subgraph DBLayer["🗄️ Database & Data Sources"]
        DS["📦 20 Data Source Clients<br/>PyPI · npm · Crates · Maven · Go<br/>RubyGems · NuGet · Conda · APT · APK<br/>Homebrew · CocoaPods · Pub · Gradle<br/>Swift · Hex · Haskell · Packagist<br/>Docs · Custom DB"]
        DB["🗄️ SQLite (default) / PostgreSQL"]
    end

    CLI -->|"inline"| API
    CLI -->|"direct"| CoreLayer
    CLI -->|"subprocess"| DESKTOP
    DESKTOP -->|"HTTP"| API
    API --> CoreLayer
    CoreLayer --> DS
    CoreLayer --> DB
```

---

## 6. Components

| Component | What it is | How to get | Best for |
|---|---|---|---|
| **CLI** | `udr` command-line tool | `pip install ud-resolver` | CI/CD pipelines, scripts, ad-hoc resolution |
| **Python library** | Importable `backend.*` modules | `pip install ud-resolver` | Embedding in your own tools |
| **API server** | FastAPI REST server | `udr serve` (same pip package) | Programmatic access, web frontends |
| **Desktop app** | Standalone Electron GUI | Download from Releases | Users who want a GUI, no terminal |

### When to use each

| You want to... | Use |
|---|---|
| Resolve deps in a CI/CD pipeline or script | **CLI** |
| Call the resolver from Python code | **Python library** |
| Use a web GUI, no terminal | **Desktop app** |
| Expose the resolver as a service | **API server** (`udr serve`) |

---

## 7. CLI Usage

All 18 commands support `--help` for inline usage.

### Global flags

| Flag | Description |
|---|---|
| `--version` | Print version and exit |
| `--offline` | Use cached data only, no network |
| `-h, --help` | Show help |

### Command reference

| Command | What it does | Example |
|---|---|---|
| `serve` | Start REST API server | `udr serve --port 8000` |
| `check` | Scan system (OS, CPU, GPU, CUDA) | `udr check --json` |
| `resolve` | Resolve compatible versions | `udr resolve flask@npm torch@pypi` |
| `lock` | Auto-detect manifests, resolve, write udr.lock | `udr lock --dry-run` |
| `scan` | Scan GitHub repo or local directory | `udr scan --github https://github.com/user/repo` |
| `graph` | Show dependency tree | `udr graph flask django` |
| `verify` | Validate lock file versions | `udr verify` |
| `list-ecosystems` | List supported ecosystems | `udr list-ecosystems --json` |
| `update` | Re-resolve a single package | `udr update flask` |
| `install` | Generate install commands from lock file | `udr install --dry-run` |
| `completion` | Generate shell completions | `udr completion bash` |
| `why` | Explain why a version was selected | `udr why flask` |
| `outdated` | Check for newer versions | `udr outdated --json` |
| `diff` | Compare two lock files | `udr diff old.lock new.lock` |
| `search` | Search packages across ecosystems | `udr search numpy --limit 50` |
| `auth` | Manage API keys for the API server | `udr auth create --name my-key` |
| `index` | Manage offline SQLite indexes | `udr index status` |
| `details` | Show package details | `udr details react -e npm` |

### Package spec syntax

Use `name@ecosystem` to specify which ecosystem a package belongs to:

| Spec | Package | Ecosystem |
|---|---|---|
| `numpy` | numpy | pypi (default) |
| `numpy@pypi` | numpy | pypi |
| `@angular/core@npm` | @angular/core | npm |
| `express@npm` | express | npm |
| `serde@crates` | serde | crates |
| `torch@pypi` | torch | pypi |

The `@` delimiter splits on the **last** `@` so scoped npm packages (`@angular/core`) work correctly.

### CUDA / GPU handling

The resolver is GPU-aware for PyPI packages. When a package has CUDA-tagged variants (e.g. `torch 2.1.2+cu121`, `torch 2.1.2+cu118`), the tool selects the best match based on the system's CUDA version.

| System CUDA | Behavior |
|---|---|
| Detected (e.g. `12.1`) | Best-matching CUDA variant selected |
| No GPU detected | CPU-only versions used. No CUDA variants selected |
| `--cuda` flag provided | Overrides auto-detection |

```bash
# On a CPU-only machine, force CUDA resolution
udr lock --cuda 12.1
udr resolve torch --cuda 12.1
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Error (resolution failed, file not found, invalid input) |
| `130` | Cancelled by user (Ctrl+C) |

### Recognized manifest and lock files

| File | Ecosystem | Type |
|---|---|---|
| `requirements.txt`, `*-requirements.txt` | pypi | Manifest |
| `pyproject.toml`, `Pipfile` | pypi | Manifest |
| `poetry.lock`, `uv.lock`, `Pipfile.lock` | pypi | Lock |
| `package.json` | npm | Manifest |
| `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` | npm | Lock |
| `Cargo.toml` | crates | Manifest |
| `Cargo.lock` | crates | Lock |
| `go.mod` | gomodules | Manifest |
| `environment.yml` | conda | Manifest |
| `Gemfile` | rubygems | Manifest |
| `Gemfile.lock` | rubygems | Lock |
| `composer.json` | packagist | Manifest |
| `composer.lock` | packagist | Lock |
| `pubspec.yaml` | pub | Manifest |
| `build.gradle`, `build.gradle.kts` | gradle | Manifest |
| `Package.swift` | swift | Manifest |
| `Package.resolved` | swift | Lock |
| `mix.exs` | hex | Manifest |
| `mix.lock` | hex | Lock |
| `*.cabal` | haskell | Manifest |
| `pom.xml` | maven | Manifest |
| `Podfile`, `Podfile.lock` | cocoapods | Manifest |
| `packages.config` | nuget | Manifest |
| `Brewfile`, `Brewfile.lock.json` | homebrew | Manifest |
| `apt-packages.txt` | apt | Manifest |
| `apk-packages.txt` | apk | Manifest |
| `udr.lock` | — | Self (UDR lock file) |

---

## 8. API Usage

Start the server:

```bash
udr serve --host 0.0.0.0 --port 8000
```

Swagger UI: `http://localhost:8000/api/v1/docs`

### Key endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/api/v1/system/info` | System information |
| `POST` | `/api/v1/packages/resolve` | Resolve dependencies |
| `GET` | `/api/v1/packages/search?q=numpy` | Search packages |
| `GET` | `/api/v1/packages/{eco}/{name}/details` | Package details |
| `GET` | `/api/v1/packages/{eco}/{name}/versions` | Available versions |
| `GET` | `/api/v1/packages/{eco}/{name}/dependencies` | Dependency tree |
| `POST` | `/api/v1/scan/github` | Scan GitHub repo |
| `POST` | `/api/v1/scan/local` | Scan local directory |
| `POST` | `/api/v1/generate-lock` | Generate lock file |
| `POST` | `/api/v1/verify` | Verify lock file |
| `POST` | `/api/v1/graph` | Dependency graph |
| `POST` | `/api/v1/install-commands` | Get install commands |
| `GET` | `/api/v1/index/status` | List offline indexes |
| `POST` | `/api/v1/index/pull` | Download pre-built index |
| `POST` | `/api/v1/index/build` | Build index from package data |
| `GET` | `/api/v1/completion/{shell}` | Generate shell completion script |

### Example: Resolve packages via API

```bash
curl -X POST http://localhost:8000/api/v1/packages/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "packages": [
      {"name": "flask", "ecosystem": "pypi", "version": ">=2.0"},
      {"name": "react", "ecosystem": "npm", "version": "^18"}
    ],
    "auto_detect_system": true
  }'
```

### Run modes

| Mode | Auth | CMD |
|---|---|---|
| `local` (default) | None | `udr serve` |
| `saas` | JWT + API key | `udr serve --mode saas` |

---

## 9. Python Library Usage

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

## 10. Desktop App

The desktop app is a standalone Electron application — no Python, Node.js, or any runtime required.

### Download

Download from [GitHub Releases](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases):

| Platform | File |
|---|---|
| Windows 10+ | `UDR-Setup-x.y.z.exe` |
| macOS 11+ (Intel) | `UDR-x.y.z-x64.dmg` |
| macOS 11+ (Apple Silicon) | `UDR-x.y.z-arm64.dmg` |
| Linux (x86_64) | `UDR-x.y.z-x86_64.AppImage` |
| Linux (ARM64) | `UDR-x.y.z-arm64.AppImage` |

### Interface

Single-page app with a collapsible icon sidebar:

| Section | Tabs |
|---|---|
| **Overview** | Dashboard |
| **Packages** | Resolve, Search, Details, Versions, Dependencies, Compatibility |
| **System** | System |
| **Project** | Scan, Graph, Verify Lock, Install, Restore, Update |

### Features

- 14 tabbed views — no raw JSON shown
- System tray with quick-access menu
- Auto-update checks on launch
- Desktop notifications
- Keyboard shortcuts (Ctrl+K for Resolve, Ctrl+R to reload)

---

## 11. Features in Detail

### 20 supported ecosystems

| Ecosystem | Language | Registry | Client |
|---|---|---|---|
| PyPI | Python | pypi.org | `pypi_client.py` |
| npm | JavaScript/TypeScript | registry.npmjs.org | `npm_client.py` |
| Conda | Python/Multi | anaconda.org | `conda_client.py` |
| Maven | Java | repo1.maven.org | `maven_client.py` |
| Crates.io | Rust | crates.io | `crates_client.py` |
| Go Modules | Go | proxy.golang.org | `gomodules_client.py` |
| NuGet | C#/.NET | api.nuget.org | `nuget_client.py` |
| RubyGems | Ruby | rubygems.org | `rubygems_client.py` |
| Packagist | PHP | packagist.org | `packagist_client.py` |
| Homebrew | System | formulae.brew.sh | `homebrew_client.py` |
| CocoaPods | Swift/ObjC | trunk.cocoapods.org | `cocoapods_client.py` |
| APT | Debian/Ubuntu | deb.debian.org | `apt_client.py` |
| APK | Alpine | dl-cdn.alpinelinux.org | `apk_client.py` |
| Pub | Dart/Flutter | pub.dev | `pub_client.py` |
| Gradle | Java/Kotlin | plugins.gradle.org | `gradle_client.py` |
| Swift | Swift | swiftpackageindex.com | `swift_client.py` |
| Hex | Elixir | hex.pm | `hex_client.py` |
| Haskell | Haskell | hackage.haskell.org | `haskell_client.py` |
| Docs DB | Documentation | Internal | `docs_client.py` |
| Custom DB | Custom | Internal | `custom_client.py` |

### SAT-solver resolution

Uses Z3 (Microsoft's theorem prover) to find compatible versions across all ecosystems simultaneously:
- Handles complex cross-ecosystem version constraints
- Detects and reports conflicts with specific error messages
- Configurable timeout via `SOLVER_TIMEOUT` env var (default: 120s)
- Falls back to backtracking search when SAT times out

### System awareness

Detects and adapts to your environment:
- OS, kernel version, architecture
- CPU model, core count, architecture
- GPU model, VRAM, driver version
- CUDA version (via pynvml, nvcc, nvidia-smi)
- Python, Node.js, GCC, Java versions
- Memory (total, available)
- Accelerator detection: TPU (Edge TPU, Cloud TPU), NPU (Intel Myriad, Qualcomm Hexagon, Rockchip, NVIDIA DLA, Graphcore IPU), Apple Neural Engine (M1–M4)
- Network speed benchmark (DNS latency, HTTP latency, download bandwidth)

### GPU-aware resolution

Automatically selects CUDA variants (e.g. `torch 2.1.2+cu121`) when an NVIDIA GPU is detected. Use `--cuda` flag to override on CPU-only machines.

### 15 export formats

| Format | Description |
|---|---|
| `requirements.txt` | Python pip format |
| `package.json` | npm format |
| `Dockerfile` | Docker image with resolved deps |
| `docker-compose.yml` | Docker Compose service |
| `pyproject.toml` | Python project metadata |
| `environment.yml` | Conda environment |
| `Cargo.toml` | Rust dependencies |
| `build.gradle` | Gradle dependencies |
| `pom.xml` | Maven dependencies |
| `CMakeLists.txt` | CMake dependencies |
| `install.sh` | Shell install script |
| `install.bat` | Windows batch install script |
| `Gemfile` | Ruby bundler format |
| `composer.json` | PHP composer format |
| `go.mod` | Go module format |

### Lock file

Reproducible `udr.lock` with:
- Full system snapshot (OS, CPU, GPU, CUDA)
- All resolved packages with versions
- Source manifest tracking
- Vulnerability information
- CUDA variant tracking

### Cross-ecosystem transitive resolution

Resolves transitive dependencies across ecosystem boundaries. For example, if an npm package depends on a PyPI package, both are resolved together with full constraint propagation.

### Security

- JWT authentication (saas mode)
- API keys for programmatic access
- Rate limiting (per-endpoint)
- CORS, CSP, HSTS security headers
- CSRF protection
- SQL injection prevention (SQLAlchemy ORM)
- Input validation (Pydantic)

---

## 12. Deployment

### Production server

```bash
pip install ud-resolver
export DATABASE_URL=postgresql://user:pass@host:5432/udr
export ENABLE_AUTH=true
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
udr serve --host 0.0.0.0 --port 8000 --workers 4
```

### Docker

```bash
docker run ud-resolver:latest serve --host 0.0.0.0 --port 8000
```

### systemd service

```ini
[Unit]
Description=UDR API Server
After=network.target

[Service]
Type=simple
User=udr
ExecStart=/usr/local/bin/udr serve --host 0.0.0.0 --port 8000
Environment=DATABASE_URL=postgresql://...
Environment=REDIS_URL=redis://...
Restart=always

[Install]
WantedBy=multi-user.target
```

### Environment variables

See `.env.example` in the repository root for all available variables.

---

## 13. Troubleshooting

### Common issues

| Problem | Solution |
|---|---|
| `udr` command not found | Check Python Scripts/bin is on PATH, or run `python -m backend.cli` |
| `z3-solver` fails to install | Install build tools: `sudo apt-get install build-essential` (Linux) or `xcode-select --install` (macOS) |
| `ModuleNotFoundError: No module named 'backend'` | Run `pip install -e ".[dev,system]"` |
| Resolution is slow | First run fetches from remote registries; subsequent runs use cache |
| `lock` finds no manifests | Use `--manifest path/to/file` to specify explicitly |
| Port already in use | `udr serve --port 8001` or `kill -9 $(lsof -ti :8000)` |
| SAT solver timed out | Increase timeout: `export UDR_SOLVER_TIMEOUT=120` |
| CUDA variants not selected | Use `--cuda 12.1` to force CUDA-aware resolution |

### Getting help

Open an issue at https://github.com/code-with-zeeshan/universal-dependency-resolver/issues with:
- Full error message
- OS and Python version
- The command you ran
- Output of `udr --version`

---

## 14. Performance

| Operation | Typical time |
|---|---|
| CLI startup | ~0.85s (lazy imports avoid loading Z3 for simple commands) |
| Simple resolution (1-3 packages, 1 ecosystem) | <1s (after metadata fetch) |
| Complex resolution (multi-ecosystem, many constraints) | Varies — depends on Z3 solver |
| System scan | <500ms |
| GPU detection | <100ms |

### Caching

| Layer | Type | TTL |
|---|---|---|
| Package metadata | DictCache or Redis | 1 hour |
| Resolution results | DictCache or Redis | 1 hour |
| System info | DictCache | 5 minutes |

All registry API calls use `aiohttp` with connection pooling and concurrent fetching via `asyncio.gather`.

---

## 15. Where to Go Next

| Resource | What it covers |
|---|---|
| [CLI Reference](CLI.md) | Every command with flags and examples |
| [API Reference](API.md) | 47 REST endpoints with request/response schemas |
| [Architecture](ARCHITECTURE.md) | Codebase structure, layers, design decisions |
| [Components](COMPONENTS.md) | CLI vs Desktop vs Library comparison |
| [Development](DEVELOPMENT.md) | Setup, testing, project structure |
| [Deployment](DEPLOYMENT.md) | Production deployment guide |
| [Performance](PERFORMANCE.md) | SAT solver benchmarks, optimization tips |
| [Desktop](DESKTOP.md) | Desktop app build and usage |
| [Troubleshooting](TROUBLESHOOTING.md) | Common issues and solutions |
| [API Integration](API_INTEGRATION.md) | Third-party integrations |
| [SDK Roadmap](SDK_ROADMAP.md) | Upcoming Python SDK features |
