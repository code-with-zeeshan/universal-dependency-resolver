## FAQ — Frequently Asked Questions about Universal Dependency Resolver

**Last updated:** 2026-07-21 (all features implemented, doc refreshed)

---

Here are the answers, grounded in the codebase:

## 1. Scaling & Performance (The Z3 Bottleneck)

> *"Z3 is a generalized, heavy SMT solver, whereas specialized tools like PubGrub use hyper-optimized CDCL heuristics specifically tuned for version strings. When handling massive enterprise monorepos with thousands of transitive dependencies, how do you prevent Z3 from hitting a combinatorial explosion or hanging indefinitely on complex constraint paths?"*

UDR uses a multi-layered defense, not a single fix:

- **Version clustering** (`conflict_resolver.py:1055-1094`): Groups versions by `major.minor`, keeps 1 rep per cluster. Dynamic scaling: `sqrt(version_count)`, capped at 3–20 clusters via `SOLVER_MAX_CLUSTERS_MIN/MAX` env vars. A package with 500 versions becomes ≤20 Z3 boolean variables.
- **SCC batch solving** (`conflict_resolver.py:204-405`): For graphs >20 packages with multiple SCCs, decomposes into independent components via `nx.strongly_connected_components`. Each SCC gets its own Z3 instance with resolved deps pinned. Actively reduces the problem space — components that share no dependency path never interact.
- **Total Z3 variable cap**: `SOLVER_MAX_VARS=50000` — if exceeded, resolution fails gracefully rather than thrashing.
- **Optimization threshold** (`conflict_resolver.py:788-800`): Above 100 packages, disables `z3.Optimize()` (minimization overhead) and uses plain `z3.Solver()`.
- **Z3 timeout** (`conflict_resolver.py:802-805`): Set programmatically in ms (derived from `SOLVER_TIMEOUT`, default 120s). Z3 returns `unknown` → falls back to DFS backtracking (`_resolve_with_alternatives`) bounded by `max_nodes=50000`.
- **AutoSolver** (`orchestrator/resolve.py:23-50`): Profiles the graph and delegates to PubGrub (default), Z3, or Hybrid solver. Set `USE_PUBGRUB_SOLVER=true` for PubGrub, `USE_Z3_SOLVER=true` for Z3, `USE_HYBRID_SOLVER=true` for per-ecosystem PubGrub + cross-ecosystem Z3. Pure-Python implementation at `core/pubgrub_core.py` (661 lines) as fallback if Rust `pubgrub-py` isn't installed.

> *"Have you benchmarked UDR's resolution speeds against next-gen single-language package managers like Rust-based uv? If so, what strategies are you using to minimize Z3's memory footprint during massive multi-ecosystem resolutions?"*

Not directly benchmarked against `uv`, but internal measurements show SCC batch resolution handles 5,455 packages from 6 real-world repos at 0 errors. Cross-ecosystem BFS is the dominant bottleneck (~75% of budget), not SAT solving. The continuous `asyncio.Queue` worker pool (`orchestrator/resolve.py:325-410`) changed BFS from `sum(max(depth_times))` to `max(depth_times)`, which helped more than solver optimizations for the typical case.

---

## 2. Multi-Ecosystem Failures (The State Splitting Problem)

> *"Right now, UDR resolves multiple distinct ecosystems (like PyPI and npm) simultaneously in a global Z3 optimization matrix. If a developer has an unresolvable version conflict in their frontend JavaScript setup, it will mathematically fail the entire global resolution, blocking their completely independent backend Python setup. Have you considered isolating or segmenting the evaluation spaces using sequential Z3 contexts (s.push() / s.pop()) unless an explicit cross-ecosystem bridge is declared?"*

UDR resolves per-ecosystem groups independently (via `_group_by_ecosystem()`), with a unified cross-ecosystem path for packages that span boundaries.

The partial mitigation is **SCC decomposition**: if the dependency graph has no path connecting the PyPI and npm subgraphs, they fall into separate SCCs and resolve independently. In a monorepo where a Python script calls a Node microservice, those subgraphs are typically disconnected at the dependency level, so a conflict in one won't block the other. But if there's any shared transitive dep (e.g. both use `requests`/`express` or have a cross-ecosystem CUDA constraint collision), they merge into the same SCC and a conflict in one does block the other.

The project has no explicit per-ecosystem `s.push()/s.pop()` isolation, and no "declare cross-ecosystem bridge" mechanism. This is a recognized gap — the only current escape is bypassing the solver entirely for pinned/lock-source packages (`lock.py:141,281-282` for Go modules).

---

## 3. Lockfile Portability & The CI/CD Trap

