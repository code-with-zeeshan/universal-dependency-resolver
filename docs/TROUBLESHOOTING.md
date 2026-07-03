# Troubleshooting Guide

Common errors and solutions when working with the Universal Dependency Resolver.

## Installation

### `z3-solver` fails to install

```
ERROR: Could not find a version that satisfies the requirement z3-solver
```

**Cause**: Z3 is a native library that requires a C++ compiler on some platforms.

**Solution**:

```bash
# Ubuntu/Debian
sudo apt-get install build-essential

# macOS
xcode-select --install

# Windows — install Microsoft C++ Build Tools
```

Or use a pre-built wheel from a third-party index:

```bash
pip install z3-solver --only-binary=:all:
```

### `pkg-config` not found

```
Package 'python3' requires pkg-config
```

**Cause**: Some Python packages need `pkg-config` at build time.

**Solution**:

```bash
# Ubuntu/Debian
sudo apt-get install pkg-config

# macOS
brew install pkg-config

# Fedora
sudo dnf install pkgconf-pkg-config
```

### `pip install ud-resolver` fails

- Make sure you have Python 3.11 – 3.13 installed
- On Linux, you may need `python3-dev` or `python3.12-dev` for compiling native extensions
- Try `pip install --upgrade pip` first
- If Z3 fails to install, try `pip install z3-solver` first, then `pip install ud-resolver`

## Runtime Errors

### `ModuleNotFoundError: No module named 'backend'`

```text
ModuleNotFoundError: No module named 'backend'
```

**Cause**: The package is not installed in the current Python environment.

**Solution**:

```bash
pip install -e ".[dev,system,postgres]"
```

### `z3` import error

```text
ImportError: libz3.so: cannot open shared object file
```

**Cause**: The Z3 shared library is not on the library path.

**Solution**:

```bash
# Linux
export LD_LIBRARY_PATH=$(python3 -c "import z3; import os; print(os.path.dirname(z3.__file__))")/lib:$LD_LIBRARY_PATH

# macOS
export DYLD_LIBRARY_PATH=$(python3 -c "import z3; import os; print(os.path.dirname(z3.__file__))")/lib:$DYLD_LIBRARY_PATH
```

### `SECRET_KEY` not set

```text
ValueError: SECRET_KEY environment variable is required when ENABLE_AUTH=true
```

**Cause**: Authentication is enabled but no secret key was provided.

**Solution**:

```bash
export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(48))")
udr serve
```

## CLI

### `udr` command not found

- Make sure your Python Scripts/bin directory is on PATH:
  - Linux/macOS: `$(python3 -m site --user-base)/bin`
  - Windows: `%APPDATA%\Python\Scripts`
- Or run as module: `python -m backend.cli resolve ...`

### Resolution is slow

- First resolution fetches data from remote registries — this is normal
- Subsequent resolutions are cached (DictCache by default, TTL configurable)
- Consider using `[system]` extra for local system scanning

### `lock` command finds no manifests

- `udr lock` scans the current directory for manifest files
- Supported: requirements.txt, pyproject.toml, Pipfile, Pipfile.lock, package.json, package-lock.json, yarn.lock, pnpm-lock.yaml, Cargo.toml, Cargo.lock, go.mod, environment.yml, Gemfile, composer.json, pubspec.yaml, pom.xml, Podfile, Podfile.lock, packages.config, Brewfile, apt-packages.txt, apk-packages.txt, and more
- Use `--manifest path/to/file` to specify explicitly

## API / Server

### Backend won't start in Desktop app

```text
Backend server could not be started.
```

**Cause**: The `udr-backend` binary is missing or incompatible.

**Solution**:

1. Check `~/.udr/backend-bin/` exists and contains `udr-backend`
2. Run `udr serve` directly to verify the Python backend works
3. On Linux, run `chmod +x ~/.udr/backend-bin/udr-backend`
4. On Windows, add the directory to Windows Defender exclusions
5. Reinstall the desktop app

