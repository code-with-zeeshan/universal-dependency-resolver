# CLI Reference

## Entry Point

```
udr <command> [options]
```

Installed by `pip install ud-resolver` as the `udr` console script.

All commands support `--help` for inline usage.

---

## Global Flags

| Flag | Description |
|---|---|
| `--version` | Print version and exit (reads from `pyproject.toml`) |
| `--offline` | Offline mode: use cached data only, no network requests |
| `-h, --help` | Show help for any command |

---

## `serve`

Start the REST API server (FastAPI + uvicorn).

**Usage:**

```bash
udr serve                              # http://127.0.0.1:8000, local mode
udr serve --host 0.0.0.0               # bind all network interfaces
udr serve --port 9000                  # custom port
udr serve --reload                     # auto-reload on file changes (dev only)
udr serve --mode saas                  # enable full auth stack (JWT, rate limiting)
```

**Flags:**

| Flag | Default | Description |
|---|---|---|---|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8000` | Bind port |
| `--reload` | `False` | Enable hot-reload for development |
| `--mode` | `local` | `local` (no auth, no rate limits) or `saas` (JWT auth, rate limiting) |

**Environment variables:**

| Variable | Default | Description |
|---|---|---|
| `SOLVER_TIMEOUT` | `30` | Seconds before SAT solver falls back to per-package alternatives (used by `lock`/`scan`/`update`; `resolve` always uses fast path) |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Server stopped cleanly (Ctrl+C) |
| `1` | Server error (port in use, import failure, etc.) |

**API docs:** Once running, visit `http://localhost:8000/api/v1/docs` (Swagger UI).

---

## `check`

Scan the current system (OS, CPU, GPU, CUDA, Python, memory, runtimes) and display a compatibility report.

**Usage:**

```bash
udr check                              # basic system info
udr check -v                           # verbose (shows CPU arch, all runtimes)
udr check --deps                       # also show project's core dependencies
udr check --json                       # raw JSON output, then exit
udr check -v --deps                    # everything
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `-v, --verbose` | `False` | Show CPU architecture, runtime versions table |
| `--deps` | `False` | Show project core dependencies (from `pyproject.toml`) |
| `--json` | `False` | Output full system info as JSON to stdout, then exit |

**JSON output fields** (when `--json` is used):

```json
{
  "platform": { "system": "Linux", "release": "6.2.0", "machine": "x86_64" },
  "cpu": { "brand": "Intel(R) Xeon(R)", "arch": "x86_64", "count_logical": 8, "count_physical": 4 },
  "memory": { "total": 33456789000, "available": 28000000000, "percent": 16.3 },
  "gpu": { "available": true, "devices": [{"name": "NVIDIA A100", "memory_total": 40960}], "cuda": "12.1" },
  "runtime_versions": {
    "python": { "version": "3.11.5", "path": "/usr/bin/python3" },
    "node": { "version": "v20.0.0" }
  }
}
```

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Success |
| `1` | Scan failed |

---

## `info`

Shorthand system overview — OS, CPU, Python, Memory, GPU, plus a table of project dependencies.

**Usage:**

```bash
udr info                               # system overview + dependency table
udr info --json                        # raw JSON, then exit
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `--json` | `False` | Output full system info as JSON to stdout, then exit |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Success |
| `1` | Scan failed |

**Unlike `check`:** `info` has no `--verbose` or `--deps` flags — it always shows dependencies and never truncates.

---

## `resolve`

Resolve compatible versions for one or more packages from any ecosystem. Uses per-package version matching (fast) for direct resolution; full SAT solver with transitive walk is used by `lock`/`scan` commands.

**Usage:**

