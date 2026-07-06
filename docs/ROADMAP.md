# UDR Roadmap

## Current State (v1.3.3)

| Area | Status |
|------|--------|
| Supported ecosystems | 20 (pypi, npm, pub, crates, maven, gomodules, apt, apk, cocoapods, homebrew, nuget, packagist, rubygems, conda, gradle, swift, hex, haskell, docs, custom_db) |
| Resolution engine | Z3 SAT solver with SCC batch partitioning, CUDA-aware conflict resolution, backtracking fallback, version clustering |
| In-place manifest update | 13/20 ecosystems: `package.json` (npm), `pubspec.yaml` (pub), `build.gradle`/`.kts` (gradle), `Package.swift` (swift), `mix.exs` (hex), `Podfile` (cocoapods), `.gemspec` (rubygems), `requirements.txt` (pypi), `apt-packages.txt` (apt), `apk-packages.txt` (apk) |
| CLI commands | `lock`, `install`, `resolve`, `scan`, `update`, `graph`, `serve`, `why`, `details`, `diff`, `outdated`, `search`, `check`, `verify`, `list-ecosystems`, `completion`, `auth`, `index` |
| Lock file | `udr.lock` |
| Export formats | requirements.txt, package.json, Dockerfile, docker-compose.yml, pyproject.toml, environment.yml, Cargo.toml, build.gradle, pom.xml, CMakeLists.txt, install.sh, install.bat, Gemfile, composer.json, go.mod |
| Tests | 1572 unit + 10 e2e CLI + 5 e2e JSON + 13 e2e problem-statement + 46 e2e edge-cases |

---

## Limitations (Future Scope)

### 1. Solver Capacity: 50000-variable limit (mitigated)
- **What**: `SOLVER_MAX_VARS=50000` caps total Z3 boolean variables.
- **Mitigation**: SCC batch partitioning resolves subgraphs independently. Projects up to ~500 packages now work reliably.
- **Remaining gap**: Very large projects (>500 packages, >50000 vars) still hit the limit.

### 2. Manifest Update Coverage (improved)
- **What**: 13/20 ecosystems now have dedicated in-place manifest updaters.
- **Missing updaters**:
  | Manifest | Ecosystem | Format | Priority |
  |----------|-----------|--------|----------|
  | `Cargo.toml` | crates | TOML | High |
  | `go.mod` | gomodules | Go module | High |
  | `Gemfile` | rubygems | Ruby DSL | High |
  | `composer.json` | packagist | JSON | High |
  | `pyproject.toml` | pypi | TOML | High |
  | `Brewfile` | homebrew | Ruby DSL | Medium |
  | `packages.config` | nuget | XML | Medium |
  | `Pipfile` | pypi | TOML | Medium |
  | `environment.yml` | conda | YAML | Low |
  | `*.cabal` | haskell | Cabal | Low |

### 3. Solver Performance for Large Projects (improved)
- **What**: SCC batch resolution addresses the monolithic solver bottleneck.
- **Root cause (fixed)**: Single monolithic solving replaced with partitioned subgraph resolution.
- **Remaining gap**: Very large graphs with deep dependency chains may still perform poorly.

### 4. Incremental / Online Resolution
- **What**: Adding or removing a single dependency requires full re-resolution.
- **Planned fix**: Track resolution cache keys and only re-resolve affected subgraphs.

### 5. go.mod Parser: Multi-line `require (...)` (fixed)
- **Status**: Fixed — `_parse_go_mod()` handles multi-line `require (...)` blocks, single-line requires, `replace`/`exclude` filtering.

### 6. _parse_cabal: Dead Code Duplication
- **What**: After the `for` loop in `_parse_cabal`, there is an unreachable duplicate of `_parse_requirements` logic.

### 7. udr.lock Ecosystem Mapping
- **What**: `udr.lock` is mapped to `pypi` ecosystem in `MANIFEST_PATTERNS`, making it appear as a Python artifact rather than a universal lock file.

### 8. Architecture: api → database Import Violation
- **What**: 7 imports from `api/` to `database/` bypassing the data-access service layer.
- **Planned fix**: Introduce a service layer between API handlers and database models.

### 9. Pre-existing Test Failures → Resolved
- **What**: All 10 pre-existing data-source test mismatches have been resolved. The only remaining e2e failure is cross-ecosystem npm API throughput (`test_02_cross_ecosystem_resolution` — 44 deps for express cause BFS >300s).