### Port already in use

```text
Address already in use
```

**Cause**: Another process is already using port 8000 (or the configured port).

**Solution**:

```bash
# Find the process
lsof -i :8000

# Kill it
kill -9 <PID>

# Or use a different port
udr serve --port 8001
```

### Redis connection refused

```text
Error connecting to Redis: Connection refused
```

**Cause**: Redis is not running or the URL is misconfigured.

**Solution**:

```bash
# Start Redis via Docker
docker compose up -d redis

# Or check the URL
echo $UDR_REDIS_URL  # Should be redis://localhost:6379/0
```

### Rate limiter falls back to in-memory store

```text
WARNING: Redis connection failed. Falling back to in-memory rate limiter.
```

**Cause**: Redis is not available and the rate limiter falls back to an in-memory store (`slowapi.Limiter` with no `storage_uri`).

**Impact**: In-memory rate limiting does **not** work across multiple workers or processes. Each worker maintains its own counter, so a client can exceed the intended global limit by distributing requests across workers.

**Solution**:
- Ensure Redis is running and `REDIS_URL` is correctly configured
- If running behind a load balancer, add **sticky sessions** (session affinity) so each client hits the same worker
- For single-worker deployments (default `udr serve` or desktop mode), the in-memory store is acceptable
- To disable rate limiting entirely:
  ```bash
  udr serve --rate-limit-enabled=false
  ```

### Rate limiting too aggressive / 429 Too Many Requests

```text
Rate limit exceeded: 30 requests per 60 seconds
```

Rate limits are per-endpoint:

- Search: 60/min
- Resolve: 10/min
- Export: 20/min

**Solution**:

```bash
# Disable rate limiting
udr serve --rate-limit-enabled=false

# Or increase limits
export UDR_RATE_LIMIT="100/minute"
udr serve
```

### Database errors

```bash
# SQLite: delete the database file to reset
rm udr.db

# Check DATABASE_URL in environment
echo $DATABASE_URL   # default: sqlite:///./udr.db
```

Integration tests default to SQLite. Set `DATABASE_URL=postgresql://...` to test against PostgreSQL.

### Auth errors

Auth is **disabled by default**. To enable: set `ENABLE_AUTH=true` and configure `SECRET_KEY` in `.env`.

## Resolution Issues

### "SAT solver timed out"

```text
Solver did not find a solution within timeout
```

**Cause**: The dependency graph is too complex to resolve within the time limit.

**Solution**:

```bash
# Increase the timeout
export UDR_SOLVER_TIMEOUT=120
udr resolve requests numpy torch

# Or reduce the number of packages
udr resolve requests numpy
```

### "No versions found" for a package

```text
No versions found for package 'my-package'
```

**Cause**: The package doesn't exist in the specified ecosystem, or the registry is unreachable.

**Solution**:

1. Check the package name and ecosystem spelling
2. Verify the registry is accessible:
   ```bash
   # e.g., for PyPI
   curl https://pypi.org/pypi/my-package/json
   ```
3. Set HTTP proxy if behind a firewall:
   ```bash
   export HTTP_PROXY=http://proxy:8080
   export HTTPS_PROXY=http://proxy:8080
   ```

### CUDA version mismatch

```text
Warning: Requested CUDA 12.1 but resolved CUDA 13.0 packages
```

**Cause**: The SAT solver found CUDA 13 packages which are backward-compatible with CUDA 12.x drivers, but the exact minor version was not available.

**Solution**: This is typically safe — CUDA 13 packages work with CUDA 12.x drivers. To force a specific version:

```bash
udr lock --cuda 12.1 --force-exact-cuda
```

## Desktop App

### Backend fails to start

- Check the error dialog for details
- Ensure Python 3.11+ is on PATH (if not using PyInstaller binary)
- On Windows, antivirus may block the PyInstaller binary — add an exclusion

### Electron window shows blank/white screen