```bash
udr resolve numpy pandas scikit-learn           # PyPI (default ecosystem)
udr resolve react vue -e npm                     # npm ecosystem
udr resolve serde tokio -e crates                # Cargo ecosystem
udr resolve flask django --format json           # JSON output
udr resolve torch --interactive                  # manual conflict resolution
udr resolve numpy@pypi express@npm               # mixed ecosystems
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `packages` | (required) | One or more package names. Use `pkg@eco` syntax for non-default ecosystems |
| `-e, --ecosystem` | `pypi` | Default ecosystem: `pypi`, `npm`, `cargo`, `go`, `conda`, `maven`, `crates`, `nuget`, `rubygems` |
| `-f, --format` | `text` | Output format: `text` (rich table) or `json` |
| `-i, --interactive` | `False` | If SAT solver reports unsatisfiable, enter manual resolution mode |

**Package spec syntax:**

```
name                          → name, default ecosystem (pypi)
name@ecosystem                → name, specific ecosystem
@angular/core@npm             → scoped npm package (@angular/core)
```

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | All packages resolved |
| `1` | Resolution failed or no packages found |
| `130` | Cancelled by user (Ctrl+C) |

**CUDA behavior:** If the system has an NVIDIA GPU with CUDA, CUDA-tagged variants (e.g. `torch 2.1.2+cu121`) are automatically selected. See CUDA section below.

---

## `lock`

Auto-detect dependency manifests in a project directory, fetch metadata for all packages, scan the system, run SAT resolution, and write a `udr-lock.json` lock file. Optionally update manifests in-place with pinned versions.

**Usage:**

```bash
udr lock                                     # current directory
udr lock -d /path/to/project                 # specific project
udr lock -m requirements.txt                 # only process one manifest
udr lock --export Dockerfile                 # also export resolved deps
udr lock --dry-run                           # preview without writing
udr lock -y                                  # skip confirmation prompts
udr lock -i                                  # interactive manifest selection + conflict resolution
udr lock --json                              # output lock data as JSON to stdout
udr lock --cuda 12.1                         # override CUDA detection (useful on CPU-only CI)
udr lock -d ./myproject --cuda 11.8 --export requirements.txt
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `-d, --directory` | `.` | Project root directory to scan |
| `-m, --manifest` | (all) | Only process a specific manifest file (e.g. `requirements.txt`) |
| `--export` | (none) | Export resolved deps to a format (e.g. `Dockerfile`, `requirements.txt`) |
| `-y, --yes` | `False` | Update manifests in-place without prompting |
| `--dry-run` | `False` | Run resolution and show results but don't write any files |
| `-i, --interactive` | `False` | Select manifests manually + resolve conflicts interactively |
| `--cuda` | (auto) | Target CUDA version string (e.g. `12.1`, `11.8`). Overrides auto-detection |
| `--json` | `False` | Output lock data as JSON to stdout instead of writing file |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Success (lock file written, or `--json` output) |
| `1` | Failure (no manifests, no packages, resolution error, etc.) |
| `130` | Cancelled by user (Ctrl+C) |

**Lock file structure** (`udr-lock.json`):

```json
{
  "version": "2.0",
  "generated_at": "2026-06-28T12:00:00",
  "resolver": "sat",
  "system": {
    "os": "Linux 6.2.0",
    "python": "3.11.5",
    "cpu": "Intel(R) Xeon(R)",
    "gpu": "NVIDIA A100",
    "cuda": "12.1"
  },
  "manifests": ["requirements.txt"],
  "packages": {
    "torch": {
      "name": "torch",
      "ecosystem": "pypi",
      "resolved_version": "2.1.2+cu121",
      "cuda_variant": true,
      "cuda_version": "121",
      "original_constraint": ">=2.0",
      "source": "requirements.txt"
    }
  },
  "warnings": []
}
```

**Pipeline steps performed:**

1. **Detect manifests** — scans for `requirements.txt`, `pyproject.toml`, `package.json`, `Cargo.toml`, `Pipfile`, `environment.yml`, `Gemfile`, `go.mod`, `composer.json`
2. **Parse packages** — extracts name, ecosystem, constraint from each manifest
3. **Fetch metadata** — queries registry APIs for each package (versions, dependencies, system requirements)
4. **Scan system** — detects OS, CPU, GPU, CUDA, Python, runtimes
5. **Resolve** — SAT solver finds compatible versions across all packages and ecosystems
6. **Export** (optional) — generate `Dockerfile`, `requirements.txt`, etc.
7. **Lock** — write `udr-lock.json`
8. **Update manifests** (optional) — pin versions in original manifest files

