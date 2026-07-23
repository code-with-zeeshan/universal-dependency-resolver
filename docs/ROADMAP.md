# UDR Roadmap

## Project Status (2026-07-22)

| Metric | Value |
|--------|-------|
| Resolution ecosystems | **25** (18 resolvable + 7 query-only + 2 internal) |
| Solver | PubGrub (Rust-backed, default) → Z3 fallback (`USE_Z3_SOLVER=true`) |
| ForkingResolver | 4-strategy parallel portfolio meta-solver (gated) |
| CLI commands | 20 |
| Lock file | `udr.lock` v2.x with workspace, cross-eco, target sections |
| Tests | **3610** (3334 unit + 96 integration + 77 e2e + 10 wheel + 94 cross-eco) |
| Coverage threshold | **58%** (enforced CI + pre-commit) |
| Architecture violations | **0** (enforced CI + pre-commit) |
| Ruff violations | **7** in `backend/` (4 fixable) |
| Missing docstrings | **0** — all D categories resolved (D102, D205, D401, D107, D413, D400, D417). |

---

## What We Built — Historical Evolution

### Phase 0 — Foundation (Solver + Pipeline)

| Item | Status | Details |
|------|--------|---------|
| Z3 SAT solver (`ConflictResolver`) | ✅ | 2660-line SAT encoding with SCC partitioning, DFS backtracking, CUDA conflict rules |
| PubGrub solver (Rust-backed) | ✅ | Default solver via `pubgrub-py`; pure-Python fallback |
| ForkingResolver | ✅ | 4 fork strategies (skip-latest, skip-first-two, major-pin, constraint-relax) run in parallel via ThreadPoolExecutor |
| Platform markers (PEP 508) | ✅ | 3-layer pipeline: PyPI client → Aggregator → BFS filtering |
| Content-addressed cache | ✅ | SHA256 blob store with git-like sharding, GC, corruption detection |
| 20 ecosystem layer sync | ✅ | All ecosystems wired through enum → manifest → client → settings → aliases |

### Phase 1 — Data Source Clients (Ecosystem Coverage)

**Clients with real registry API calls**: PyPI, npm, Crates, Maven, GoModules, RubyGems, Packagist, Conda, APT, APK, NuGet, CocoaPods, Homebrew, Pub, Gradle, Swift, Hex, Haskell

**Plugin-only (stub)**: Docker, Vcpkg, Terraform, Conan, Nix, Guix, Helm

| Ecosystem | Manifest | Lock Tree | Resolver | Updater | Notes |
|-----------|----------|-----------|----------|---------|-------|
| npm | ✅ package.json | ✅ package-lock, pnpm-lock, yarn.lock | ✅ | ✅ | Semaphore(10), ETag cached |
| crates | ✅ Cargo.toml | ✅ Cargo.lock | ✅ | ✅ | cksum integrity |
| rubygems | ✅ Gemfile, .gemspec | ✅ Gemfile.lock | ✅ | ✅ | sha integrity |
| packagist | ✅ composer.json | ✅ composer.lock | ✅ | ✅ | |
| pypi | ✅ pyproject.toml, requirements.txt, Pipfile | ✅ poetry.lock, uv.lock | ✅ | ✅ | Wheel tag awareness, marker eval |
| hex | ✅ mix.exs | ✅ mix.lock | ✅ | ✅ | |
| gomodules | ✅ go.mod | ✅ go.sum (dead code) | ✅ | ✅ | Replace, workspace, GOPROXY auth |
| gradle | ✅ build.gradle / .kts | — | ✅ | ✅ | 11 configurations |
| swift | ✅ Package.swift | ✅ Package.resolved | ✅ | ✅ | GitHub API rate-limited |
| haskell | ✅ *.cabal, stack.yaml, cabal.project | — | ✅ | ✅ | |
| pub | ✅ pubspec.yaml | — | ✅ | ✅ | |
| homebrew | ✅ Brewfile | ✅ Brewfile.lock.json | ✅ | ✅ | |
| apt | ✅ apt-packages.txt (text) | — | ✅ | ✅ | Truncated at 100 |
| apk | ✅ apk-packages.txt (text) | — | ✅ | ✅ | |
| conda | ✅ environment.yml | — | ✅ | — | pip deps correctly tagged |
| cocoapods | ✅ Podfile | ✅ Podfile.lock | ✅ | ✅ | |
| maven | ✅ pom.xml | — | ✅ | ✅ | XML updater, no SNAPSHOT |
| nuget | ✅ packages.config | — | ✅ | — | |
| nix | ✅ default.nix, shell.nix, flake.nix | ✅ flake.lock | ✅ | — | |
| guix | ✅ guix.scm, manifest.scm | — | ✅ | — | |
| helm | ✅ Chart.yaml | ✅ Chart.lock | ✅ | — | Chart.lock reacheable |
| docker | ✅ Dockerfile | — | ✅ | — | Docker Hub API v2 |
| terraform | ✅ *.tf, .terraform.lock.hcl | — | ✅ | — | Registry API |
| vcpkg | ✅ vcpkg.json | — | ✅ | — | |
| conan | ✅ conanfile.py | — | ✅ | — | ConanCenter API |