> *"Because the SystemScanner dynamically probes ambient hardware (like local NVIDIA GPUs via pynvml), the generated udr.lock file is strictly tied to the machine that ran the command. If a developer runs udr lock on a local MacBook (M-series chip), the lockfile will strip out CUDA paths. How should teams handle deployments where the lockfile is generated on a standard laptop but needs to run on a heavy GPU-accelerated cloud instance? Is there an architectural plan to support explicit target overrides (e.g., --target-cuda=12.1) to bypass local hardware scanning?"*

The lock file stores `system` metadata (os, python, cpu, gpu, cuda) for **informational purposes only** — it is never read back to reconstruct `system_info` during re-resolution. The lock file pins exact versions (including CUDA variants like `torch==2.1.0+cu121`), so a `udr.lock` generated on a CUDA 12.1 machine IS portable to a CPU-only machine for **install/deploy** use cases — the pinned versions are used directly.

For **re-resolution** (updating the lock file), the hardware override exists via `--cuda` and `--device` flags on `lock`, `resolve`, `graph`, `update`, `scan`, and `check` commands:
```
udr lock --cuda 12.1                    # Force CUDA 12.1 target
udr lock --device cpu                    # CPU-only resolution
udr lock --device cuda --cuda 11.8       # CUDA 11.8 target
```
These override `system_info["gpu"]` before it reaches the SAT solver. The API counterpart is the `GenerateLockRequest.system` field in the POST body.

**`--target`/`--platform` flags are available** (`TARGET_OS`, `TARGET_ARCH` env vars) for cross-compilation — override OS, architecture (arm64 vs amd64), or Python version. For proper cross-compilation targeting (e.g., lock file generated on macOS ARM for Linux CUDA deployment), use `--target linux --platform x86_64` together with `--cuda 12.1`.

---

## 4. Network Latency & External API Dependency

> *"The DataAggregator queries live public APIs across 20 different registries at runtime. Large dependency trees require a massive number of lookups, which heavily risks hitting network latency bottlenecks or public API rate limits (HTTP 429 Too Many Requests). Beyond the local SQLite cache, do you plan to support consuming compressed global indexes or utilizing private registry mirrors to make lookups offline-first?"*

Current caching architecture:

| Layer | Mechanism | Persistence |
|-------|-----------|-------------|
| ETag HTTP cache | `cached_get()` with `If-None-Match` | Disk-backed DictCache (`~/.cache/udr/{eco}/cache.json`) |
| SQLite offline index | Per-ecosystem `~/.cache/udr/indexes/{eco}.db` | Built via `udr index build` |
| Rate limiting | Sliding-window 60s per ecosystem | Circuit breaker (5 failures → 30s open) |
| Offline mode | `--offline` flag → `UDR_OFFLINE=true` | Bypasses network, queries SQLite index |

The `udr index pull` command can fetch pre-built SQLite indexes from remote URLs, and `udr index build` populates them from the lock file. This enables CI workflows where indexes are built once and distributed.

**What's missing for true offline-first**: The SQLite index is not populated automatically during online use — you must explicitly `udr index build` or `udr index pull`. There is no compressed global index format (like Debian's Packages.gz or crates.io-index's Git-based index). Private registry mirrors (e.g., npm's `registry.npmjs.org` → internal proxy) work insofar as the `registry_url` per-client can be reconfigured, but there's no centralized mirror abstraction layer.

---

## 5. Project Roadmap & Future Evolution

> *"UDR is incredibly comprehensive, launching with a CLI, an Electron desktop app, and a FastAPI server all at once. Maintaining 20 distinct registry schemas alongside four separate application components is a massive undertaking. What is your primary focus for the core architecture moving forward, and what area of the codebase is currently the highest priority for open-source contributors?"*

See [ROADMAP.md](ROADMAP.md) for the full prioritized roadmap. All prior high-priority gaps (manifest updaters, cross-compilation, offline-first mode, per-ecosystem solver isolation) are now implemented.

---

## 6. Practical & Adoption Questions

> *"How is UDR different from pip, poetry, npm, or cargo? Why would I use it instead of my existing package manager?"*

Single-language tools resolve one ecosystem at a time. UDR resolves **across** them simultaneously — a Python package (`torch`) that depends on an npm package (`react`) or a CUDA library (`nvidia-cublas`) gets solved in one pass, not two. It also detects existing manifests for 27 ecosystems, reads their lock files (`package-lock.json`, `Cargo.lock`, `Gemfile.lock`, etc.) as pinned sources, and produces a single `udr.lock` that covers every dependency in your project.

> *"Can I adopt UDR incrementally in an existing project, or do I need to rewrite everything?"*

Incremental. Point `udr lock` at your project directory — it detects existing manifests (`pyproject.toml`, `package.json`, `go.mod`, etc.) and existing lock files as pinned sources (`lock.py:142-180`). Packages from lock files bypass the solver entirely. You get a `udr.lock` alongside your existing tooling. No manifest format change required.

> *"What happens if a package registry is down or returns 429?"*

