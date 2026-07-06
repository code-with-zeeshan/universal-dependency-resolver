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
| `--offline` | Offline mode: use SQLite offline indexes + cached data; no network requests |
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
udr serve --log-level debug            # verbose logging
udr serve --workers 4                  # multiple worker processes
udr serve --ssl-keyfile key.pem --ssl-certfile cert.pem  # HTTPS
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8000` | Bind port |
| `--reload` | `False` | Enable hot-reload for development |
| `--mode` | `local` | `local` (no auth) or `saas` (JWT auth, rate limiting) |
| `--log-level` | `info` | Uvicorn log level: debug, info, warning, error, critical |
| `--workers` | `None` | Number of worker processes (auto-detected) |
| `--ssl-keyfile` | None | SSL key file path for HTTPS |
| `--ssl-certfile` | None | SSL certificate file path for HTTPS |

**Environment variables:**

| Variable | Default | Description |
|---|---|---|
| `SOLVER_TIMEOUT` | `120` | Total seconds for BFS+SAT resolution (used by `lock`/`scan`/`update`). ~80% of budget goes to Z3 solver (minimum 10s); rest for BFS dep discovery |
| `SCANNER_MAX_WORKERS` | `10` | Thread pool workers for parallel system scanning in `system_scanner.py` |
| `CACHE_TTL` | `3600` | Default cache TTL in seconds for package metadata |
| `CACHE_TTL_SHORT` | `300` | Cache TTL for rate-limited API endpoints (5 min default) |
| `CACHE_TTL_VERSIONS` | `600` | Cache TTL for package version listings |

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
udr check --cuda 12.1                  # simulate check for specific CUDA version
udr check --device cuda                # simulate check for specific compute device
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `-v, --verbose` | `False` | Show CPU architecture, runtime versions table |
| `--deps` | `False` | Show project core dependencies (from `pyproject.toml`) |
| `--json` | `False` | Output full system info as JSON to stdout, then exit |
| `--cuda` | `None` | Target CUDA version (e.g. 12.1) — auto-detected if omitted |
| `--device` | `None` | Target compute device: `cpu`, `cuda`, or `mps` — auto-detected if omitted |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Success |
| `1` | Scan failed |

---

## `resolve`

Resolve compatible versions for one or more packages from any ecosystem.

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
| `-e, --ecosystem` | `pypi` | Default ecosystem (used for packages without `@ecosystem` suffix) |
| `-f, --format` | `text` | Output format: `text` (rich table) or `json` |
| `-i, --interactive` | `False` | If SAT solver reports unsatisfiable, enter manual resolution mode |
| `--cuda` | `None` | Target CUDA version string (e.g. `12.1`, `11.8`). Auto-detected if omitted |
| `--device` | `None` | Target compute device: `cpu`, `cuda` (NVIDIA GPU), or `mps` (Apple Silicon). Auto-detected if omitted |
| `--timeout` | `None` | Resolution timeout in seconds (default: 120, from `SOLVER_TIMEOUT` env var) |

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

---

## `lock`

Auto-detect dependency manifests in a project directory, fetch metadata for all packages, scan the system, run SAT resolution, and write a `udr.lock` lock file. Optionally update manifests in-place with pinned versions.

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
udr lock -r                                  # write readable report file alongside lock file
udr lock --cuda 12.1                         # override CUDA detection
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `-d, --directory` | `.` | Project root directory to scan |
| `-m, --manifest` | `None` | Only process a specific manifest file (e.g. `requirements.txt`); all manifests if omitted |
| `--export` | `None` | Export resolved deps to a format (e.g. `Dockerfile`, `requirements.txt`) |
| `-y, --yes` | `False` | Update manifests in-place without prompting |
| `--dry-run` | `False` | Run resolution and show results but don't write any files |
| `-i, --interactive` | `False` | Select manifests manually + resolve conflicts interactively |
| `--cuda` | `None` | Target CUDA version string (e.g. `12.1`, `11.8`). Auto-detected if omitted |
| `--device` | `None` | Target compute device: `cpu`, `cuda`, or `mps`. Auto-detected if omitted |
| `--json` | `False` | Output lock data as JSON to stdout instead of writing file |
| `-r, --report` | `False` | Write readable report file (`udr-lock-report.txt`) alongside lock file |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Success (lock file written, or `--json` output) |
| `1` | Failure (no manifests, no packages, resolution error, etc.) |
| `130` | Cancelled by user (Ctrl+C) |

**Lock file structure** (`udr.lock`):

```json
{
  "version": "2.0",
  "generated_at": "2026-07-05T12:00:00",
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
      "direct": true,
      "cuda_variant": true,
      "cuda_version": "121",
      "original_constraint": ">=2.0",
      "source": "requirements.txt",
      "resolution_hash": "abc123...",
      "depends_on": {
        "pypi": {
          "sympy": ">=1.0",
          "jinja2": ">=2.0"
        }
      }
    }
  },
  "warnings": []
}
```

**Pipeline steps performed:**

1. **Detect manifests** — scans for recognized dependency files (see manifest list below)
2. **Parse packages** — extracts name, ecosystem, constraint from each manifest
3. **Fetch metadata** — queries registry APIs for each package (versions, dependencies, system requirements)
4. **Scan system** — detects OS, CPU, GPU, CUDA, Python, runtimes
5. **Resolve** — SAT solver finds compatible versions across all packages and ecosystems
6. **Export** (optional) — generate `Dockerfile`, `requirements.txt`, etc.
7. **Lock** — write `udr.lock`
8. **Update manifests** (optional) — pin versions in original manifest files

**Recognized manifests and lock files:**

| File | Ecosystem | Type |
|---|---|---|
| `requirements.txt`, `requirements.in`, `*-requirements.txt` | pypi | Manifest |
| `Pipfile` | pypi | Manifest |
| `pyproject.toml` | pypi | Manifest |
| `Pipfile.lock` | pypi | Lock |
| `poetry.lock` | pypi | Lock |
| `uv.lock` | pypi | Lock |
| `package.json` | npm | Manifest |
| `package-lock.json` | npm | Lock |
| `yarn.lock` | npm | Lock |
| `pnpm-lock.yaml` | npm | Lock |
| `Cargo.toml` | crates | Manifest |
| `Cargo.lock` | crates | Lock |
| `go.mod` | gomodules | Manifest |
| `environment.yml`, `environment.yaml` | conda | Manifest |
| `Gemfile` | rubygems | Manifest |
| `Gemfile.lock` | rubygems | Lock |
| `composer.json` | packagist | Manifest |
| `composer.lock` | packagist | Lock |
| `pubspec.yaml` | pub | Manifest |
| `build.gradle`, `build.gradle.kts` | gradle | Manifest |
| `Package.swift` | swift | Manifest |
| `Package.resolved` | swift | Lock |
| `mix.exs` | hex | Manifest |
| `mix.lock` | hex | Lock |
| `*.cabal` | haskell | Manifest |
| `pom.xml` | maven | Manifest |
| `Podfile`, `Podfile.lock` | cocoapods | Manifest |
| `packages.config` | nuget | Manifest |
| `Brewfile`, `Brewfile.lock.json` | homebrew | Manifest |
| `apt-packages.txt` | apt | Manifest |
| `apk-packages.txt` | apk | Manifest |
| `udr.lock` | — | Self (UDR lock file) |

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
| `--github` | `None` | GitHub repository URL (e.g. `https://github.com/user/repo`) |
| `--branch` | `main` | Git branch to scan (only with `--github`) |
| `--directory` | `None` | Local project directory path |
| `-m, --manifest` | `None` | Only process a specific manifest file; all manifests if omitted |
| `-y, --yes` | `False` | Update manifests without prompting |
| `--export` | none | Export resolved deps to a format (e.g. `Dockerfile`) |
| `--json` | `False` | Output lock data as JSON |
| `--cuda` | `None` | Target CUDA version string. Auto-detected if omitted |
| `--device` | `None` | Target compute device: `cpu`, `cuda`, or `mps`. Auto-detected if omitted |
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