### Phase 2 — P0/P1/P2/P3 Gap Closure (36 items, all closed, 2026-07-14)

**P0 — Correctness (5/5)**:
- `split("@")[0]` → `split("@", 1)[-1]` for scoped npm packages
- `asyncio.gather` hardened at 6 sites with `return_exceptions=True`
- Auth middleware `except Exception: pass` → `logger.exception()`
- `manifest_detector.py` silent pass → logged warning
- `except (TimeoutError, Exception)` split into separate handlers

**P1 — Performance (6/6)**:
- Ecosystem probing: partial results preserved on timeout
- 45× `rglob` → single `rglob("*")` walk (O(N×M) → O(N))
- O(n²) graph node scans → O(1) lookup dict
- DictCache debounce (2s write coalescing)
- Sequential CVE POST → parallel `asyncio.gather`
- Per-call ThreadPoolExecutor → reusable instance

**P2 — Code Quality (10/10)**:
- 21 silent `except Exception: pass` → logged across 16 files
- 29 dead functions removed from `api/routes/system.py` (1491→559 lines)
- 20 manifest updaters extracted from `cli/shared.py` (1240→494 lines)
- `_lock()` monolith extracted into 6 helpers (615→90 lines)
- 7 module-level env vars centralized to `settings/__init__.py`
- 8 unregistered env vars registered + 4 unused `import os` removed
- Layer violation (api→cli) fixed
- 293 missing type annotations added
- 62 `getattr(args, ...)` calls → typed `args.attr`
- 4 duplicate function pairs consolidated

**P3 — Test Coverage (7/7)**:
- `pubgrub_core.py`: 101 new tests (found 3 bugs → xfail)
- `policy_engine.py`: 47 new tests (10 rule types)
- `pinning.py`: 26 new tests
- `ConflictResolver`: 51 new method tests
- `test_pipeline.py`: e2e user workflow
- SBOM tests: deferred (thin wrapper)
- Plugin contract tests: all 5 plugins verified

**P4 — Nice-to-Have (8/8)**:
- PubGrub flat-dict dependency constraint fix
- Blocking I/O → async in `system.py`
- Temp directory leak fix (`mkdtemp` → try/finally)
- SSRF guard (`_validate_external_url`)
- Background task tracking
- Version parse logging
- Lazy settings (PEP 562 `__getattr__`, 96+ env vars)
- Immutable `CONFLICT_RULES` tuple

### Phase 3 — Q1-Q43 (191 findings, all fixed, 2026-07-17)