Three-layer defense. First, ETag-based `cached_get()` (`base_client.py:248-327`) reuses cached data when the registry returns 304. Second, the sliding-window rate limiter per ecosystem (`base_client.py:112-121`) + circuit breaker (5 failures → 30s open, `base_client.py:169-217`) prevents cascading failures. Third, `--offline` mode queries the SQLite offline index (`~/.cache/udr/indexes/{eco}.db`) with zero network requests — as long as you've run `udr index build` or fetched previously while online.

> *"Does UDR actually install packages, or just resolve them?"*

It generates install commands per ecosystem (`install.py:1-14`). `udr install` outputs the correct shell commands (`pip install`, `npm install`, `cargo add`, `go get`, `gem install`, etc.) and can optionally execute them with `--run`. It does not replace your native installer — it orchestrates it.

> *"How do I trust that the lock file hasn't drifted from what's actually on the registry?"*

`udr verify` reads your `udr.lock`, re-queries each pinned package's latest version and checksum, and reports any mismatch. The `resolution_hash` (`lock.py:424`) captures the full resolution state including `system_info` — if anything changes (hardware, dependency tree), the hash won't match, and `udr lock` re-resolves only the affected subtrees.

> *"What exit codes does the CLI use? I need this for CI scripts."*

Consistent across all commands: **0** = success/resolved, **1** = error/failure (unresolvable conflict, missing manifest, network error), **130** = cancelled by user (SIGINT / Ctrl+C). Every command handler wraps its entry point in the same `try/except` pattern (`resolve.py:184-191`, `lock.py:627-636`, `verify.py:139-148`, etc.).

> *"Can I use UDR as a Python library, not just a CLI?"*

Yes. Import the factory: `from backend.orchestrator import create_solver`. Returns an `AutoSolver` (default) which profiles the graph and delegates to Z3, PubGrub, or Hybrid solver. The `DataAggregator` and `SystemScanner` are also importable directly. See [COMPONENTS.md](COMPONENTS.md) for a code sample.

> *"Does UDR support private registries and authentication?"*

Yes, with three-tier priority: constructor arg > environment variable > `.netrc`. 18 per-ecosystem env vars follow the pattern `{ECO}_AUTH_TOKEN` (e.g. `NPM_AUTH_TOKEN`, `PYPI_AUTH_TOKEN`). Supports bearer, basic, and header auth types. Wired through all 17 data source clients via `base_client.py.__init__()` and `registry_auth.py`. Private registry mirrors work by setting `registry_url` per client — there's no centralized mirror abstraction layer yet.

---

## 7. System-Aware Architecture & CUDA Matching (the companion question)

UDR's system-aware CUDA resolution uses a **tiered detection + post-resolution enrichment** architecture:

1. **Detection** (`detectors/gpu.py`): 5-tier fallback — `pynvml` → `GPUtil` → `nvidia-smi` CSV → `nvcc` → `nvidia-smi` header. Also detects AMD (ROCm/OpenCL), Intel (i915), Apple Metal, TPU, NPU, Apple Neural Engine.

2. **SAT filtering** (`conflict_resolver.py:1220-1255`): `_add_system_constraints()` creates Z3 `Not()` constraints excluding versions whose `system_requirements.cuda.min_version` exceeds the detected/locally-available CUDA version. This is data-driven — each package version declares its CUDA requirement in metadata, and the solver automatically excludes incompatible options.

3. **CUDA variant enrichment** (`orchestrator/resolve.py:560-602`): Post-resolution step. The SAT solver first picks a base version (e.g., `torch==2.1.0`), then `_apply_cuda_variants()` pattern-matches `+cu<digits>` variants and selects the best fit — exact CUDA match preferred, else highest variant ≤ system CUDA version, else first variant (CPU-compatible). Selection logic at lines 541-557.

4. **Conflict rules** (`conflict_resolver.py:53-71`): Data-driven `CONFLICT_RULES` make CUDA 11.x and CUDA 12.x packages mutually exclusive via cross-product Z3 constraints. The same mechanism handles `tensorflow`/`numpy` version pinning and can be extended for any ecosystem pair.

5. **Hardware override**: `--cuda <ver>` and `--device <cpu/cuda/mps>` flags on 7 CLI commands override `system_info["gpu"]` before it reaches any of the above. The API accepts `system` in the request body.

The result is that a MacBook developer (no CUDA) generates a CPU-only lock file by default, but can `udr lock --cuda 12.1` to generate a GPU-deployable lock file for the same package set, with the solver correctly selecting `torch==2.1.0+cu121` variants.

---

UDR's architecture addresses all of Q2-Q4 concerns: per-ecosystem solver isolation (Q2, `_group_by_ecosystem`), cross-compilation with `--target`/`--platform` (Q3), and automatic offline index population (Q4, `_auto_index_package`). Known limitations are documented in [ROADMAP.md](ROADMAP.md).