---

## `scan`

Scan a remote GitHub repository or a local directory — same pipeline as `lock` but without needing to clone manually or change directories.

**Usage:**

```bash
udr scan --github https://github.com/user/repo          # scan remote repo
udr scan --github https://github.com/user/repo --branch develop
udr scan --directory /path/to/project                   # scan local path
udr scan --github https://github.com/user/repo --cuda 12.1
udr scan --github https://github.com/user/repo -y --export Dockerfile
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `--github` | (none) | GitHub repository URL (e.g. `https://github.com/user/repo`) |
| `--branch` | `main` | Git branch to scan (only with `--github`) |
| `--directory` | (none) | Local project directory path |
| `-y, --yes` | `False` | Update manifests without prompting |
| `--export` | (none) | Export resolved deps to a format (e.g. `Dockerfile`) |
| `--cuda` | (auto) | Target CUDA version string, overrides auto-detection |
| `--dry-run` | `False` | Preview without writing files |
| `-i, --interactive` | `False` | Interactive manifest selection + conflict resolution |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Success |
| `1` | Scan failed |
| `130` | Cancelled by user (Ctrl+C) |

**Notes:**
- Must provide exactly one of `--github` or `--directory`.
- `--github` downloads the repo as a zipball (no `git clone` needed), extracts to a temp directory, and deletes it after the command completes.
- This is equivalent to `git clone + cd repo + udr lock` in one step.

---

## `graph`

Display a dependency tree for one or more packages — shows direct and transitive dependencies without resolving conflicts.

**Usage:**

```bash
udr graph flask django                        # PyPI packages
udr graph numpy@pypi serde@crates             # mixed ecosystems
udr graph react -e npm                        # npm packages
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `packages` | (required) | One or more package names with optional `@ecosystem` suffix |
| `-e, --ecosystem` | `pypi` | Default ecosystem |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Success |
| `1` | Resolution failed or no packages resolved |
| `130` | Cancelled by user (Ctrl+C) |

---

## `verify`

Validate a lock file — checks that every pinned version still exists in its respective package registry.

**Usage:**

```bash
udr verify                              # uses udr-lock.json in current dir
udr verify path/to/custom-lock.json     # specific lock file
```

**Flags:**

| Argument/Flag | Default | Description |
|---|---|---|
| `lock_file` | `udr-lock.json` | Path to lock file (positional, optional) |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | All versions verified, or no packages in lock file |
| `1` | One or more packages have errors (missing versions, unavailable packages) |

**Error vs Warning:**
- **Warning** — package exists but has no resolved version (e.g. was unresolved)
- **Error** — version no longer exists in registry, or package not found at all

---

## `list-ecosystems`

List all 13 supported package ecosystems with display names.

**Usage:**

```bash
udr list-ecosystems                     # rich table output
udr list-ecosystems --json              # JSON array output
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `--json` | `False` | Output ecosystems as a JSON array |

**JSON output:**

```json
[
  {"name": "pypi", "display": "PyPI", "identifier": "pypi"},
  {"name": "npm", "display": "Npm", "identifier": "npm"}
]
```

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Always |

---

## `completion`

Generate shell completion scripts for bash, zsh, or fish.

**Usage:**

```bash
udr completion                    # auto-detect shell (requires shellingham)
udr completion bash               # bash completions
udr completion zsh                # zsh completions
udr completion fish               # fish completions
```

**Installing completions:**

```bash
# bash — source in ~/.bashrc
udr completion bash > /etc/bash_completion.d/udr

# zsh — save to a directory in $fpath
udr completion zsh > /usr/local/share/zsh/site-functions/_udr

# fish
udr completion fish > ~/.config/fish/completions/udr.fish
```

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Script generated successfully |
| `1` | Unsupported shell (when passed explicitly) |

---

## `update`

Re-resolve a single package and update its entry in the lock file. Useful when you want to upgrade a specific dependency without re-scanning everything.

**Usage:**