### 10. Missing Docstrings (186)
- **What**: Ruff D rule flags 186 functions/modules missing docstrings.
- **Status**: Incremental fix — one function at a time.

---

## Phase 5 — Cross-Ecosystem Upgrade

| # | Item | Priority | Status | Notes |
|---|------|----------|--------|-------|
| 5.1 | Batch/sharded SAT solver | P0 | ✅ Done | SCC graph partitioning, topological resolution |
| 5.2 | TOML manifest updater | P0 | ✅ Done | `pyproject.toml`, `Pipfile` updaters done; `Cargo.toml` pending |
| 5.3 | JSON manifest updater | P0 | ✅ Done | `composer.json`, `package.json` updaters done |
| 5.4 | Ruby DSL manifest updater | P1 | Partially done | `Podfile` + `.gemspec` done; `Gemfile`, `Brewfile` pending |
| 5.5 | Go module manifest updater | P1 | ✅ Done | `go.mod` updater with `go get` integration |
| 5.6 | Groovy/Kotlin DSL updater | P2 | ✅ Done | `build.gradle` / `build.gradle.kts` |
| 5.7 | Swift DSL updater | P2 | ✅ Done | `Package.swift` |
| 5.8 | Elixir DSL updater | P2 | ✅ Done | `mix.exs` |
| 5.9 | Cabal updater | P3 | Pending | For `*.cabal` |
| 5.10 | XML updater | P3 | Pending | For `packages.config` |
| 5.11 | Incremental resolution | P1 | Partially done | resolution_hash-based caching for unchanged packages; full incremental re-resolution pending |

## Phase 6 — Platform & Integrations

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 6.1 | WASM frontend | P1 | Browser-based dependency analysis |
| 6.2 | Desktop app (Tauri) | P2 | Native GUI (Electron served since v1.2) |
| 6.3 | VSCode extension | P2 | In-editor manifest editing + lock integration |
| 6.4 | GitHub Actions | P1 | CI: `udr lock --check` for drift detection |
| 6.5 | GitLab CI template | P2 | Same as GitHub Actions |
| 6.6 | Pre-commit hook | P2 | `udr lock --check` before commits |

## Phase 7 — Compliance & Security

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 7.1 | License compliance | P1 | Detect incompatible licenses in dependency tree |
| 7.2 | SBOM generation | P1 | SPDX 2.3 / CycloneDX 1.5 output |
| 7.3 | CVE auto-fix | P1 | `udr update --fix-cve` to bump vulnerable deps |
| 7.4 | Supply chain attestation | P2 | SLSA provenance + signed lock files |
| 7.5 | Policy engine | P2 | Custom rules: "no GPL in production", "pin all transitive" |

## Phase 8 — Ecosystem Deepening

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 8.1 | Nix / Guix support | P3 | Functional package manager manifests |
| 8.2 | Vcpkg support | P3 | C/C++ package manager |
| 8.3 | Conan support | P3 | C/C++ (another) |
| 8.4 | Helm / chart support | P3 | Kubernetes manifests |
| 8.5 | Terraform provider locks | P3 | `.terraform.lock.hcl` |
| 8.6 | Dockerfile FROM parsing | P3 | Base image dependency tracking |

## Phase 9 — Developer Experience

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 9.1 | Dependency graph visualization | P1 | Web UI with interactive force-directed graph |
| 9.2 | `udr why` command | P1 | Explain why a specific version was selected |
| 9.3 | `udr diff` command | P2 | Compare two lock files |
| 9.4 | `udr audit` command | P1 | Standalone vulnerability audit |
| 9.5 | `udr outdated` command | P2 | List packages with newer versions available |
| 9.6 | Shell completion | P2 | Bash/Zsh/fish tab completion |
| 9.7 | Man page | P3 | Unix man page for CLI reference |

## Release Milestones

| Version | Focus | Status | Target |
|---------|-------|--------|--------|
| v1.1 | Manifest update for 13/20 ecosystems + batch SCC solver | ✅ Released in v1.3.3 | Q3 2026 |
| v2.0 | WASM frontend + SBOM + license checking | Pending | Q4 2026 |
| v2.1 | Desktop app + VSCode extension | Pending | Q1 2027 |
| v3.0 | Policy engine + supply chain attestation | Pending | Q2 2027 |