**Cause**: The preload script failed or an unhandled error occurred in the renderer.

**Solution**:

1. Open Developer Tools (`Ctrl+Shift+I`) and check the Console tab
2. Check `~/.udr/udr-desktop.log` for errors
3. Restart the desktop app
4. Reinstall if the problem persists

### Tray icon not appearing

**Cause**: Missing tray icon asset or Linux desktop environment quirk.

**Solution**:

- On GNOME, install `gnome-shell-extension-appindicator`:
  ```bash
  sudo apt-get install gnome-shell-extension-appindicator
  ```
- Restart GNOME Shell (`Alt+F2`, type `r`, Enter)
- The app still works — the tray is cosmetic

### Auto-update fails

```text
Error: Cannot find latest version
```

**Cause**: `electron-updater` cannot reach the GitHub releases page, or the app is not signed.

**Solution**:

1. Check internet connectivity
2. Verify the app was installed from the official release (not built from source)
3. On macOS, ensure the app is not quarantined:
   ```bash
   xattr -dr com.apple.quarantine /Applications/UDR.app
   ```

### macOS: "app is damaged" or Gatekeeper blocks it

- Right-click → Open, or
- System Settings → Privacy & Security → "Open Anyway"

### Linux: AppImage doesn't run

```bash
# Install FUSE
sudo apt install fuse  # Debian/Ubuntu

# Or extract and run directly
./UDR-*.AppImage --appimage-extract
./squashfs-root/AppRun
```

## Docker

### Container exits immediately

```text
udr exited with code 0
```

**Cause**: The default command is `udr --help`. Use `serve` explicitly.

**Solution**:
```bash
docker run ud-resolver:latest serve --host 0.0.0.0 --port 8000
```

### Permission denied writing to volume

```text
PermissionError: [Errno 13] Permission denied: '/home/udr/data'
```

**Cause**: The container runs as `udr` user (UID 1000) but the host directory is owned by root.

**Solution**:
```bash
# On the host
mkdir -p ./data
chown -R 1000:1000 ./data
```

## Development

### Pre-commit hooks fail

```text
ruff.....................................................................Failed
```

**Cause**: The linter found issues in staged files.

**Solution**:

```bash
# Auto-fix what ruff can fix
ruff check --fix

# Re-stage and retry
git add -A
git commit -m "message"
```

### Tests fail with asyncio error

```text
RuntimeError: asyncio.run() cannot be called from a running event loop
```

**Cause**: Test is not properly configured for async testing.

**Solution**: Install with dev dependencies and use pytest-asyncio:

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

### Mypy reports errors that seem wrong

**Cause**: Mypy strict mode catches many valid issues that are safe to ignore in practice.

**Solution**: Add `# type: ignore[error-code]` to suppress specific errors. Common codes:

| Code | Meaning |
|------|---------|
| `arg-type` | Argument type mismatch |
| `return-value` | Return type mismatch |
| `union-attr` | Attribute not on all union members |
| `type-arg` | Missing generic type parameter |
| `assignment` | Type mismatch in assignment |
| `call-overload` | Call doesn't match any overload |

### Ruff auto-fix changes too much

**Cause**: Ruff's `--fix` applies safe fixes automatically, which may change formatting preferences.

**Solution**: Review changes before committing:

```bash
ruff check --diff   # Preview changes
ruff format --check --diff   # Preview formatting
```

## Tests

```bash
# Run all tests
python -m pytest tests/ -q

# Run with output
python -m pytest tests/ -v
```

Redis is optional — tests without it will skip Redis-dependent tests automatically.

## Getting help

If none of these solutions help, please open an issue at:

https://github.com/code-with-zeeshan/universal-dependency-resolver/issues

Include:
- The full error message
- Your OS and Python version (`python --version`)
- The command you ran
- Output of `udr --version`
- Whether you're using the CLI, API, or Desktop app

Also check the Swagger UI at `http://localhost:8000/api/v1/docs`.