---

## `graph`

Display a dependency tree for one or more packages — shows direct and transitive dependencies.

**Usage:**

```bash
udr graph flask django                        # PyPI packages
udr graph numpy@pypi serde@crates             # mixed ecosystems
udr graph react -e npm                        # npm packages
udr graph torch --cuda 12.1                   # with CUDA variant selection
udr graph torch --json                        # JSON output
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `packages` | (required) | One or more package names with optional `@ecosystem` suffix |
| `-e, --ecosystem` | `pypi` | Default ecosystem |
| `--json` | `False` | Output as JSON |
| `--cuda` | `None` | Target CUDA version — auto-detected if omitted |
| `--device` | `None` | Target compute device: `cpu`, `cuda`, or `mps` — auto-detected if omitted |

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
udr verify                              # uses udr.lock in current dir
udr verify path/to/custom-lock.json     # specific lock file
```

**Flags:**

| Argument/Flag | Default | Description |
|---|---|---|
| `lock_file` | `udr.lock` | Path to lock file (positional, optional) |
| `--json` | `False` | Output as JSON |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | All versions verified, or no packages in lock file |
| `1` | One or more packages have errors (missing versions, unavailable packages) |

---

## `list-ecosystems`

List all supported package ecosystems with display names.

**Usage:**

```bash
udr list-ecosystems                     # rich table output
udr list-ecosystems --json              # JSON array output
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `--json` | `False` | Output ecosystems as a JSON array |

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

**API equivalent:** `GET /api/v1/completion/{shell}` returns the same scripts as `text/plain`.

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Script generated successfully |
| `1` | Unsupported shell (when passed explicitly) |

---

## `update`

Re-resolve a single package and update its entry in the lock file.

**Usage:**

```bash
udr update flask                        # re-resolve flask in current project
udr update flask -d /path/to/project    # specific project
udr update flask -i                     # interactive conflict resolution
udr update torch --cuda 12.1            # update with CUDA override
udr update flask --dry-run              # preview changes without writing
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `package` | (required) | Package name to re-resolve |
| `-d, --directory` | `.` | Project directory containing `udr.lock` |
| `-i, --interactive` | `False` | Interactive conflict resolution |
| `--dry-run` | `False` | Show what would be updated without modifying the lock file |
| `--cuda` | `None` | Target CUDA version — auto-detected if omitted |
| `--device` | `None` | Target compute device: `cpu`, `cuda`, or `mps` — auto-detected if omitted |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Package updated or already at latest version |
| `1` | Package not found in lock file, fetch failed, or resolution failed |
| `130` | Cancelled by user (Ctrl+C) |

