# UDR Roadmap

## Current State (v1.0)

| Area | Status |
|------|--------|
| Supported ecosystems | 20 (pypi, npm, pub, crates, maven, gomodules, apt, apk, cocoapods, homebrew, nuget, packagist, rubygems, conda, gradle, swift, hex, haskell, docs, custom_db) |
| Resolution engine | Z3 SAT solver with CUDA-aware conflict resolution, backtracking fallback, version clustering |
| In-place manifest update | `package.json` (npm), `pubspec.yaml` (pub), line-based (`requirements.txt`, `apt-packages.txt`, `apk-packages.txt`) |
| CLI commands | `lock`, `install`, `resolve`, `scan`, `update`, `graph`, `serve` |
| Lock file | `udr.lock` |
| Export formats | requirements.txt, pip, conda, npm, json |
| Tests | 1202 unit + 10 e2e CLI + 5 e2e JSON + 14 comprehensive |

---

## Limitations (Future Scope)

### 1. Solver Capacity: 5000-variable limit
- **What**: `SOLVER_MAX_VARS=5000` caps total Z3 boolean variables. Projects with >200 packages across ecosystems may hit this limit.
- **Symptoms**: streamlit (1433 pkgs), sentry (2731 pkgs), flutter/packages (1270 pkgs) are too large for batch resolution.
- **Planned fix**: Batch/sharded resolution — resolve subgraphs independently, merge with constraint propagation.

### 2. Manifest Update Coverage
- **What**: Only 3 of 20 ecosystems have dedicated in-place manifest updaters.
- **Missing updaters**:
  | Manifest | Ecosystem | Format | Priority |
  |----------|-----------|--------|----------|
  | `Cargo.toml` | crates | TOML | High |
  | `go.mod` | gomodules | Go module | High |
  | `Gemfile` | rubygems | Ruby DSL | High |
  | `composer.json` | packagist | JSON | High |
  | `pyproject.toml` | pypi | TOML | High |
  | `build.gradle` | gradle | Groovy/Kotlin | Medium |
  | `Package.swift` | swift | Swift DSL | Medium |
  | `mix.exs` | hex | Elixir DSL | Medium |
  | `Podfile` | cocoapods | Ruby DSL | Medium |
  | `Brewfile` | homebrew | Ruby DSL | Medium |
  | `packages.config` | nuget | XML | Medium |
  | `Pipfile` | pypi | TOML | Medium |
  | `environment.yml` | conda | YAML | Low |
  | `*.cabal` | haskell | Cabal | Low |

### 3. Solver Performance for Large Projects
- **What**: The Z3-backed SAT solver works well for <200 packages but slows significantly beyond that.
- **Root cause**: Single monolithic solving — all packages and versions become boolean variables in one Z3 context.
- **Planned fix**: Dependency graph partitioning (Kosaraju SCCs) + topological resolution order.

### 4. Incremental / Online Resolution
- **What**: Adding or removing a single dependency requires a full re-resolution.
- **Planned fix**: Track resolution cache keys (package + constraint + ecosystem) and only re-resolve affected subgraphs.

### 5. go.mod Parser: Multi-line `require (...)`
- **What**: The `_parse_go_mod()` function uses simple line-by-line matching and doesn't handle multi-line `require (...)` blocks.
- **Workaround**: Single-line `require module/path vX.Y.Z` statements work fine.

### 6. _parse_cabal: Dead Code Duplication
- **What**: After the `for` loop in `_parse_cabal`, there is an unreachable duplicate of `_parse_requirements` logic (lines 403-417).

### 7. udr.lock Ecosystem Mapping
- **What**: `udr.lock` is mapped to `pypi` ecosystem in `MANIFEST_PATTERNS`, making it appear as a Python artifact rather than a universal lock file.

### 8. Architecture: api → database Import Violation
- **What**: 7 imports from `api/` to `database/` bypassing the data-access service layer.
- **Planned fix**: Introduce a service layer between API handlers and database models.

### 9. Pre-existing Test Failures (10)
- **What**: Data-source client tests (crates, homebrew, maven) have argument/response mismatches.
- **Impact**: These are test/expectation issues, not runtime bugs. All real-world tests pass.

### 10. Missing Docstrings (186)
- **What**: Ruff D rule flags 186 functions/modules missing docstrings.
- **Status**: Incremental fix — one function at a time.

---

## Phase 5 — Cross-Ecosystem Upgrade

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 5.1 | Batch/sharded SAT solver | P0 | Partition dependency graph, resolve subgraphs independently |
| 5.2 | TOML manifest updater | P0 | Shared parser for `pyproject.toml`, `Cargo.toml`, `Pipfile` |
| 5.3 | JSON manifest updater | P0 | Shared parser for `composer.json` |
| 5.4 | Ruby DSL manifest updater | P1 | Shared parser for `Gemfile`, `Podfile`, `Brewfile` |
| 5.5 | Go module manifest updater | P1 | For `go.mod` |
| 5.6 | Groovy/Kotlin DSL updater | P2 | For `build.gradle` / `build.gradle.kts` |
| 5.7 | Swift DSL updater | P2 | For `Package.swift` |
| 5.8 | Elixir DSL updater | P2 | For `mix.exs` |
| 5.9 | Cabal updater | P3 | For `*.cabal` |
| 5.10 | XML updater | P3 | For `packages.config` |
| 5.11 | Incremental resolution | P1 | Cache-based partial re-resolution |

## Phase 6 — Platform & Integrations

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 6.1 | WASM frontend | P1 | Browser-based dependency analysis |
| 6.2 | Desktop app (Tauri) | P2 | Native GUI for lock/resolve/scan workflows |
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

| Version | Focus | Target |
|---------|-------|--------|
| v1.1 | Manifest update for all 20 ecosystems + batch solver | Q3 2026 |
| v2.0 | WASM frontend + SBOM + license checking | Q4 2026 |
| v2.1 | Desktop app + VSCode extension | Q1 2027 |
| v3.0 | Policy engine + supply chain attestation | Q2 2027 |
