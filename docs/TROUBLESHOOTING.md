# Troubleshooting

## Installation

### `z3-solver` fails to install

**Error:** `pip install z3-solver` fails with compilation errors.

**Solutions:**
```bash
# Install pre-built wheel (Linux x86_64)
pip install z3-solver

# If that fails, install from conda
conda install -c conda-forge z3-solver

# Or use the PubGrub solver instead (no C++ dependency)
pip install ud-resolver[pubgrub]
export USE_PUBGRUB_SOLVER=true
```

### `pubgrub-py` fails with Rust linker error

**Error:** `pip install pubgrub-py` fails on Rust compilation, typically `error: linking with `cc` failed`.

**Solutions:**
```bash
# Ensure gcc is available (not just rust-lld)
export CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER=gcc
pip install pubgrub-py

# On NixOS:
apt install gcc  # or your distro equivalent

# Fall back to pure-Python PubGrub (slower but works)
# The solver auto-detects if pubgrub-py is installed
```

### `ModuleNotFoundError: No module named 'some_dependency'`

**Cause:** The package was installed without optional extras.

**Solution:**
```bash
pip install --upgrade ud-resolver[all]
```

---

## CLI

### `udr: command not found`

```bash
# The venv is not activated
source venv/bin/activate
# Or install globally
pip install ud-resolver[z3,system]
```

### Resolution is slow

**Common causes:**
- First run (cold cache) — all registry data fetched fresh
- Go modules hit proxy latency (~2s per `.mod` fetch)
- Large BFS graph with many transitive deps

**Solutions:**
```bash
# Increase timeout
udr lock --timeout 300

# Pre-warm indexes
udr index build

# Increase concurrency (Go modules)
export GOMODULES_CONCURRENCY=30

# Reduce BFS batch size
export BFS_BATCH_SIZE=10

# Use existing lock files as version sources
# (go.sum, package-lock.json act as pre-resolved sources)
```

### `No manifests found`

UDR did not find any recognized dependency files in the target directory.

