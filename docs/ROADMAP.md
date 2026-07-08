# UDR Roadmap

## Current State (v1.4.0)

| Area | Status |
|------|--------|
| Supported ecosystems | 20 (pypi, npm, pub, crates, maven, gomodules, apt, apk, cocoapods, homebrew, nuget, packagist, rubygems, conda, gradle, swift, hex, haskell, docs, custom_db) |
| Resolution engine | Z3 SAT solver + PubGrub (pure-Python fallback) with SCC batch partitioning, CUDA-aware conflict resolution, DFS backtracking fallback, dynamic version clustering, configurable optimization threshold |
| In-place manifest update | 13/20 ecosystems — PyPI, npm, crates, maven, gomodules, apt, apk, cocoapods, homebrew, nuget, packagist, rubygems, conda have updaters; **Go, Haskell, Hex, Gradle, Swift, Pub, Homebrew cannot write back** |
| CLI commands | `lock`, `install`, `resolve`, `scan`, `update`, `graph`, `serve`, `why`, `details`, `diff`, `outdated`, `search`, `check`, `verify`, `list-ecosystems`, `completion`, `auth`, `index` |
| Lock file | `udr.lock` (supports `--workspace` for multi-workspace projects) |
| Export formats | requirements.txt, package.json, Dockerfile, docker-compose.yml, pyproject.toml, environment.yml, Cargo.toml, build.gradle, pom.xml, CMakeLists.txt, install.sh, install.bat, Gemfile, composer.json, go.mod |
| Tests | 1831 unit + 94 integration = **1925 total** (zero regressions) |
| All 21 bottlenecks | ✅ Fixed — P0×4 (wrong results), P1×4 (reliability), P2×5 (scalability), P3×8 (code quality) |
| Architecture violations | 0 (api→orchestrator→database service layer enforced) |
| Ruff violations | 0 in `backend/` |
| Missing docstrings | 221 (D100–D417) — incremental fix ongoing |

---

## High-Priority Gaps (from FAQ.md — needs contributors)

### 1. Missing Manifest Updaters
- **What**: Only 13/20 ecosystems have in-place `_update_*` functions.
- **Entry point**: `backend/cli/shared.py` — add updaters for Go (`go.mod`), Haskell (`*.cabal`), Hex/Elixir (`mix.exs`), Gradle (`build.gradle`/`.kts`), Swift (`Package.swift`), Pub (`pubspec.yaml`), Homebrew (`Brewfile`).
- **Priority**: High — manifests are the primary output surface; missing updaters mean users must manually re-write after `udr lock`.

### 2. No Cross-Compilation Targeting (`--target`/`--platform`)
- **What**: `SystemScanner` always auto-detects OS, architecture (arm64 vs amd64), Python version — no way to override. A lock file generated on macOS ARM for a Linux CUDA deploy target locks in the wrong OS/arch.
- **Partial fix**: `--cuda <ver>` + `--device <cpu/cuda/mps>` exist on 7 commands, but only override GPU info.
- **Entry point**: `backend/core/system_scanner.py` + CLI flag propagation through all command handlers.
- **Priority**: High — CI/CD workflows need to generate deploy-target lock files from developer laptops.

### 3. Offline-First Mode is Manual
- **What**: SQLite offline index (`~/.cache/udr/indexes/{eco}.db`) exists but must be explicitly built via `udr index build` or pulled via `udr index pull`. There's no "cache-as-you-go" — API responses are not automatically indexed for future offline use.
- **Partial fix**: DictCache with disk persistence + ETag conditional requests cache individual lookups, but a fresh package always requires network unless pre-indexed.
- **Entry point**: `backend/core/offline_index.py` + `DataAggregator` auto-population during online fetches.
- **Priority**: High — the `--offline` flag exists but raises `FileNotFoundError` for un-indexed packages.

### 4. Per-Ecosystem Solver Isolation
- **What**: All ecosystems share a single Z3 optimization matrix (`conflict_resolver.py:1113-1218`). A conflict in JavaScript frontend deps blocks backend Python resolution if any transitive dependency path connects them.
- **Partial mitigation**: SCC decomposition separates disconnected subgraphs, but shared transitive deps merge them back into one component.
- **Entry point**: `backend/core/conflict_resolver.py` — advanced topic; explore `s.push()/s.pop()` contexts or multi-solver architecture.
- **Priority**: Medium — affects monorepos with independent sub-projects across ecosystems.

---

## Remaining Limitations (Lower Priority)

### 5. Solver Capacity: 50000-variable limit
- **What**: `SOLVER_MAX_VARS=50000` caps total Z3 boolean variables.
- **Mitigation**: SCC batch partitioning + dynamic version clustering handle projects up to ~500 packages. PubGrub solver (pure-Python 661 lines) available via `USE_PUBGRUB_SOLVER=true`.
- **Remaining gap**: Very large monorepos (>500 packages) may still hit the limit.

### 6. Incremental / Online Resolution
- **What**: Adding or removing a single dependency triggers full BFS re-discovery.
- **Partial fix**: `resolution_hash`-based caching skips SAT solver for unchanged subtrees.
- **Remaining gap**: BFS still re-walks all dependencies even when only one root changes.

### 7. udr.lock Ecosystem Mapping
- **What**: `udr.lock` is mapped to `pypi` ecosystem in `MANIFEST_PATTERNS`, making it appear as a Python artifact rather than a universal lock file.
- **Fix**: Map to a dedicated internal ecosystem (e.g. `"udr"`).

