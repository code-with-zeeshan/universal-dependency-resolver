# Frequently Asked Questions

## 1. How does UDR handle multi-ecosystem conflicts?

UDR uses a SAT solver (Z3 by default, PubGrub as opt-in) that understands dependency constraints across ecosystem boundaries. When package A from PyPI depends on package B from npm, the solver creates cross-ecosystem variables and solves them in a single SAT model. If the graph is too large, packages are grouped into single-ecosystem sub-graphs that resolve independently, with only cross-ecosystem edges going through the unified path.

## 2. What happens when resolution fails?

The solver first runs cross-validation (tries the alternate solver — Z3 ↔ PubGrub). If both agree on unsat, it returns diagnostic info:
- Packages with no compatible versions
- Cyclic impossible constraints
- Mismatched version requirements

The `--interactive` flag opens a manual resolution mode where you can adjust constraints and re-run.

## 3. Can I take a lock file from one machine and use it on another?

Yes. The lock file (`udr.lock`) stores resolved versions independent of the host machine. GPU-aware packages store CUDA variant info in the lock file. Running `udr verify` on a different machine checks that all pinned versions still exist in their registries. To re-resolve for a different environment, use `udr update --cuda <version>`.

## 4. How does UDR handle network latency or registry downtime?

- **Caching**: DictCache (in-memory, TTL 1h) + ContentAddressedCache (SHA256 blob store on disk)
- **Offline indexes**: Pre-built SQLite indexes can be downloaded for environments without registry access
- **Retry**: Base HTTP client retries with exponential backoff (max delay 10s)
- **Timeouts**: Configurable via `SOLVER_TIMEOUT` (default 120s) and `SOLVER_API_TIMEOUT` (default 300s)
- **Fallback**: If a registry is unreachable, the resolver uses cached data or offline indexes

## 5. What's the roadmap for UDR?

The project is ready for production use. Current focus:

| Area | Status |
|---|---|
| CLI (24 commands) | ✅ Complete |
| REST API (59 endpoints) | ✅ Complete |
| SAT Solver (Z3 + PubGrub) | ✅ Complete |
| 25 ecosystems supported | ✅ Complete |
| CVE scanning | ✅ Complete |
| SBOM (SPDX/CycloneDX) | ✅ Complete |
| Desktop app (Electron) | ✅ Complete |
| VS Code extension | ✅ Complete |
| Supply chain signing | ✅ Complete |
| License / policy engine | ✅ Complete |
| Cross-compilation | ✅ Complete |
| JS/TS and Go SDKs | 🔮 Planned (community-driven) |

## 6. How is this different from `pip-compile` / `poetry` / `npm` / `cargo`?

| Tool | Focus | Limitation |
|---|---|---|
| pip-compile | Python only | Single ecosystem |
| Poetry | Python only | Single ecosystem |
| npm/yarn/pnpm | JavaScript only | Single ecosystem |
| Cargo | Rust only | Single ecosystem |
| Bundler | Ruby only | Single ecosystem |
| **UDR** | **All ecosystems** | **Cross-ecosystem SAT solving, unified lock file** |

UDR is not a replacement for these tools — it's a meta-resolver that coordinates them. It produces a `udr.lock` that captures the full dependency graph across all ecosystems, then delegates actual package installation to the native package managers.

## 7. Does UDR support CUDA/GPU-aware resolution?

Yes. For PyPI packages with CUDA-tagged variants (e.g. `torch 2.1.2+cu121`), UDR:

1. Auto-detects the system CUDA version via `nvidia-smi`, `nvcc`, or `pynvml`
2. Selects the best-matching CUDA variant (exact match preferred, closest lower as fallback)
3. On CPU-only machines, use `--cuda 12.1` to force GPU-aware resolution
4. Stores CUVA variant info in the lock file for portability

Also supports `--device` flag for explicit selection: `cpu`, `cuda`, `mps` (Apple Silicon), or `rocm` (AMD).

## 8. Can I use UDR in CI/CD?

Yes. UDR is designed for CI pipelines:

```yaml
# GitHub Actions — check for drift on every PR
- name: Check lock file freshness
  run: |
    pip install ud-resolver[z3]
    udr lock --check
```

The `--check` flag runs full resolution and diffs against the existing lock file. Exits with code 1 if drift is detected (fails the build). Use `udr lock --check` in pre-commit hooks, GitHub Actions, GitLab CI, or any CI system.

## 9. What data does UDR send to external services?

UDR queries public package registries (PyPI, npmjs.com, crates.io, etc.) for version and dependency metadata. No telemetry, no usage tracking, no data sent to any UDR-controlled server. The offline index mode (`udr index pull`) downloads pre-built SQLite databases from a URL you specify.

## 10. How do I migrate from an existing lock file?

```bash
# Auto-detect and migrate (supports 25 formats)
udr migrate

# Preview first
udr migrate --display

# Force overwrite existing udr.lock
udr migrate --force
```

Supported source formats: `package-lock.json`, `Cargo.lock`, `poetry.lock`, `uv.lock`, `go.sum`, `Gemfile.lock`, `composer.lock`, `mix.lock`, `Package.resolved`, `yarn.lock`, `pnpm-lock.yaml`, `Brewfile.lock.json`, `Podfile.lock`, `Pipfile.lock`.

## 11. What Python versions are supported?

Python 3.11, 3.12, and 3.13.

## 12. Do I need a database or Redis?

No. SQLite is the default (zero configuration). PostgreSQL and Redis are optional for production multi-worker deployments.