**Check:**
- Are you in the right directory?
- Does the directory contain a recognized manifest? See the full list in [CLI.md](CLI.md#lock).
- Use `udr lock -m requirements.txt` to specify a manifest explicitly.

### `No packages found in manifests`

Manifest files exist but are empty or could not be parsed.

**Check:**
- Manifest file has content (not blank)
- Content is in a parseable format (e.g. valid JSON for `package.json`)
- Use `udr lock --json` to see the raw parse output

### `Lock file not found`

The command requires a `udr.lock` file. Generate one with `udr lock`.

```bash
udr lock                    # generate lock file
udr verify                  # then verify it
```

### `Package '{name}' not found in lock file`

The package does not exist in the lock file.

**Check:**
- Spelling (case-sensitive for some ecosystems)
- Run `udr why --all` to list all packages in the lock file
- If it's a transitive dependency, it will still appear in the lock file

### `Resolution failed: the dependency graph is unsatisfiable`

No combination of versions satisfies all constraints. This is a genuine conflict.

**Diagnose:**
```bash
# See what went wrong
udr lock --json | grep resolution_error

# Use why to understand the chain
udr why <package>

# Try resolving with different constraints
udr resolve conflicting-pkg --json

# Interactive mode to explore the conflict space
udr lock --interactive
```

**Common causes:**
- Two packages require incompatible versions of the same transitive dependency
- A transitive dependency has no versions matching its own dependency constraints
- CUDA variant mismatch (e.g. `torch` with CUDA 12 but `nvidia-*` needs CUDA 11)

### `solver capacity exceeded`

The SAT variable count exceeded `SOLVER_MAX_VARIABLES` (default 50000). Common with packages that have very many versions.

**Solutions:**
```bash
# Increase the limit
export SOLVER_MAX_VARIABLES=100000

# Or reduce version count per package
export SOLVER_MAX_VERSIONS_PER_PKG=20
```

### `No compatible versions` for a package

The package exists in the registry but no version satisfies the constraint + system requirements.

**Causes:**
- Constraint is too tight (e.g. `flask==1.0.0` when only 2.x is available)
- System requirements filter out all versions (e.g. `requires_python>=3.12` but Python is 3.11)
- CUDA variant not available for the requested version

### `CUDA mismatch` warning

The resolver found CUDA variants but no GPU was detected and `--cuda` was not provided.

```bash
# Explicitly set CUDA version
udr lock --cuda 12.1

# Or accept CPU-only resolution (the warning is informational)
```

---

## API / Server

### Backend won't start

```bash
# Port already in use
lsof -i :8000
kill <pid>

# Missing dependencies
pip install ud-resolver[all]

# SECRET_KEY still default (saas mode)
export SECRET_KEY="$(openssl rand -hex 32)"
```

### `Address already in use`

```
Error: [Errno 98] Address already in use
```

```bash
# Use a different port
udr serve --port 8001

# Or kill the existing process
fuser -k 8000/tcp
```

### `429 Too Many Requests` (Rate limited)

The endpoint has a per-minute or per-hour rate limit. See [API.md](API.md) for endpoint-specific limits.

```bash
# Wait for the rate limit window to reset
# Rate limiter uses Redis (if configured) or in-memory fallback
```

If you hit rate limits frequently, set up Redis:

```bash
export REDIS_URL=redis://localhost:6379
udr serve
```

### `401 Unauthorized`

**Causes:**
- Missing `Authorization: Bearer <token>` header
- Missing `X-API-Key` header
- Expired JWT token (tokens expire — use `/auth/refresh`)
- `ENABLE_AUTH=true` and no credentials provided

**Solutions:**
```bash
# Check current auth mode
# If running locally without auth:
export ENABLE_AUTH=false
udr serve

# If using API key:
export API_KEY=my-key
curl -H "X-API-Key: my-key" http://localhost:8000/api/v1/system/info
```

### `SECRET_KEY` warning

```
SECRET_KEY is still the default value — set a strong random secret in production
```

```bash
export SECRET_KEY="$(openssl rand -hex 32)"
```

---

## Desktop App

### Blank screen on launch

**Causes:**
- Backend failed to start (port conflict, missing dependencies)
- Browser security blocking localhost requests

**Solutions:**
```bash
# Check if the backend is running
curl http://127.0.0.1:8000/api/v1/system/info

# Kill any existing udr process and restart
pkill -f udr
# Then relaunch the desktop app

# On Linux, check AppImage extraction
./udr-desktop-*.AppImage --appimage-extract
./squashfs-root/AppRun
```

### macOS "app is damaged" warning

```bash
xattr -c /Applications/udr-desktop.app
```

### Linux AppImage: "FUSE not available"

```bash
# Install FUSE
sudo apt install fuse       # Debian/Ubuntu
sudo pacman -S fuse2        # Arch

# Or extract and run directly
./udr-desktop-*.AppImage --appimage-extract
./squashfs-root/AppRun
```

### GPU not detected in System Info

The desktop app bundles `nvidia-ml-py` but it may not detect GPUs on all systems.

```bash
# Verify GPU detection independently
nvidia-smi

# If nvidia-smi works but desktop doesn't show GPU:
# Install nvidia-ml-py manually in the environment
```

---

## Docker

### Container exits immediately

```bash
# Check logs
docker logs udr-server

# Common causes:
# 1. Port already in use on host — use a different host port
docker run -p 8001:8000 udr-server

# 2. Volume permissions — ensure the mounted directory exists
mkdir -p ~/.cache/udr
docker run -v ~/.cache/udr:/home/user/.cache/udr udr-server
```

### Permission denied on cache volume

```bash
# The container runs as non-root user 1000:1000
chown -R 1000:1000 ~/.cache/udr
```

---

## Development

### Pre-commit hooks fail

```bash
# Reinstall hooks
pre-commit uninstall && pre-commit install

# Run on all files to verify
pre-commit run --all-files

# Skip hooks for a specific commit (emergency only)
git commit -m "..." --no-verify
```

### `ruff check` violations

```bash
# Auto-fix what ruff can fix
ruff check backend/ --fix

# Check what remains
ruff check backend/
```

### `mypy` type errors

```bash
# Run mypy on the backend
mypy backend/

# Common fixes:
# - Add type annotations to function signatures
# - Use `# type: ignore[<code>]` for third-party library calls
# - Add `assert isinstance(x, ...)` for narrowed types
```

### asyncio errors (`TimeoutError`, `Event loop closed`)

```bash
# Increase solver timeout
export SOLVER_TIMEOUT=300
udr lock

# If you see "Event loop is closed" in tests:
# Make sure pytest-asyncio is configured for async fixtures
```

### Test failures

```bash
# Run a single test to isolate
python -m pytest tests/unit/test_cli.py::test_name -v

# Re-run with full output
python -m pytest -x -v --tb=long

# Check if it's a network-dependent test
python -m pytest tests/unit/ -x --ignore=tests/e2e
```

---

## Test Commands

```bash
# Run all tests
python -m pytest

# Unit tests (3739)
python -m pytest tests/unit

# Integration tests (96)
python -m pytest tests/integration

# End-to-end tests (383)
python -m pytest tests/e2e

# With coverage (threshold: 58%)
python -m pytest --cov=backend --cov-report=term-missing --cov-fail-under=57

# Parallel
python -m pytest -n auto

# Specific ecosystem tests
python -m pytest tests/e2e/test_all_ecosystems.py -v
python -m pytest tests/e2e/test_api_all_ecosystems.py -v

# Cross-ecosystem tests
python -m pytest tests/unit/test_cross_eco_coverage.py -v

# Fuzz tests
python -m pytest tests/unit/test_constraint_fuzz.py -v
```