---

## `auth`

Manage DB-backed API keys for the UDR API server. Requires a running server with `ENABLE_AUTH=true` and a connected database.

**Usage:**

```bash
udr auth create --name my-key --role admin
udr auth revoke 1
udr auth list
```

**Subcommands:**

### `auth create`

| Flag | Default | Description |
|---|---|---|
| `--name` | `cli-generated` | Human-readable name for the key |
| `--role` | `read-only` | `admin`, `read-write`, or `read-only` |
| `--description` | — | Optional description |

### `auth revoke`

| Argument | Description |
|---|---|
| `key_id` | ID of the key to revoke (required, positional) |

### `auth list`

No flags. Displays a table of all API keys with ID, name, role, active status, last used, and usage count.

---

## `index`

Manage offline SQLite indexes for local package resolution. Indexes are stored at
`~/.cache/udr/indexes/{ecosystem}.db`.

**Subcommands:**

### `index pull`

Download pre-built SQLite indexes from a remote URL.

```bash
udr index pull https://indexes.udr.dev       # pull all available indexes
udr index pull https://indexes.udr.dev -e pypi  # single ecosystem
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `url` | (required) | Base URL for index download (expects `index.json` manifest + `{eco}.db` files) |
| `-e, --ecosystem` | `None` | Only pull index for this ecosystem |

### `index build`

Build an offline SQLite index from resolved packages in `udr.lock` or a comma-separated
package list. Fetches version + dependency data from registries and stores locally.

```bash
udr index build                             # build from udr.lock in cwd
udr index build -d /path/to/project          # build from lock file in project
udr index build --packages flask,requests    # build index for specific packages
udr index build --packages react -e npm      # build index for npm packages
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `--packages` | `""` | Comma-separated package names to index (uses `--ecosystem`) |
| `-e, --ecosystem` | `pypi` | Ecosystem for `--packages` |
| `-d, --directory` | cwd | Directory containing `udr.lock` |

### `index status`

Show which ecosystems have local indexes available, with package/version counts.

