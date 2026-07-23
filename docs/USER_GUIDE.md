# User Guide

## Table of Contents

1. [Who This Is For](#1-who-this-is-for)
2. [Introduction](#2-introduction)
3. [Quick Start](#3-quick-start)
4. [Installation](#4-installation)
5. [Prerequisites](#5-prerequisites)
6. [How It Works](#6-how-it-works)
7. [Components](#7-components)
8. [CLI Usage](#8-cli-usage)
9. [API Usage](#9-api-usage)
10. [Python Library Usage](#10-python-library-usage)
11. [Desktop App](#11-desktop-app)
12. [Features in Detail](#12-features-in-detail)
13. [Deployment](#13-deployment)
14. [Troubleshooting](#14-troubleshooting)
15. [Performance](#15-performance)
16. [Where to Go Next](#16-where-to-go-next)

---

## 1. Who This Is For

| You... | The problem | What UDR does |
|---|---|---|
| 🏗️ **Run a multi-language monorepo** | pip + npm + cargo + go — each its own lock file, each its own audit tool, each its own version scheme. The same dep pinned to different versions across ecosystems? No tool catches it. | One `udr.lock` across all ecosystems. `udr lock --check` in CI catches cross-ecosystem version drift before prod. |
| 🧠 **Deploy ML models with GPU deps** | torch + CUDA toolkit + nvidia-* wheels — wrong variant means silent CPU fallback or crash. Every ML team wastes days on this. | Auto-detects CUDA version, selects correct `torch+cu121` variant. CUDA 11-vs-12 conflict rules prevent incompatible pairs. |
| 🔒 **Own supply chain compliance** | Quarterly audits = run `pip-audit` + `npm audit` + `cargo audit` + `go list -m` + `bundler-audit` separately. | `udr check --cve` against OSV across **18 ecosystems** at once. `udr sbom` for SPDX/CycloneDX. Done. |

---

## 2. Introduction

**Universal Dependency Resolver (UDR)** is a cross-ecosystem dependency resolution tool. It resolves, locks, and exports dependencies across **25 package ecosystems** (18 resolvable + 7 query-only) using an AutoSolver (profiles graph → Z3/PubGrub/Hybrid per workload) that finds compatible versions even across ecosystem boundaries.

### The problem it solves

Your project pulls in packages from everywhere — Python scripts call Node services, Docker images need both `pip` and `apt` packages, and your CI pipeline has to pin every transitive dependency across all of them.

Existing tools only work within one ecosystem. `pip-compile` handles Python. `npm ls` handles JavaScript. Cross-ecosystem conflicts go undetected until something breaks at runtime. System compatibility — GPU drivers, CUDA versions, OS patches — is never checked.

**UDR fixes that.**

---

## 3. Quick Start

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

## 4. Installation

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

## 5. Prerequisites

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

Recommended: `pip install "ud-resolver[z3,pubgrub,system]"` — see each row below for what they add.

| Extra | Adds | Used for |
|---|---|---|
| `[z3]` | z3-solver (46MB) | CUDA XOR conflict rules + cross-eco constraints. GPU filtering works without it (pre-filtered before solver). |
| `[pubgrub]` | Rust-backed PubGrub solver | Faster CDCL on 100+ package graphs. Falls back to pure-Python automatically if wheel unavailable. |
| `[system]` | psutil, py-cpuinfo, distro, gputil, nvidia-ml-py | CPU model strings, GPU temperature/utilization, per-process memory. Base install detects GPU/OS/CPU via nvidia-smi/lspci/platform — no extra needed for constraint resolution. |
| `[postgres]` | psycopg2-binary, redis, celery, aiocache | PostgreSQL + Redis + async task queue |
| `[monitoring]` | OpenTelemetry, Sentry, Prometheus | Tracing, error tracking, metrics |
| `[all]` | All extras above | Full install |

### Build tools (for compiling native extensions)

If `z3-solver` or other packages fail to compile:

| OS | Command |
|---|---|
| Ubuntu/Debian | `sudo apt-get install build-essential pkg-config python3-dev` |
| macOS | `xcode-select --install` |
| Windows | Install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) |

---

## 6. How It Works

```mermaid
sequenceDiagram
    participant User as 👤 User
    participant CLI as 🖥️ CLI
    participant Orch as 🔄 Orchestrator
    participant Agg as 📊 DataAggregator
    participant Scanner as 🔍 SystemScanner
    participant Solver as 🧠 AutoSolver (PubGrub/Z3)
    participant Export as 📤 ExportGenerator

    User->>CLI: udr resolve flask>=2.0 react@npm
    Note over CLI,Orch: Step 1 — Orchestrator fetches metadata
    CLI->>Orch: resolve(packages, system_info)
    Orch->>Agg: get_package_info("flask", "pypi")
    Agg->>Agg: Query PyPI API
    Agg-->>Orch: versions + dependencies
    Orch->>Agg: get_package_info("react", "npm")
    Agg->>Agg: Query npm registry
    Agg-->>Orch: versions + dependencies
    Note over Orch,Scanner: Step 2 — Scan target system
    Orch->>Scanner: scan_all()
    Scanner-->>Orch: OS, CPU, GPU, CUDA, runtimes
    Note over Orch,Solver: Step 3 — SAT resolution
    Orch->>Solver: resolve(packages, system_info)
    Solver->>Solver: Profile + select backend<br/>resolve constraints
    Solver-->>Orch: compatible versions
    Note over Orch,Export: Step 4 — Export / Lock
    Orch->>Export: export(packages, "requirements.txt")
    Export-->>Orch: formatted output
    Orch-->>CLI: result
    CLI-->>User: ✅ Resolution complete
```

### Step by step

1. **Metadata fetch** — Queries registry APIs (PyPI, npmjs.org, crates.io, etc.) for each package's versions, dependencies, and system requirements
2. **System scan** — Detects OS, CPU, GPU, CUDA version, Python version, Node.js, GCC, Java
3. **SAT resolution** — AutoSolver (profiles graph → Z3/PubGrub/Hybrid per workload) finds a set of mutually compatible versions across all packages and ecosystems. Handles cross-ecosystem constraints (e.g. `torch` on PyPI depending on `nvidia-cublas`). GPU-aware: selects CUDA variants when NVIDIA GPU detected
4. **Export / Lock** — Writes `udr.lock` or exports to any of 15 formats

### Architecture overview

```mermaid
graph TB
    subgraph UserLayer["👤 User Interfaces"]
        CLI["🖥️ CLI<br/><code>backend/cli/</code><br/>19 commands"]
        DESKTOP["🖥️ Desktop App<br/><code>Electron + GUI</code>"]
    end

    subgraph OrchestratorLayer["🔄 Orchestrator (shared orchestration)"]
        ORCH["<code>orchestrator/resolve.py</code><br/>BFS + SAT pipeline<br/><code>install.py scanner.py db_service.py</code>"]
    end

    subgraph APILayer["🌐 API Layer (FastAPI)"]
        API["<code>main.py</code><br/>App + middleware + routes<br/>packages · system · auth · scan · lock"]
    end

    subgraph CoreLayer["🧠 Core Logic"]
        AS["<code>auto_solver.py</code><br/>AutoSolver (profiles → Z3/PubGrub/Hybrid)"]
        CR["<code>conflict_resolver.py</code><br/>Z3 SAT solver"]
        PG["<code>pubgrub_solver.py</code><br/>PubGrub solver"]
        HY["<code>hybrid_solver.py</code><br/>PubGrub per-eco + Z3 cross-eco"]
        DA["<code>data_aggregator.py</code><br/>Async aggregation"]
        EG["<code>export_generator.py</code><br/>15 export formats"]
        SS["<code>system_scanner.py</code><br/>OS · GPU · CUDA · runtimes"]
        MD["<code>manifest_detector.py</code><br/>46+ manifest/lock patterns"]
        CACHE["<code>cache.py</code><br/>DictCache + Redis"]
    end

    subgraph DBLayer["🗄️ Database & Data Sources"]
        DS["📦 26 registered ecosystem plugins<br/>18 resolvable + 7 query-only + 2 internal"]
        DB["🗄️ SQLite (default) / PostgreSQL"]
    end

    CLI --> OrchestratorLayer
    CLI --> CoreLayer
    DESKTOP -->|"HTTP"| API
    API --> OrchestratorLayer
    OrchestratorLayer --> CoreLayer
    CoreLayer --> DS
    CoreLayer --> DB
```

---

## 7. Components

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

## 8. CLI Usage

All 19 commands support `--help` for inline usage.

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
| `sbom` | Generate SPDX/CycloneDX SBOM from lock file | `udr sbom --format spdx` |
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

### SBOM generation

Generate SPDX 2.3 or CycloneDX 1.5 Software Bill of Materials from the lock file:

```bash
udr sbom                                        # SPDX JSON to stdout
udr sbom --format cyclonedx --output sbom.json  # CycloneDX to file
```

### CI drift detection

Check if the lock file is up to date without writing (exits 0 if current, 1 if drift detected):

```bash
udr lock --check                                # CI-friendly drift check
```

### Supply chain attestation

Sign lock files with Ed25519 keys and verify signatures:

```bash
udr auth gen-key                                # generate signing key
udr lock --sign                                 # sign lock file
udr verify --signature                          # verify signature
udr lock --provenance                           # add SLSA provenance section
```

### Policy engine

Evaluate lock file against a YAML policy file (`udr-policy.yaml`):

```bash
udr check --policy                              # check policy compliance
```

Supports 10 rules: `no-deprecated`, `no-yanked`, `no-gpl`, `no-agpl`, `max-vulnerabilities`, `max-critical-vulns`, `must-pin-transitives`, `allowed-licenses`, `blocked-packages`, `require-vendor`.

### CVE auto-fix

Automatically update vulnerable packages to versions that fix known CVEs:

```bash
udr update --fix-cve                            # fix all vulnerable packages
udr update flask --fix-cve                      # fix a specific package
```

### Cross-compilation targeting

Override OS/architecture for cross-compilation resolution:

```bash
udr lock --target linux --platform x86_64       # resolve for linux/amd64
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

## 9. API Usage

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

## 10. Python Library Usage

```python
import asyncio
from backend.core.data_aggregator import DataAggregator
from backend.orchestrator import create_solver
from backend.core.system_scanner import SystemScanner

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

## 11. Desktop App

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

## 12. Features in Detail

### 25 supported ecosystems (18 resolvable + 7 query-only + 2 internal)

| Ecosystem | Language | Registry | Client | Capability |
|---|---|---|---|---|
| PyPI | Python | pypi.org | `pypi_client.py` | resolvable |
| npm | JavaScript/TypeScript | registry.npmjs.org | `npm_client.py` | resolvable |
| Conda | Python/Multi | anaconda.org | `conda_client.py` | resolvable |
| Maven | Java | repo1.maven.org | `maven_client.py` | resolvable |
| Crates.io | Rust | crates.io | `crates_client.py` | resolvable |
| Go Modules | Go | proxy.golang.org | `gomodules_client.py` | resolvable |
| NuGet | C#/.NET | api.nuget.org | `nuget_client.py` | resolvable |
| RubyGems | Ruby | rubygems.org | `rubygems_client.py` | resolvable |
| Packagist | PHP | packagist.org | `packagist_client.py` | resolvable |
| Homebrew | System | formulae.brew.sh | `homebrew_client.py` | resolvable |
| CocoaPods | Swift/ObjC | trunk.cocoapods.org | `cocoapods_client.py` | resolvable |
| APT | Debian/Ubuntu | deb.debian.org | `apt_client.py` | resolvable |
| APK | Alpine | dl-cdn.alpinelinux.org | `apk_client.py` | resolvable |
| Pub | Dart/Flutter | pub.dev | `pub_client.py` | resolvable |
| Gradle | Java/Kotlin | plugins.gradle.org | `gradle_client.py` | resolvable |
| Swift | Swift | swiftpackageindex.com | `swift_client.py` | resolvable |
| Hex | Elixir | hex.pm | `hex_client.py` | resolvable |
| Haskell | Haskell | hackage.haskell.org | `haskell_client.py` | resolvable |
| Nix | NixOS | nixpkgs / GitHub | `nix_plugin.py` | query-only |
| GNU Guix | Guix | guix upstream | `guix_plugin.py` | query-only |
| Vcpkg | C/C++ | vcpkg.io | `vcpkg_plugin.py` | query-only |
| Conan | C/C++ | conan.io | `conan_plugin.py` | query-only |
| Docker | Containers | Docker Hub | `docker_plugin.py` | query-only |
| Helm | Kubernetes | artifacthub.io | `helm_plugin.py` | query-only |
| Terraform | Infrastructure | registry.terraform.io | `terraform_plugin.py` | query-only |

### SAT-solver resolution

Uses **AutoSolver** (default — profiles the dependency graph and selects Z3/PubGrub/Hybrid per workload). Use `USE_PUBGRUB_SOLVER=true` to force PubGrub, `USE_Z3_SOLVER=true` to force Z3, or `USE_HYBRID_SOLVER=true` for PubGrub per-ecosystem + Z3 cross-ecosystem:
- **Per-ecosystem solver isolation**: packages grouped by ecosystem and resolved independently — a conflict in npm can't block PyPI
- Cross-ecosystem dependencies use a unified resolution path
- Handles complex cross-ecosystem version constraints
- Detects and reports conflicts with specific error messages
- Configurable timeout via `SOLVER_TIMEOUT` env var (default: 120s)
- Falls back to backtracking search when solver times out
- `SOLVER_MAX_VARIABLES` cap (default 50000) prevents runaway solver on large graphs

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
- Lock file signing (Ed25519) with auto-generated key pairs
- SLSA provenance tracking for supply chain integrity

---

## 13. Deployment

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

## 14. Troubleshooting

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

## 15. Performance

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

## 16. Where to Go Next

| Resource | What it covers |
|---|---|
| [CLI Reference](CLI.md) | Every command with flags and examples |
| [API Reference](API.md) | 54 REST endpoints with request/response schemas |
| [Architecture](ARCHITECTURE.md) | Codebase structure, layers, design decisions |
| [Components](COMPONENTS.md) | CLI vs Desktop vs Library comparison |
| [Development](DEVELOPMENT.md) | Setup, testing, project structure |
| [Deployment](DEPLOYMENT.md) | Production deployment guide |
| [Performance](PERFORMANCE.md) | SAT solver benchmarks, optimization tips |
| [Desktop](DESKTOP.md) | Desktop app build and usage |
| [Troubleshooting](TROUBLESHOOTING.md) | Common issues and solutions |
| [API Integration](API_INTEGRATION.md) | Third-party integrations |
| [SDK Roadmap](SDK_ROADMAP.md) | Upcoming Python SDK features |
