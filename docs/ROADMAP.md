# UDR Roadmap

## Current State (v4.0.0)

| Area | Status |
|------|--------|
| Supported ecosystems | 27 (pypi, npm, pub, crates, maven, gomodules, apt, apk, cocoapods, homebrew, nuget, packagist, rubygems, conda, gradle, swift, hex, haskell, vcpkg, conan, docker, helm, terraform, nix, guix, docs, custom_db) |
| Resolution engine | PubGrub SAT solver (Rust-backed, default) + Z3 fallback (`USE_Z3_SOLVER=true`) with SCC batch partitioning, CUDA-aware conflict resolution, DFS backtracking fallback, dynamic version clustering, configurable optimization threshold |
| In-place manifest update | **18/18 resolvable ecosystems** — all ecosystems with local manifests can be written back after `udr lock` |
| CLI commands | `lock`, `install`, `resolve`, `scan`, `update`, `graph`, `serve`, `why`, `details`, `diff`, `outdated`, `search`, `check`, `verify`, `list-ecosystems`, `completion`, `auth`, `index`, `sbom` |
| Lock file | `udr.lock` (supports `--workspace` for multi-workspace projects) |
| Export formats | requirements.txt, package.json, Dockerfile, docker-compose.yml, pyproject.toml, environment.yml, Cargo.toml, build.gradle, pom.xml, CMakeLists.txt, install.sh, install.bat, Gemfile, composer.json, go.mod |
| Dependency graph visualization | Interactive D3.js force-directed graph in WASM frontend (`#graph` page) |
| Tests | 2514 unit + 94 integration = **2608 total** (zero regressions) |
| All 21 bottlenecks | ✅ Fixed — P0×4 (wrong results), P1×4 (reliability), P2×5 (scalability), P3×8 (code quality) |
| Architecture violations | 0 — enforced via CI + pre-commit |
| Ruff violations | 0 in `backend/` |
| Coverage threshold | 60% (`fail_under = 60`) — enforced via CI + pre-commit |
| Missing docstrings | 221 (D100–D417) — incremental fix ongoing |

---

## High-Priority Gaps (from FAQ.md — needs contributors)

### 1. Missing Manifest Updaters — ✅ Complete
- **What**: **18/18 ecosystems** now have in-place `_update_*` functions (go.mod, cabal, mix.exs, build.gradle, Package.swift, pubspec.yaml, Brewfile, apt-packages.txt, apk-packages.txt, pom.xml, and all prior).
- **Status**: All resolvable ecosystems are writable. Removed from high-priority gap list.

### 2. Cross-Compilation Targeting (`--target`/`--platform`) — ✅ Complete
- **What**: `--target` (linux/windows/darwin) + `--platform` (x86_64/aarch64/arm64/i386/amd64) flags on `lock`, `install`, `update`, `resolve`. Override OS/arch before resolution. Target info stored in lock file's `target` section alongside host system info.
- **Env overrides**: `TARGET_OS`, `TARGET_ARCH`, `TARGET_CUDA` settings for CI-driven cross-compilation.
- **Status**: Implemented. Removed from high-priority gap list.

### 3. Offline-First Mode — Auto-Population ✅
- **What**: `_auto_index_package` in `DataAggregator` caches every API response into the SQLite offline index automatically during normal fetches. No explicit `udr index build` needed for previously-seen packages.
- **Remaining gap**: First-time packages still require network (no proactive index sync).
- **Status**: Auto-population implemented. Manual `udr index sync` still available for pre-seeding.

### 4. Per-Ecosystem Solver Isolation — ✅ Complete
- **What**: All ecosystems share a single Z3 optimization matrix (`conflict_resolver.py:1113-1218`). A conflict in JavaScript frontend deps blocks backend Python resolution if any transitive dependency path connects them.
- **Fix**: `_group_by_ecosystem()` splits packages into single-ecosystem groups; each group resolves independently in isolated solver contexts. Cross-ecosystem packages (with cross-ecosystem deps) still use unified path.
- **Status**: Implemented. Removed from high-priority gap list.

---

## Remaining Limitations (Lower Priority)