### 8. Missing Docstrings (221)
- **What**: Ruff D rule flags 221 functions/modules missing docstrings.
- **Status**: Incremental fix — one function at a time.

---

## Phase 5 — Cross-Ecosystem Upgrade ✅ All Complete

| # | Item | Priority | Status | Notes |
|---|------|----------|--------|-------|
| 5.1 | Batch/sharded SAT solver | P0 | ✅ Done | SCC graph partitioning, topological resolution |
| 5.2 | TOML manifest updater | P0 | ✅ Done | `pyproject.toml`, `Pipfile`, `Cargo.toml` |
| 5.3 | JSON manifest updater | P0 | ✅ Done | `composer.json`, `package.json` |
| 5.4 | Ruby DSL manifest updater | P1 | ✅ Done | `Podfile`, `.gemspec`, `Gemfile`, `Brewfile` |
| 5.5 | Go module manifest updater | P1 | ✅ Done | `go.mod` with `go get` integration |
| 5.6 | Groovy/Kotlin DSL updater | P2 | ✅ Done | `build.gradle` / `build.gradle.kts` |
| 5.7 | Swift DSL updater | P2 | ✅ Done | `Package.swift` |
| 5.8 | Elixir DSL updater | P2 | ✅ Done | `mix.exs` |
| 5.9 | Cabal updater | P3 | ✅ Done | `*.cabal` |
| 5.10 | XML updater | P3 | ✅ Done | `packages.config` (nuget) |
| 5.11 | Incremental resolution | P1 | Partially done | resolution_hash caching; full incremental re-resolution pending |
| 5.12 | PubGrub solver integration | P1 | ✅ Done (pure-Python) | `backend/core/pubgrub_core.py` (661 lines) — pure-Python PubGrub with CDCL; no Rust toolchain needed. `USE_PUBGRUB_SOLVER=true` to enable. Falls back gracefully to ConflictResolver (Z3). |

## Phase 6 — Cross-Compilation & Offline (New — from FAQ priorities)

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 6.1 | `--target`/`--platform` flags | P1 | Override OS, arch, Python version for CI/CD lock file generation from dev laptops |
| 6.2 | Automatic offline index population | P1 | Cache API responses into SQLite index automatically during online use; eliminate `udr index build` requirement |
| 6.3 | Per-ecosystem solver isolation | P2 | Isolate independent ecosystems into separate solver contexts; prevent JS conflict from blocking Python resolution |

## Phase 7 — Platform & Integrations

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 7.1 | WASM frontend | P2 | Browser-based dependency analysis |
| 7.2 | Desktop app (Tauri) | P2 | Native GUI (Electron served since v1.2) |
| 7.3 | VSCode extension | P2 | In-editor manifest editing + lock integration |
| 7.4 | GitHub Actions | P2 | CI: `udr lock --check` for drift detection |
| 7.5 | GitLab CI template | P2 | Same as GitHub Actions |
| 7.6 | Pre-commit hook | P2 | `udr lock --check` before commits |

## Phase 8 — Compliance & Security

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 8.1 | License compliance | P1 | ✅ Done (`check --license`) — SPDX alias table, configurable policy |
| 8.2 | CVE scanning | P1 | ✅ Done (`check --cve`) — OSV-based, severity-colored output |
| 8.3 | CVE auto-fix | P1 | `udr update --fix-cve` to bump vulnerable deps |
| 8.4 | SBOM generation | P1 | SPDX 2.3 / CycloneDX 1.5 output |
| 8.5 | Supply chain attestation | P2 | SLSA provenance + signed lock files |
| 8.6 | Policy engine | P2 | Custom rules: "no GPL in production", "pin all transitive" |

## Phase 9 — Ecosystem Deepening

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 9.1 | Nix / Guix support | P3 | Functional package manager manifests |
| 9.2 | Vcpkg support | P3 | C/C++ package manager |
| 9.3 | Conan support | P3 | C/C++ (another) |
| 9.4 | Helm / chart support | P3 | Kubernetes manifests |
| 9.5 | Terraform provider locks | P3 | `.terraform.lock.hcl` |
| 9.6 | Dockerfile FROM parsing | P3 | Base image dependency tracking |

## Phase 10 — Developer Experience

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 10.1 | Dependency graph visualization | P2 | Web UI with interactive force-directed graph |
| 10.2 | `udr why` command | P1 | ✅ Done (`udr why <package>`) — dependency chain + constraint trace |
| 10.3 | `udr diff` command | P2 | ✅ Done (`udr diff [old] [new]` or `udr diff --workspace`) |
| 10.4 | `udr outdated` command | P2 | ✅ Done (`udr outdated --json`) |
| 10.5 | Shell completion | P2 | ✅ Done (`udr completion bash` / zsh / fish) |
| 10.6 | Man page | P3 | Unix man page for CLI reference |

## Release Milestones

| Version | Focus | Status | Target |
|---------|-------|--------|--------|
| v1.3 | All 21 bottlenecks fixed, Phase 5 complete, 0 ruff violations | ✅ Released | Q3 2026 |
| v1.4 | CVE scanning, license compliance, PubGrub pure-Python, workspace awareness, private registry auth | ✅ Released | Q3 2026 |
| v1.5 | Cross-compilation flags + offline-first auto-indexing | Pending | Q4 2026 |
| v2.0 | WASM frontend + SBOM | Pending | Q1 2027 |
| v3.0 | Policy engine + supply chain attestation + per-ecosystem isolation | Pending | Q2 2027 |
