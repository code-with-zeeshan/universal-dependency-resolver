# Architecture

```mermaid
graph TB
    subgraph UserLayer["👤 User Interfaces"]
        CLI["🖥️ CLI<br/><code>backend/cli/</code><br/>19 commands"]:::cli
        DESKTOP["🖥️ Desktop App<br/><code>Electron + GUI</code><br/>Standalone binary"]:::desktop
    end

    subgraph APILayer["🌐 API Layer (FastAPI)"]
        API_MAIN["<code>main.py</code><br/>App factory + middleware"]:::api
        ROUTES["<code>routes/</code><br/>packages · system · auth<br/>scan · lock"]:::api
        SCHEMAS["<code>schemas.py</code><br/>Pydantic request/response"]:::api
    end

    subgraph OrchestratorLayer["🔄 Orchestrator"]
        ORCH["<code>orchestrator/resolve.py</code><br/>BFS + SAT pipeline"]:::api
    end

    subgraph CoreLayer["🧠 Core Logic"]
        CR["<code>conflict_resolver.py</code><br/>Z3 SAT solver (fallback)"]:::core
        PG["<code>pubgrub_solver.py</code><br/>PubGrub solver (default, Rust-backed)"]:::core
        DA["<code>data_aggregator.py</code><br/>Async metadata aggregation"]:::core
        EG["<code>export_generator.py</code><br/>15 export formats (Jinja2)"]:::core
        SS["<code>system_scanner.py</code><br/>OS · CPU · GPU · CUDA · runtimes · accelerators"]:::core
        MD["<code>manifest_detector.py</code><br/>47+ manifest/lock patterns"]:::core
        CACHE["<code>cache.py</code><br/>DictCache + Redis"]:::core
    end

    subgraph DataLayer["📦 Data Sources"]
        DS_CLIENTS["<code>data_sources/</code><br/>22 ecosystem plugins"]:::data
        PYPI["PyPI"]:::data
        NPM["npm"]:::data
        CRATES["Crates.io"]:::data
        MAVEN["Maven"]:::data
        MORE["+ 15 more (plugin system)"]:::data
    end

    subgraph DBLayer["🗄️ Database"]
        MODELS["<code>models.py</code><br/>SQLAlchemy ORM"]:::db
        SQLITE["SQLite"]:::db
        PG["PostgreSQL"]:::db
    end

    CLI -->|"subprocess"| DESKTOP
    DESKTOP -->|"HTTP localhost"| API_MAIN
    CLI -->|"inline call"| API_MAIN
    CLI -->|"direct import"| CoreLayer
    API_MAIN --> ROUTES
    ROUTES --> SCHEMAS
    CLI -->|"direct import"| OrchestratorLayer
    ROUTES --> OrchestratorLayer
    OrchestratorLayer --> CoreLayer
    CoreLayer --> DataLayer
    CoreLayer --> DBLayer
    DS_CLIENTS -.-> PYPI
    DS_CLIENTS -.-> NPM
    DS_CLIENTS -.-> CRATES
    DS_CLIENTS -.-> MAVEN
    DS_CLIENTS -.-> MORE
    MODELS --> SQLITE
    MODELS -.->|"optional"| PG

    classDef cli fill:#2e7d32,color:#fff,stroke:#1b5e20,stroke-width:2px
    classDef desktop fill:#e65100,color:#fff,stroke:#bf360c,stroke-width:2px
    classDef api fill:#1565c0,color:#fff,stroke:#0d47a1,stroke-width:2px
    classDef core fill:#6a1b9a,color:#fff,stroke:#4a148c,stroke-width:2px
    classDef data fill:#c62828,color:#fff,stroke:#b71c1c,stroke-width:2px
    classDef db fill:#00695c,color:#fff,stroke:#004d40,stroke-width:2px
```

## Layer breakdown

### CLI layer (`backend/cli/`)

Modular CLI package with 22 files across 19 commands:

```
backend/cli/
├── __init__.py        # Re-exports all symbols for backward compat
├── main.py            # _build_parser(), main(), dispatch dict
├── shared.py          # 20+ shared helpers (parse, resolve, output, …)
└── commands/
    ├── serve.py       # cmd_serve — start API server
    ├── check.py       # cmd_check — system compatibility
    ├── resolve.py     # cmd_resolve — resolve package deps
    ├── info.py        # cmd_info — system overview
    ├── lock.py        # cmd_lock — manifest → lock file
    ├── graph.py       # cmd_graph — dependency tree
    ├── verify.py      # cmd_verify — validate lock file
    ├── scan.py        # cmd_scan — GitHub/local scan
    ├── update.py      # cmd_update — re-resolve single package
    ├── install.py     # cmd_install, cmd_restore — restore from lock
    ├── list_ecosystems.py  # cmd_list_ecosystems
    ├── auth.py        # cmd_auth — API key management
    ├── completion.py  # cmd_completion — shell completion
    ├── why.py         # cmd_why — explain version selection
    ├── outdated.py    # cmd_outdated — show outdated packages
    ├── diff.py        # cmd_diff — compare lock files
    ├── search.py      # cmd_search — search packages
    ├── sbom.py        # cmd_sbom — SBOM generation (SPDX/CycloneDX)
    └── details.py     # cmd_details — package details
```

The old monolithic `backend/cli.py` (2105 lines) was replaced by this package. A 3-line backward-compat shim remains at `backend/cli.py` for existing imports.

### API layer (`backend/api/`)

Entry point: `api/main.py` — creates the FastAPI app, registers middleware and routes.

- **Auth** (`api/auth.py`) — JWT + API key authentication. Only registered when `ENABLE_AUTH=true` (default).
- **Middleware** (`api/middleware.py`) — request ID, CORS, security headers, rate limiting, request size limits, correlation ID, response time.
- **Schemas** (`api/schemas.py`) — Pydantic request/response models.
- **Dependencies** (`api/dependencies.py`) — FastAPI dependency injection (database session, data aggregator, resolver, scanner).

Routes:

| Path prefix | File | Endpoints |
|---|---|---|
| `/api/v1/packages` | `packages.py` | Search, info, details, versions, dependencies, compatibility, resolve, export, export-formats, ecosystems |
| `/api/v1/system` | `system.py` | Info, check-compatibility |
| `/api/v1/auth` | `auth.py` | Register, login, logout, token, refresh, profile, api-keys, verify |
| `/api/v1/scan` | `scan.py` | GitHub repo, upload archive, local directory |
| `/api/v1` | `lock.py` | Verify, graph, update |

### Core logic (`backend/core/`)

