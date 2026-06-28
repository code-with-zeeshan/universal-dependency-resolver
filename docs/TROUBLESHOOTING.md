# Troubleshooting

## Installation

### `pip install ud-resolver` fails

- Make sure you have Python 3.11 – 3.13 installed
- On Linux, you may need `python3-dev` or `python3.12-dev` for compiling native extensions
- Try `pip install --upgrade pip` first
- If Z3 fails to install, try `pip install z3-solver` first, then `pip install ud-resolver`

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
- Supported: requirements.txt, package.json, Cargo.toml, pyproject.toml, build.gradle, pom.xml, environment.yml, CMakeLists.txt, Dockerfile, and more
- Use `--manifest path/to/file` to specify explicitly

## API Server

### Port already in use

```bash
lsof -i :8000
kill <PID>
```

Or use a different port: `udr serve --port 8001`

### Database errors

```bash
# SQLite: delete the database file to reset
rm udr.db

# Check DATABASE_URL in environment
echo $DATABASE_URL   # default: sqlite:///./udr.db
```

### 429 Too Many Requests

Rate limits are per-endpoint:

- Search: 60/min
- Resolve: 10/min
- Export: 20/min

Wait for reset or adjust in settings.

### Auth errors

Auth is **disabled by default**. To enable: set `ENABLE_AUTH=true` and configure `SECRET_KEY` in `.env`.

## Desktop App

### Backend fails to start

- Check the error dialog for details
- Ensure Python 3.11+ is on PATH (if not using PyInstaller binary)
- On Windows, antivirus may block the PyInstaller binary — add an exclusion

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

## Tests

```bash
# Run all tests
python -m pytest tests/ -q

# Run with output
python -m pytest tests/ -v
```

Integration tests default to SQLite. Set `DATABASE_URL=postgresql://...` to test against PostgreSQL. Redis is optional — tests without it will skip Redis-dependent tests automatically.

## Getting help

- Open a [GitHub Issue](https://github.com/code-with-zeeshan/universal-dependency-resolver/issues)
- Check the Swagger UI at `http://localhost:8000/api/v1/docs`