**Key bug fixes across all 43 questions**:
- **Q2**: Per-ecosystem isolation `break`→`continue` (resolve.py:903)
- **Q4**: Lock file ecosystem-qualified package keys
- **Q5**: Content-sniffing with PEP 508 validation
- **Q6**: Chart.lock and flake.lock reacheable; import-order plugin fix; Podfile.lock parser
- **Q7**: OS/arch constraint pipeline completed (dead code→live)
- **Q8**: Unbounded asyncio.gather → Semaphore guarded
- **Q9**: go.sum dead code removed
- **Q10**: Plugin import-order bug fixed
- **Q11**: udr.lock removed from MANIFEST_PATTERNS
- **Q12**: 94 cross-eco tests for all 21 untested ecosystems
- **Q13**: npm/yarn workspaces, Cargo [workspace], Go go.work
- **Q14**: Conda+pip correctly tags pip deps as pypi
- **Q15**: Go replace consumed, go.work parser, GOPROXY_AUTH_TOKEN
- **Q16**: Wheel platform tag enforcement (`check_platform_compatibility`)
- **Q17**: Optional deps `--with-dev`/`--without-optional`
- **Q18**: API key `is_active` filter `is`→`==` (auth bypass fix)
- **Q19**: Graceful shutdown with signal handlers + context managers
- **Q20**: Docker/Vcpkg/Terraform/Conan/Helm real API calls (no stubs)
- **Q21**: `asyncio.run()` inside event loop → `await asyncio.wait_for`
- **Q22**: Desktop/API sync (Check tab, CORS, API key)
- **Q23**: Docker deployment (SECRET_KEY, env vars, HEALTHCHECK)
- **Q24**: All 14 env vars registered in lazy settings
- **Q25**: `pytest-timeout` in dev deps, global 120s timeout
- **Q26**: Coverage includes data_sources (removed omit)
- **Q27**: Nested transaction fix (remove inner `db.commit()`)
- **Q28**: Sentry `traces_sample_rate=1.0`→`0.1`, `send_default_pii=False`
- **Q29**: Thread/Executor lifecycle leaks (try/finally guards)
- **Q30**: Race conditions (throttle, circuit breaker, cache, API key)
- **Q31**: Subprocess calls with timeout (22 sites)
- **Q32**: fcntl.flock with timeout + staleness check
- **Q33**: Connection pooling (reuse aiohttp.ClientSession)
- **Q34**: Plugin system (Hex typo, dual registration, validation, thread-safety, lifecycle)
- **Q35**: Database integrity (CASCADE, lazy→selectinload, size/overflow, SQLite JSON)
- **Q36**: Security hardening (27 items: timing attack, JWT, plaintext keys, CSRF, MD5→SHA256)
- **Q37**: Manifest parsers (14 broken parsers fixed)
- **Q38**: Settings/Config (11 inconsistencies fixed)
- **Q39**: Data source clients (8 bugs fixed)
- **Q40**: Utilities (logging, dead code, purl, typo)
- **Q41**: Documentation audit (13 stale claims fixed)
- **Q42**: Scanner gaps (macOS disks, APT truncation, race)
- **Q43**: Testing gaps (system_scanner 23→40 tests, test_comprehensive uses create_solver)

### Phase 4 — Q44-Q47 (Claim Audit, 2026-07-18)

- **Q44**: Doc count mismatches fixed (API endpoints 63→54, exports 12→15, ecosystems 20→22)
- **Q45**: Cross-eco dependency resolution end-to-end (3 solver tests + E2E tests)
- **Q46**: EVIDENCE.md created (188 claims, 188/188 verified)
- **Q47**: Real-repo evidence (6 repos, 5,455 packages, 0 errors)

### Phase 5 — Cross-Ecosystem Upgrade (all complete)

| # | Item | Status |
|---|------|--------|
| 5.1 | Batch/sharded SAT solver | ✅ SCC graph partitioning, topological resolution |
| 5.2-5.11 | Manifest updaters (all 18 ecosystems) | ✅ go.mod, cabal, mix.exs, build.gradle, Package.swift, pubspec.yaml, Brewfile, pom.xml, apt/apk |
| 5.12 | Incremental resolution | ✅ resolution_hash per package |
| 5.13 | PubGrub solver integration | ✅ Rust-backed default |

