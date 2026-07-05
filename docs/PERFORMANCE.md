# Performance

## SAT solver internals

```mermaid
flowchart TB
    subgraph Input["📥 Input"]
        PACKAGES["Package list<br/>with versions & deps"]
        SYSINFO["System info<br/>OS · GPU · CUDA · Python"]
    end

    subgraph Normalize["1️⃣ Normalize"]
        NORM["Normalize package names<br/>Validate inputs"]
        GRAPH["Build dependency graph<br/>(NetworkX DiGraph)"]
    end

    subgraph Variables["2️⃣ Create Z3 Variables"]
        VARS["Create Bool vars per version<br/><code>z3.Bool('torch_2.1.2')</code>"]
        CLUSTER["Cluster versions<br/>(major.minor, latest patch)"]
        WEIGHTS["Assign optimization weights<br/>newer = lower weight"]
    end

    subgraph Constraints["3️⃣ Add Constraints"]
        ONEVER["Exactly one version per pkg<br/><code>z3.Or() + z3.AtMost(1)</code>"]
        SYSREQ["System requirements<br/>CUDA ≥ min_version<br/>Python ≥ min_version"]
        DEP["Dependency constraints<br/><code>z3.Implies(pkg, valid_deps)</code>"]
        CONFLICT["Conflict rules<br/>CUDA 11 vs 12 XOR<br/>tensorflow + numpy upper bound"]
    end

    subgraph Solve["4️⃣ Solve"]
        OPT["<code>z3.Optimize()</code><br/>minimize(Sum(weights))"]
        CHECK["<code>solver.check()</code>"]
        RESULT{"Result?"}
        SAT["SAT ✅<br/>Extract model<br/><code>solver.model()</code>"]
        UNSAT["UNSAT ❌<br/>Analyze conflicts"]
        TIMEOUT["TIMEOUT ⏰<br/>Fallback: backtracking"]
    end

    subgraph Output["5️⃣ Output"]
        SOLUTION["Formatted solution<br/>version · ecosystem · tree"]
        PARTIAL["Partial solution<br/>per-package alternatives"]
        ERROR["Error payload<br/>with correlation ID"]
    end

    Input --> Normalize
    NORM --> GRAPH
    GRAPH --> Variables
    CLUSTER --> VARS
    VARS --> WEIGHTS
    WEIGHTS --> Constraints
    ONEVER --> SYSREQ
    SYSREQ --> DEP
    DEP --> CONFLICT
    CONFLICT --> Solve
    OPT --> CHECK
    CHECK --> RESULT
    RESULT -->|"sat"| SAT
    RESULT -->|"unsat"| UNSAT
    RESULT -->|"unknown"| TIMEOUT
    SAT --> SOLUTION
    UNSAT --> PARTIAL
    TIMEOUT --> PARTIAL
    PARTIAL --> ERROR

    style SAT fill:#2e7d32,color:#fff,stroke:#1b5e20,stroke-width:2px
    style UNSAT fill:#c62828,color:#fff,stroke:#b71c1c,stroke-width:2px
    style TIMEOUT fill:#e65100,color:#fff,stroke:#bf360c,stroke-width:2px
```

**Key implementation details:**
- Z3 boolean variables are created per package version (`z3.Bool(f"{name}_{version}")`)
- Exactly-one constraint enforced via `z3.Or()` + `z3.AtMost(1)` per package
- Dependency constraints use `z3.Implies(pkg_var, Or(valid_dep_vars))`
- CUDA 11 vs 12 conflict: `z3.Not(And(var11, var12))` for each pair
- `SOLVER_MAX_VARS` env var (default 5000) prevents memory blowup
- Version clustering caps at 50 versions per package via `SOLVER_MAX_VERSIONS_PER_PKG`
- When UNSAT/timeout, falls back to DFS backtracking in `_resolve_with_alternatives()`

## Startup time

The CLI starts in ~0.85s on a modern machine. This is achieved through:

- **Lazy `import z3`**: Z3 is imported inside 7 methods of `ConflictResolver`, not at module level. Commands that don't need resolution (e.g. `udr check`, `udr list-ecosystems`) skip Z3 entirely.
- **Lazy data source clients**: All 20 ecosystem clients are registered via `importlib.import_module()` in `_register_client()` builders. They are only imported when first accessed.
- **Lazy aggregator**: `DataAggregator` creates clients on demand.

## Resolution performance

- Simple resolutions (1-3 packages, single ecosystem): <1s (after metadata fetch)
- Complex resolutions (multi-ecosystem, many constraints): depends on Z3 solver time

## Caching

| Layer | Type | Default TTL |
|---|---|---|
| Package metadata | DictCache (in-memory) or Redis | 1 hour |
| Resolution results | DictCache or Redis | 1 hour |
| System info | DictCache (5-min TTL) | 5 minutes |
| System scan results | In-memory, refreshed per resolve | Per request |

## Network

- All registry API calls use `aiohttp` with connection pooling
- Concurrent fetching via `asyncio.gather` for package metadata
- 5-second timeout on individual registry requests
- Configurable rate limits per ecosystem (default: 60-600 req/min)

## Desktop app

- Backend runs as a subprocess on a local port
- GUI communicates via localhost REST API (no network overhead)
- No Python install needed — compiled to standalone binary via PyInstaller

## Bottlenecks

- **First-ever resolution** for a package requires remote API calls. Subsequent resolutions hit cache.
- **Z3 solver** time scales with constraint complexity. Simple version ranges are fast; complex cross-ecosystem constraints take longer.
- **System scanning** GPU detection via `pynvml` is fast (<100ms). Full system scan <500ms.