```bash
udr index status                            # rich table output
udr index status --json                     # JSON output
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `--json` | `False` | Output as JSON |

**Integration**: When `--offline` is set, the resolver queries the SQLite index instead
of making network calls. Use `udr index build` after `udr lock` to cache resolved
packages for offline use.

**API equivalents:**
| CLI | API |
|---|---|
| `udr index status` | `GET /api/v1/index/status` |
| `udr index pull <url>` | `POST /api/v1/index/pull` |
| `udr index build` | `POST /api/v1/index/build` |

---

## `install`

Install all **direct** dependencies from the lock file using their native package managers.

**Usage:**

```bash
udr install                              # install all direct deps from udr.lock
udr install -d /path/to/project          # project directory with lock file
udr install --lock-file path/to/lock.json  # custom lock file path
udr install -e npm                       # only install npm packages
udr install --dry-run                    # show install plan without executing
udr install -y                           # skip confirmation prompt
udr install --restore                    # restore mode (all packages)
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `-d, --directory` | `.` | Project directory containing `udr.lock` |
| `-l, --lock-file` | `None` | Path to lock file (default: `<directory>/udr.lock`) |
| `-e, --ecosystem` | `None` | Only install packages from this ecosystem; all ecosystems if omitted |
| `-n, --dry-run` | `False` | Show install plan without running commands |
| `-y, --yes` | `False` | Skip confirmation prompt |
| `--restore` | `False` | Restore mode — alias for install (kept for compatibility) |
| `--cuda` | `None` | CUDA version to target (e.g. 121 for cu121 wheels) |

**Supported installers (direct deps only):**

| Ecosystem | Command |
|---|---|
| `pypi` | `pip install pkg==ver` |
| `npm` | `npm install pkg@ver` |
| `crates` | `cargo add pkg@ver` |
| `gomodules` | `go get pkg@ver` |
| `conda` | `conda install pkg==ver` |
| `rubygems` | `gem install pkg==ver` |
| `packagist` | `composer require pkg==ver` |
| `pub` | `dart pub add pkg:ver` |
| `nuget` | `dotnet add package pkg --version ver` |
| `cocoapods` | `pod install` (uses Podfile) |
| `maven` | `mvn dependency:copy-dependencies` |
| `homebrew` | `brew install pkg` |
| `hex` | `mix deps.update pkg` |
| `swift` | `swift package resolve` |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | All packages installed (or dry-run completed) |
| `1` | No packages found, no installer known, or install failed |

---

## `why`

Explain why a package version was selected — show the dependency chain from the lock file.

**Usage:**

```bash
udr why flask                          # explain flask version in current project
udr why flask -d /path/to/project      # specific project
udr why flask --json                   # JSON output
udr why --all                          # explain all packages
udr why --all --json                   # all packages as JSON array
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `package` | (optional with `--all`) | Package name to explain |
| `-a, --all` | `false` | Show info for all packages |
| `-d, --directory` | `.` | Project directory with lock file |
| `--json` | `False` | Output as JSON |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Success |
| `1` | Package not found in lock file |

---

## `outdated`

List packages with newer versions available in their respective registries.

**Usage:**

```bash
udr outdated                           # check all packages in current project
udr outdated -d /path/to/project       # specific project
udr outdated --json                    # JSON output
udr outdated -e npm                    # only check npm packages
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `-d, --directory` | `.` | Project directory with lock file |
| `--json` | `False` | Output as JSON |
| `-e, --ecosystem` | `None` | Only check packages from this ecosystem; all ecosystems if omitted |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Success (checked all packages) |
| `1` | No lock file found or no packages |

---

## `diff`

Compare two lock files and show version differences.

**Usage:**

```bash
udr diff old.lock new.lock             # compare two lock files
udr diff old.lock new.lock --json      # JSON output
```

**Flags:**

| Argument/Flag | Default | Description |
|---|---|---|
| `lock_file_a` | (required) | First lock file path |
| `lock_file_b` | (required) | Second lock file path |
| `--json` | `False` | Output as JSON |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Success |
| `1` | Error reading lock files |

---

## `search`

Search for packages across ecosystems in registries.

**Usage:**