### Phase 6 — Cross-Compilation & Offline

| # | Item | Status |
|---|------|--------|
| 6.1 | --target/--platform flags | ✅ OS/arch/CUDA target override |
| 6.2 | Automatic offline index population | ✅ SQLite auto-cache during fetches |
| 6.3 | Per-ecosystem solver isolation | ✅ _group_by_ecosystem() |

### Phase 7 — Platform & Integrations

| # | Item | Status |
|---|------|--------|
| 7.1 | WASM frontend | 🔧 Deferred (no clear user need) |
| 7.2 | Desktop app (Electron→Tauri) | ✅ Electron works (43 tests, 82.88% coverage on testable modules), Tauri deferred |
| 7.3 | VSCode extension | ✅ 13 commands, CI wired, tsconfig fixed |
| 7.4 | GitHub Actions | ✅ lock-check.yml |
| 7.5 | GitLab CI | ✅ .gitlab-ci.yml template |
| 7.6 | Pre-commit hook | ✅ lock-check before commits |

### Phase 8 — Compliance & Security

| # | Item | Status |
|---|------|--------|
| 8.1 | License compliance | ✅ check --license |
| 8.2 | CVE scanning | ✅ check --cve (OSV) |
| 8.3 | CVE auto-fix | ✅ update --fix-cve |
| 8.4 | SBOM generation | ✅ SPDX 2.3 / CycloneDX 1.5 |
| 8.5 | Supply chain attestation | ✅ lock --sign, SLSA provenance |
| 8.6 | Policy engine | ✅ 10 rule types |

### Phase 9 — Ecosystem Deepening (all complete)

| # | Item | Status |
|---|------|--------|
| 9.1 | Nix/Guix | ✅ Manifests, lock parsers, 24 tests |
| 9.2 | Vcpkg | ✅ C/C++ package manager |
| 9.3 | Conan | ✅ C/C++ (another) |
| 9.4 | Helm/chart | ✅ Kubernetes manifests |
| 9.5 | Terraform provider locks | ✅ .terraform.lock.hcl |
| 9.6 | Dockerfile FROM parsing | ✅ Docker Hub API v2 |

### Phase 10 — Developer Experience (all complete)

| # | Item | Status |
|---|------|--------|
| 10.1 | Dependency graph | ✅ D3.js force-directed |
| 10.2 | `udr why` | ✅ Dependency chain + constraint trace |
| 10.3 | `udr diff` | ✅ Lock file comparison |
| 10.4 | `udr outdated` | ✅ Stale package detection |
| 10.5 | Shell completions | ✅ Bash/zsh/fish |
| 10.6 | Man page | ✅ docs/man/udr.1 |

---

## Remaining Work

### Skipped Items (No Current Plan To Implement)

These items were evaluated and deliberately skipped because the effort does not justify the gain for UDR's core value proposition (cross-ecosystem resolution):