### 5. Solver Capacity: 50000-variable limit
- **What**: `SOLVER_MAX_VARS=50000` caps total Z3 boolean variables.
- **Mitigation**: PubGrub (default, Rust-backed) handles 200+ packages in synthetic tests. SCC batch partitioning + dynamic version clustering handle larger projects. Z3 fallback via `USE_Z3_SOLVER=true`.
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
| 5.10 | XML updater | P3 | ✅ Done | `packages.config` (nuget), `pom.xml` (maven) |
| 5.11 | Simple text updater | P3 | ✅ Done | `apt-packages.txt`, `apk-packages.txt` |
| 5.12 | Incremental resolution | P1 | ✅ Done | resolution_hash per package; BFS + SAT skip for unchanged subtrees; per-transitive-dep hash comparison |
| 5.13 | PubGrub solver integration | P1 | ✅ Done (Rust-backed, default) | `backend/core/pubgrub_solver.py` — Rust-backed `pubgrub-py` when installed; pure-Python fallback. **Default solver** — no env var needed. `USE_Z3_SOLVER=true` to force Z3. |

## Phase 6 — Cross-Compilation & Offline (New — from FAQ priorities)

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 6.1 | `--target`/`--platform` flags | P1 | Override OS, arch, Python version for CI/CD lock file generation from dev laptops |
| 6.2 | Automatic offline index population | P1 | Cache API responses into SQLite index automatically during online use; eliminate `udr index build` requirement |
| 6.3 | Per-ecosystem solver isolation | P2 | ✅ Done — `_group_by_ecosystem()`, isolated per-eco solver contexts |

## Phase 7 — Platform & Integrations

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 7.1 | WASM frontend | P2 | Browser-based dependency analysis |
| 7.2 | Desktop app (Tauri) | P2 | Native GUI (Electron served since v1.2) |
| 7.3 | VSCode extension | P2 | In-editor manifest editing + lock integration |
| 7.4 | GitHub Actions | P2 | ✅ Done — `udr lock --check` for drift detection, `.github/workflows/lock-check.yml` |
| 7.5 | GitLab CI template | P2 | Same as GitHub Actions |
| 7.6 | Pre-commit hook | P2 | `udr lock --check` before commits |

## Phase 8 — Compliance & Security

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 8.1 | License compliance | P1 | ✅ Done (`check --license`) — SPDX alias table, configurable policy |
| 8.2 | CVE scanning | P1 | ✅ Done (`check --cve`) — OSV-based, severity-colored output |
| 8.3 | CVE auto-fix | P1 | ✅ Done — `udr update --fix-cve` to bump vulnerable deps |
| 8.4 | SBOM generation | P1 | ✅ Done — `udr sbom` SPDX 2.3 / CycloneDX 1.5 output |
| 8.5 | Supply chain attestation | P2 | ✅ Done — `udr lock --sign`, `udr verify --signature`, SLSA provenance |
| 8.6 | Policy engine | P2 | ✅ Done — `udr check --policy`, YAML-based rules |

## Phase 9 — Ecosystem Deepening ✅ All Complete

| # | Item | Priority | Status | Notes |
|---|------|----------|--------|-------|
| 9.1 | Nix / Guix support | P3 | ✅ Done | Functional package manager manifests — `default.nix`/`flake.nix`/`flake.lock` + `guix.scm`/`manifest.scm` |
| 9.2 | Vcpkg support | P3 | ✅ Done | C/C++ package manager |
| 9.3 | Conan support | P3 | ✅ Done | C/C++ (another) |
| 9.4 | Helm / chart support | P3 | ✅ Done | Kubernetes manifests |
| 9.5 | Terraform provider locks | P3 | ✅ Done | `.terraform.lock.hcl` |
| 9.6 | Dockerfile FROM parsing | P3 | ✅ Done | Base image dependency tracking |

All Phase 9 items complete — **27 ecosystems total**.

## Phase 10 — Developer Experience

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 10.1 | Dependency graph visualization | P2 | ✅ Done | Interactive D3.js force-directed graph in WASM frontend (`#graph` page) |
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
| v1.5 | Cross-compilation flags + offline-first auto-indexing + per-ecosystem solver isolation | ✅ Released | Q4 2026 |
| v2.0 | CVE auto-fix + SBOM generation + GitHub Actions CI drift check | ✅ Released | Q1 2027 |
| v3.0 | Policy engine + supply chain attestation + signed lock files | ✅ Released | Q2 2027 |
| v4.0 | WASM frontend + Desktop app (Tauri) + VSCode extension | ✅ Released | Q3 2027 |
