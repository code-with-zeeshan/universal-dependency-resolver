# Performance

## Solver Pipeline

The core resolution engine performs SAT solving (Z3 by default, PubGrub as opt-in) with the following pipeline:

```
Package inputs (name + version constraint)
        │
        ▼
┌─────────────────────────┐
│  1. Normalize           │
│  - Cross-eco constraint │  npm ^ → >=, <=, ~ → PEP 440
│    normalization         │  Go pseudo-version → semver
│  - NPM alias stripping   │  Bare versions → ==bound
│  - Version padding       │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  2. Create variables    │  SAT variable per (pkg, version) pair
│  - Version clustering   │  Group by major.minor, keep latest patch
│  - Prerelease filtering │  max 50 vars/pkg, 50000 total
│  - Limit enforcement    │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  3. Add constraints     │
│  - Singleton: one ver   │  Exactly one version per package
│  - Dep: if A=v1→B=v2    │  If version A selected, deps satisfied
│  - Conflict: ¬(A=v1∧B=v2)│  CUDA/numpy/version conflicts
│  - Platform markers     │  PEP 508 marker filtering (PEP 508)
│  - CUDA variant select  │  GPU variant selection by CUDA version
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  4. Solve (Z3 CDCL)     │
│  - Try optimize first   │  z3.Optimize() when USE_Z3_OPTIMIZE=true
│  - Fallback to solver   │  z3.Solver() when optimization disabled
│  - upgrade_to_latest    │  Post-process: upgrade each pkg to newest
│  - Timeout handling     │  Parallel cross-solver (PubGrub) fallback
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  5. Output              │
│  - Version assignments  │  {pkg: version} dict
│  - Deprecation warnings │  yanked/deprecated flags
│  - Resolution hash      │  SHA256 of (packages + system + constraints)
│  - Cross-validation     │  Alternate solver verification on failure
└─────────────────────────┘
```

## Startup Time

- **Cold start** (from pip install): ~0.85s to `udr --help`
- **Lazy imports**: Heavy dependencies (Z3, aiohttp, cryptography) imported only when the specific command needs them
- **Warm cache**: System scanner results cached for 5 minutes

## Resolution Performance

| Scenario | Packages | Time | Solver |
|---|---|---|---|
| Small (flask + deps) | 15-25 | ~15s | Z3 |
| Medium (express + deps) | 60-80 | ~45s | Z3 |
| Large (sentry: npm + pypi) | 1,567 | ~144s | Z3 |
| Large (cilium: gomodules) | 490 | ~225s | Z3 |
| Workspace (rust-lang/regex) | 21 | ~59s | Z3 |

**Key factors:**
- Registry API latency dominates (50-80% of total time)
- BFS dependency discovery scales with graph size, not solver time
- Z3 SAT solving is typically <5s for most real-world graphs
- Go proxy latency is the main bottleneck for gomodules (~2s per .mod fetch × 320 modules / 20 concurrent ≈ 32s minimum)

## Caching

| Layer | Location | TTL | Purpose |
|---|---|---|---|
| DictCache | In-memory | 3600s | Registry API responses (JSON) |
| DictCache (short) | In-memory | 300s | Rate-limited endpoints |
| DictCache (versions) | In-memory | 600s | Package version listings |
| ContentAddressedCache | `~/.cache/udr/cac/` | configurable | SHA256-verified blob store |
| SQLite Indexes | `~/.cache/udr/indexes/` | permanent | Offline package metadata |
| Redis (optional) | External | 3600s | Worker-shared cache + rate limiting |

## Network Concurrency

| Setting | Default | Description |
|---|---|---|
| `NPM_CONCURRENCY` | 10 | Concurrent npm registry requests |
| `GOMODULES_CONCURRENCY` | 20 | Concurrent Go proxy requests |
| `BFS_BATCH_SIZE` | 20 | Batch size for BFS dependency discovery |
| `SCANNER_MAX_WORKERS` | 10 | Thread pool for system scanning |

## Bottlenecks (Known)

| Bottleneck | Impact | Mitigation |
|---|---|---|
| Go proxy latency | ~2s per `.mod` fetch | Increase `GOMODULES_CONCURRENCY`, use `go.sum` as lock source |
| Conda multi-arch metadata | Slow for large env files | Use offline indexes |
| APT BFS explosion | Many system-level transitive deps | Limit depth with `--timeout` |
| Fresh cold cache | First run fetches all registry data | Pre-populate with `udr index build` |
| PubGrub pure-Python fallback | ~10× slower than Rust backend | Install `pubgrub-py` (Rust) |

## Desktop App

- Backend bundled via PyInstaller (single executable, ~110-120 MB)
- Communicates with local backend via HTTP on `127.0.0.1:8000`
- No rendering latency — plain HTML/CSS/JS with async fetch patterns
- Same performance profile as CLI for all resolution tasks