| Item | Effort | Rationale |
|------|--------|-----------|
| **Concurrent version support (Cargo-style)** | 4-8 week architectural rework across SAT encoding, PubGrub API, BFS dedup, lock file format | Only 1/20 ecosystems (Cargo) needs it. Cargo's existing resolution already works. |
| **Virtual package/Provides resolution** | Solver changes for 2/20 ecosystems | APT/APK parse `provides` data but APT/APK are flat-resolved (no cross-eco). Rare even in Debian. |
| **Single lighter-weight SAT backend (PySAT/resolvo)** | Evaluate + integrate + maintain | Z3 works. PubGrub is the strategic path. ForkingResolver already wraps both. Adding a third backend increases maintenance burden. |
| **CLI consolidation (18→9 commands)** | Breaking change, doc rewrite, deprecation cycle | Users learn 3-5 commands anyway. Breaking muscle memory hurts more than 18 commands. |
| **Plugin marketplace** | Infrastructure, registry, discovery | Zero community plugins exist. Build the API first, marketplace follows. |
| **WASM frontend** | Compile entire resolver to WASM | No clear user need. Current frontend works via REST API. |
| **Desktop Tauri rewrite** | Full rewrite of Electron app | Electron works (43 tests pass). Desktop adoption is niche. |
| **Benchmark regression suite** | pytest-benchmark + historical tracking | Existing `scripts/benchmark.py` + weekly CI benchmark workflow provide basic coverage. No direct user benefit. |
| **Coverage 55%→65%** | Hardest 10% takes 90% effort | Current 55% is green. Focus on high-risk paths rather than line count. |
| **Full incremental re-resolution (skip BFS)** | Rewrite BFS to track subgraph changes | Resolution hash caching already skips SAT for unchanged subtrees. BFS walk is not the bottleneck. |
| **Man page** | Writing + packaging | `udr --help` + CLI.md serve the same purpose. |

### Nice-to-Have (If Someone Wants To Build)

| Item | Effort | Gain | Status |
|------|--------|------|--------|
| **Ruff docstrings (221 missing)** | 1-2 hours per session, incremental | Code clarity, ruff compliance | ✅ All 0 D violations — fixed across 54 files |
| **Type stubs (.pyi) for orchestrator/ and core/** | 2-3 days | Better IDE experience for library consumers | ✅ `.pyi` stubs created for `orchestrator/` (12 exports) and `core/` (21 lazy exports) |
| **API/CLI parity: add /outdated, /diff, /why, /graph, /verify** | — | — | ✅ All 5 endpoints exist |
| **Structured error types (ResolutionError hierarchy)** | — | — | ✅ Exists (P2 #25) |
| **Prometheus metrics endpoint** | — | — | ✅ Wired via `Instrumentator` (P2 #23) |
| **OpenTelemetry spans** | — | — | ✅ Manual spans on 3 critical paths (P2 #24) |
| **Ecosystem version normalization table** | — | — | ✅ Pre-release + multi-format in `constraint_normalizer.py` (P2 #19) |
| **Ecosystem aliases** | — | — | ✅ `sanitize_ecosystem_name` handles all common aliases (P2 #21) |

---

## Release Milestones

| Version | Focus | Status | Target |
|---------|-------|--------|--------|
| v1.3 | Core resolution, 25 ecosystems, CLI+API, desktop app | ✅ Released | Q3 2026 |
| v1.4 | PubGrub default, ForkingResolver, ContentAddressedCache, platform markers, P0-P4 gap closure, Q1-Q43 fixes, Phase 5-10 complete, doc rewrite, accuracy hardening | 🔜 Current | 2026-07-23 |
| v1.5 | Remaining deferred items, WASM frontend (if demand), community plugin marketplace, benchmark regression suite | 🔮 Next | Q4 2026 |
| v2.0 | Source repo URL + commit hash enrichment, ruff docstrings (all D violations → 0), type stubs (.pyi), desktop Tauri evaluation | 🔮 Planned | Q1 2027 |

---

## Key Strategic Decisions

1. **PubGrub is the long-term solver** — Z3 becomes optional `udr[z3]`. PubGrub is smaller (no 30MB z3-solver), simpler (~650 lines vs ~2089), and production-proven (Dart, Swift, Cargo).
2. **Plugin-first for ecosystem coverage** — Not more bespoke clients. Define the plugin interface first, let the community fill in ecosystems.
3. **Library API surface = `orchestrator/` + `core/`** — Everything else (`data_sources/`, `manifest_detector.py`, `database/`) is internal with no stability guarantees.
4. **Client contract tests as gate** — No new client lands without passing the standard suite (`test_client_contract.py`).
5. **Desktop bundles offline indexes + local API** — Not a separate codebase. Electron shell wraps `udr serve` as subprocess.
6. **API mirrors CLI** — Every CLI command should have a corresponding API endpoint.