```bash
udr update flask                        # re-resolve flask in current project
udr update flask -d /path/to/project    # specific project
udr update flask -i                     # interactive conflict resolution
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `package` | (required) | Package name to re-resolve |
| `-d, --directory` | `.` | Project directory containing `udr-lock.json` |
| `-i, --interactive` | `False` | Interactive conflict resolution |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Package updated or already at latest version |
| `1` | Package not found in lock file, fetch failed, or resolution failed |
| `130` | Cancelled by user (Ctrl+C) |

---

## Package Spec Syntax

Use `name@ecosystem` to specify which ecosystem a package belongs to:

| Spec | Package | Ecosystem |
|---|---|---|
| `numpy` | numpy | pypi (default) |
| `numpy@pypi` | numpy | pypi |
| `@angular/core@npm` | @angular/core | npm |
| `express@npm` | express | npm |
| `serde@crates` | serde | crates |
| `torch@pypi` | torch | pypi |

The `@` delimiter splits on the **last** `@` so scoped npm packages (`@angular/core`) work correctly.

---

## CUDA / GPU Handling

The resolver is GPU-aware for PyPI packages. When a package has CUDA-tagged variants (e.g. `torch 2.1.2+cu121`, `torch 2.1.2+cu118`), the tool selects the best match based on the system's CUDA version.

### Auto-detection

The system scanner detects CUDA via:
1. `pynvml` (NVIDIA Management Library) — most reliable
2. `nvcc --version` — compiler version
3. `nvidia-smi` — driver-reported CUDA version

If none work, CUDA is reported as unavailable.

### Resolution behavior

| System CUDA | Behavior |
|---|---|
| Detected (e.g. `12.1`) | Best-matching CUDA variant selected (exact match preferred, closest lower version as fallback) |
| Detected but no variants available | CPU-only version used |
| **Not detected** | **CPU-only versions used. No CUDA variants selected.** |
| `--cuda` flag provided | Overrides auto-detection — forces CUDA-aware resolution |

### `--cuda` flag

On CPU-only machines (CI runners, cloud VMs, Colab), use `--cuda` to produce a lock file with GPU variants:

```bash
udr lock --cuda 12.1                     # resolve as if CUDA 12.1 is available
udr lock --cuda 11.8 --export Dockerfile # CUDA 11.8 with Docker export
udr scan --github <url> --cuda 12.1      # scan remote repo with GPU resolution
```

If CUDA variants exist but no GPU is detected (and `--cuda` was not provided), the tool issues a warning:

```
⚠ CUDA variant available for torch but no GPU detected
   Use --cuda <version> to target a specific CUDA version
⚠ CUDA variants exist but were not selected — resolution is CPU-only
```

### Lock file portability

The lock file stores the detected (or overridden) system info:
```json
"system": {
  "gpu": "NVIDIA A100",
  "cuda": "12.1"
}
```

Running `udr lock` on a GPU machine records GPU info. Running the lock file on a different machine doesn't trigger re-resolution — use `udr update` to re-resolve on a new machine. If the lock file was generated with `--cuda 12.1` on a CPU-only CI, the `system.gpu` field records the override for provenance.

---

## Exit Code Summary

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Error (resolution failed, file not found, invalid input, unsupported shell) |
| `130` | Cancelled by user (Ctrl+C) |

---

## Error Handling

All commands display errors in a formatted red panel:

```
╭────────────────────────────────────── Error ──────────────────────────────────────╮
│ Resolution failed: <message>                                                      │
╰────────────────────────────────────────────────────────────────────────────────────╯
```

Common error messages and their causes:

| Error | Likely Cause |
|---|---|
| `PackageLoader could not find a 'templates' directory` | Package installed without template data files. Run `pip install --upgrade ud-resolver` |
| `'brand'` / `'arch'` | System scanner failed to detect CPU info. Use `udr info --json` to debug |
| `No manifests found` | No recognized dependency files in the target directory |
| `No packages found in manifests` | Manifest files exist but are empty or unparseable |
| `Lock file not found` | Run `udr lock` first to generate `udr-lock.json` |
| `Package '{name}' not found in lock file` | The package doesn't exist in the lock file. Check spelling |
| `ModuleNotFoundError: No module named 'requests'` | (Fixed) `requests` was removed; internal GitHub download uses stdlib |