- **`conflict_resolver.py`** — Z3 SAT solver (fallback). Lazy-loaded `z3` inside methods. SCC batch partitioning, dynamic version clustering, configurable optimization threshold.
- **`pubgrub_solver.py`** — PubGrub solver (default, Rust-backed `pubgrub-py` when installed; pure-Python fallback).
- **`hybrid_solver.py`** — Hybrid solver (PubGrub per-ecosystem + Z3 cross-ecosystem). Enabled via `USE_HYBRID_SOLVER=true`.
- **`plugin.py`** — Ecosystem plugin system: `EcosystemPlugin` ABC, `@register_ecosystem` decorator, `import_builtin_plugins()` for eager discovery. All 22 ecosystems use the plugin interface.
- **`data_aggregator.py`** — Aggregates package data from all ecosystem clients. Uses `asyncio.gather` for concurrent fetching with BFS batch parallelism and configurable `BFS_BATCH_SIZE`.
- **`orchestrator/resolve.py`** — BFS + SAT pipeline: `_group_by_ecosystem()` splits packages into per-ecosystem groups for **per-ecosystem solver isolation** (a conflict in npm can't block PyPI). Cross-ecosystem deps use a unified path. `create_solver()` factory selects PubGrub (default), Hybrid (`USE_HYBRID_SOLVER=true`), or Z3 fallback.
- **`export_generator.py`** — Jinja2 template-based export. 15 formats using `.j2` templates.
- **`system_scanner.py`** — Detects OS, CPU, GPU, CUDA, Python, Node.js, GCC, Java. Results cached with 5-min TTL.
- **`cache.py`** — `DictCache` (in-memory dict + TTL, no dependencies) with optional Redis fallback.
- **`manifest_detector.py`** — Scans project directories for 20+ manifest formats (requirements.txt, package.json, Cargo.toml, etc.)

### Data sources (`backend/data_sources/`)

All 22 ecosystem plugins (registered via `@register_ecosystem`), each an `EcosystemPlugin` subclass inheriting from `BaseClient`:

| Client | Ecosystem | Registry |
|---|---|---|
| `pypi_client.py` | PyPI | pypi.org |
| `npm_client.py` | npm | registry.npmjs.org |
| `conda_client.py` | Conda | repo.anaconda.com / conda-forge |
| `maven_client.py` | Maven | repo1.maven.org |
| `crates_client.py` | Crates.io | crates.io |
| `gomodules_client.py` | Go Modules | proxy.golang.org |
| `nuget_client.py` | NuGet | api.nuget.org |
| `rubygems_client.py` | RubyGems | rubygems.org |
| `packagist_client.py` | Packagist (PHP) | packagist.org |
| `homebrew_client.py` | Homebrew | formulae.brew.sh |
| `cocoapods_client.py` | CocoaPods | trunk.cocoapods.org |
| `apt_client.py` | APT (Debian) | deb.debian.org |
| `apk_client.py` | APK (Alpine) | dl-cdn.alpinelinux.org |
| `pub_client.py` | Pub (Dart/Flutter) | pub.dev |
| `gradle_client.py` | Gradle | plugins.gradle.org |
| `swift_client.py` | Swift | swiftpackageindex.com |
| `hex_client.py` | Hex (Elixir) | hex.pm |
| `haskell_client.py` | Haskell (Cabal) | hackage.haskell.org |
| `nix_plugin.py` | Nix | Nixpkgs / GitHub |
| `guix_plugin.py` | GNU Guix | Guix upstream |

All ecosystems use the **plugin system** (`backend/core/plugin.py`). Built-in plugins are eagerly discovered via `import_builtin_plugins()` — third-party plugins (installed via pip) are discoverable via setuptools entry points.

### Database (`backend/database/`)

- **`models.py`** — SQLAlchemy ORM models (8 tables, see ER diagram below). SQLite by default, PostgreSQL optional.
- **`compatibility_db.py`** — Compatibility matrix operations (CRUD for packages, reports, conflicts, benchmarks, cache).

## Import architecture rules

The codebase enforces strict import layering. Arrows show allowed dependency directions:

```mermaid
graph LR
    subgraph Layers["📐 Import Architecture"]
        CLI["<b>cli/</b>"]:::cliLayer
        API["<b>api/</b>"]:::apiLayer
        ORCH["<b>orchestrator/</b>"]:::orchLayer
        CORE["<b>core/</b>"]:::coreLayer
        DS["<b>data_sources/</b>"]:::dsLayer
        DB["<b>database/</b>"]:::dbLayer
        SETTINGS["<b>settings/</b>"]:::infra
        UTILS["<b>utils/</b>"]:::infra
    end

    CLI --> ORCH
    API --> ORCH
    ORCH --> CORE
    ORCH --> DS
    CORE --> SETTINGS
    CORE --> UTILS
    DB --> CORE
    DS --> CORE

    CLI -.->|"❌ NO"| API
    API -.->|"❌ NO"| CLI
    CLI -.->|"❌ NO"| DB
    API -.->|"❌ NO"| DS

    classDef cliLayer fill:#2e7d32,color:#fff,stroke:#1b5e20,stroke-width:2px
    classDef apiLayer fill:#1565c0,color:#fff,stroke:#0d47a1,stroke-width:2px
    classDef orchLayer fill:#e65100,color:#fff,stroke:#bf360c,stroke-width:2px
    classDef coreLayer fill:#6a1b9a,color:#fff,stroke:#4a148c,stroke-width:2px
    classDef dsLayer fill:#c62828,color:#fff,stroke:#b71c1c,stroke-width:2px
    classDef dbLayer fill:#00695c,color:#fff,stroke:#004d40,stroke-width:2px
    classDef infra fill:#424242,color:#fff,stroke:#212121,stroke-width:2px
```

| Violation | Count | Status |
|---|---|---|
| `api/ → cli/` | 0 | **Fixed** — switched to `orchestrator/` |
| `cli/ → api/` | 0 | **Fixed** — `download_github_repo` moved to `core/utils.py` |
| `api/ → database/` | 7 | Should fix — needs data-access service layer |
| `data_sources/ → core/` | 50+ | **Accepted** — core utilities are natural dependency |
| `database/ → core/` | 6 | **Accepted** — DB uses version parsing from core |
| `cli/commands/serve.py → api/` | 1 | **Accepted** — serve wraps FastAPI app; deployment concern |
| `manifest_detector.py → core/` | 1 | **Accepted** — utility import |
| `backend/__init__.py → core/` | 4 | **Accepted** — public API re-exports |
| `cli.py → cli/` | 3 | **Accepted** — entry point shim |
| `run.py → api/` | 1 | **Accepted** — entry point |

## Key design decisions

- **Lazy loading**: `import z3` inside methods (not at module level), 22 ecosystem plugins via `@register_ecosystem` + `import_builtin_plugins()`. Saves ~1s on every CLI command that doesn't need resolution.
- **SQLite first**: No PostgreSQL or Redis required. SQLite + DictCache work for all standalone/desktop use cases.
- **Auth conditionally registered**: `ENABLE_AUTH=true` by default. Auth router only mounted when enabled.
- **Settings trimmed**: ~200 lines of core settings. Removed Celery, email, webhooks, monitoring, rate-limit-for-each-endpoint, and other server-only configs.
- **No Docker**: Tool ships as `pip install ud-resolver` and as a desktop app. Docker export templates (Dockerfile.j2, docker-compose.yml.j2) are user-facing features for exporting resolved dependencies.
- **Architecture rules enforced**: CI + pre-commit hooks verify no `api/ → cli/` or `cli/ → api/` imports. Coverage threshold `fail_under = 60` enforced in CI.

## Testing

```
tests/
├── unit/         → 2407 tests (CLI, API, core, data sources, settings, Hypothesis fuzz)
├── integration/  → 96 tests (API + DB + data flow, uses SQLite)
├── e2e/          → 74 tests (CLI black-box, problem-statement, JSON compliance)
│   conftest.py   → SQLite fallback, optional Redis
└── conftest.py   → shared fixtures
```

Integration tests default to SQLite (no PostgreSQL needed). Tests use `_patch_engine` to substitute the production database engine with the test engine.

## Data model (ER diagram)

```mermaid
erDiagram
    Package ||--o{ PackageVersion : has
    Package ||--o{ CompatibilityReport : has
    Package ||--o{ ConflictRule : "conflicts as pkg1"
    Package ||--o{ ConflictRule : "conflicts as pkg2"
    User ||--o{ APIKey : owns
    User ||--o{ CompatibilityReport : submits

    Package {
        int id PK
        string name UK
        string ecosystem UK
        string latest_version
        text description
        string homepage
        string repository
        string license
        datetime created_at
        datetime updated_at
    }

    PackageVersion {
        int id PK
        int package_id FK
        string version UK
        datetime release_date
        string python_requires
        int size_bytes
        int download_count
        json system_requirements
        json dependencies
        json metadata_json
        datetime created_at
    }

    CompatibilityReport {
        int id PK
        int package_id FK
        string version
        string os_name
        string os_version
        string cpu_architecture
        string gpu_name
        string cuda_version
        string cudnn_version
        string python_version
        json system_info
        bool works
        text notes
        string user_id
        datetime created_at
    }

    ConflictRule {
        int id PK
        int package1_id FK
        string package1_version_spec
        int package2_id FK
        string package2_version_spec
        string conflict_type
        text description
        string severity
        text resolution
        datetime created_at
        bool verified
    }

    VerifiedCombination {
        int id PK
        string name
        text description
        json packages
        json system_requirements
        string verified_by
        datetime verification_date
        json test_results
        int usage_count
        float success_rate
        datetime created_at
        datetime updated_at
    }

    SystemBenchmark {
        int id PK
        string system_hash UK
        string os_name
        string os_version
        string cpu_model
        int cpu_cores
        float ram_gb
        string gpu_model
        float gpu_memory_gb
        json system_info
        json benchmarks
        datetime created_at
    }

    ResolutionCache {
        int id PK
        string request_hash UK
        json packages
        json system_info
        json constraints
        json resolution
        int resolution_time_ms
        bool success
        int hit_count
        datetime created_at
        datetime expires_at
    }

    User {
        int id PK
        string username UK
        string email UK
        string hashed_password
        string full_name
        bool is_active
        bool is_superuser
        json scopes
        datetime created_at
        datetime updated_at
        datetime last_login
    }

    APIKey {
        int id PK
        string key UK
        string name
        text description
        int user_id FK
        json scopes
        bool is_active
        datetime expires_at
        datetime last_used_at
        int usage_count
        datetime created_at
        datetime revoked_at
    }
```

**9 tables** across 4 domains:

| Domain | Tables | Purpose |
|---|---|---|
| 📦 **Package data** | `packages`, `package_versions` | Registry metadata for resolved packages |
| 🧪 **Compatibility** | `compatibility_reports`, `conflict_rules`, `verified_combinations` | Known-working combinations and conflicts |
| ⚡ **Infrastructure** | `system_benchmarks`, `resolution_cache` | Performance data and cached resolutions |
| 👤 **Auth** | `users`, `api_keys` | Authentication and API key management |