```bash
udr search numpy                        # search all ecosystems
udr search numpy --ecosystems pypi      # search only pypi
udr search numpy --json                 # JSON output
udr search numpy --limit 50             # max results per ecosystem
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `query` | (required) | Search query string |
| `--ecosystems` | `None` | Comma-separated ecosystems (e.g. `pypi,npm`); all ecosystems if omitted |
| `--limit` | `20` | Max results per ecosystem (1–100) |
| `--json` | `False` | Output as JSON |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Results found |
| `1` | No results or search failed |

---

## `details`

Show detailed package info — versions, dependencies, and metadata from the registry.

**Usage:**

```bash
udr details numpy                       # show numpy details (pypi)
udr details react -e npm                # show react details (npm)
udr details serde -e crates --json      # JSON output
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `package` | (required) | Package name |
| `-e, --ecosystem` | `pypi` | Ecosystem |
| `--json` | `False` | Output as JSON |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | Success |
| `1` | Package not found or fetch failed |

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

## CLI ↔ API Mapping

Every CLI subcommand has a corresponding REST API endpoint when `udr serve` is running:

| CLI Command | API Endpoint | Method | Notes |
|---|---|---|---|
| `udr serve` | — | — | Starts the API server itself |
| `udr check` | `/api/v1/system/info` | GET | System info + health check |
| `udr resolve` | `/api/v1/packages/resolve` | POST | Same request/response shape |
| `udr lock` | `/api/v1/generate-lock` | POST | API requires pre-processed package list |
| `udr lock --json` | `/api/v1/generate-lock` | POST | Same output shape |
| `udr lock --export` | `/api/v1/packages/export` | POST | Export resolved deps |
| `udr lock -r/--report` | — | — | CLI-only: writes local report file |
| `udr lock -m/--manifest` | — | — | CLI-only: local manifest filtering |
| `udr lock --dry-run` | — | — | CLI-only: preview without writing |
| `udr lock -i/--interactive` | — | — | CLI-only: interactive TUI mode |
| `udr lock -y/--yes` | — | — | CLI-only: auto-confirm |
| `udr graph` | `/api/v1/graph` | POST | Same request/response shape |
| `udr verify` | `/api/v1/verify` | POST | Same request/response shape |
| `udr list-ecosystems` | `/api/v1/packages/ecosystems` | GET | Same response shape |
| `udr update` | `/api/v1/update` | POST | Same request/response shape |
| `udr install` | `/api/v1/install-commands` | POST | API generates commands, doesn't execute |
| `udr install --restore` | `/api/v1/restore-commands` | POST | Same as install, but for all packages |
| `udr scan --github` | `/api/v1/scan/github` | POST | Same |
| `udr scan --directory` | `/api/v1/scan/local` | POST | Same |
| `udr why` | `/api/v1/why` | POST | Same |
| `udr outdated` | `/api/v1/outdated` | POST | Same |
| `udr diff` | `/api/v1/diff` | POST | Same |
| `udr search` | `/api/v1/packages/search` | GET | Same response shape |
| `udr details` | `/api/v1/packages/{eco}/{name}/details` | GET | Same response shape |
| `udr index pull` | `/api/v1/index/pull` | POST | Downloads SQLite index from URL |
| `udr index build` | `/api/v1/index/build` | POST | Builds index from package data |
| `udr index status` | `/api/v1/index/status` | GET | Shows local offline index status |
| `udr completion` | `/api/v1/completion/{shell}` | GET | Returns shell completion script as text/plain |

**Key differences:**
- The API returns JSON only; CLI supports `--json`, text tables, and interactive TUI modes.
- CLI `lock` does **manifest detection + file I/O** locally; the API `generate-lock` endpoint accepts pre-parsed package data.
- CLI `install` executes native package manager commands; the API only returns the commands to run.
- CLI `check` includes project-local dependency info from `pyproject.toml`; the API returns system info only.

---

## Error Handling

All commands display errors in a formatted red panel:

```
╭────────────────────────────────────── Error ──────────────────────────────────────╮
│ Resolution failed: <message>                                                      │
╰───────────────────────────────────────────────────────────────────────────────────╯
```

Common error messages and their causes:

| Error | Likely Cause |
|---|---|
| `PackageLoader could not find a 'templates' directory` | Package installed without template data files. Run `pip install --upgrade ud-resolver` |
| `No manifests found` | No recognized dependency files in the target directory |
| `No packages found in manifests` | Manifest files exist but are empty or unparseable |
| `Lock file not found` | Run `udr lock` first to generate `udr.lock` |
| `Package '{name}' not found in lock file` | The package doesn't exist in the lock file. Check spelling |
| `ModuleNotFoundError: No module named 'requests'` | (Fixed) `requests` was removed; internal GitHub download uses stdlib |
