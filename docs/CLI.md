# CLI Reference

## Usage

```bash
udr <command> [options]
```

Entry point: `udr` (from `pyproject.toml` `[project.scripts]`).

## Commands

### `serve`

Start the API server.

```bash
udr serve                  # http://127.0.0.1:8000
udr serve --host 0.0.0.0   # bind all interfaces
udr serve --port 9000      # custom port
udr serve --reload         # auto-reload on file changes (development)
```

### `check`

Check system compatibility and show project dependencies.

```bash
udr check                  # show system info (OS, CPU, GPU, Python, etc.)
udr check --deps           # show project core dependencies
udr check --json           # JSON output
udr check -v               # verbose output
```

### `resolve`

Resolve dependencies for one or more packages.

```bash
udr resolve numpy pandas scikit-learn
udr resolve react vue -e npm
udr resolve flask django --format json
```

| Flag | Description |
|---|---|
| `PACKAGES` | Package names using `pkg@ecosystem` syntax (e.g. `numpy@pypi`, `express@npm`) |
| `-e, --ecosystem` | Default ecosystem for packages without `@ecosystem` suffix |
| `-f, --format` | Output format: `text` (default) or `json` |
| `--interactive` | Interactive mode for resolving conflicts |

### `info`

Show detailed system information and project dependencies.

```bash
udr info              # full system info
udr info --json       # JSON output
```

### `lock`

Auto-detect manifests, resolve all dependencies, write a lock file (`udr-lock.json`).

```bash
udr lock                             # scan current directory
udr lock --directory /path/to/project
udr lock --manifest requirements.txt  # specific manifest only
udr lock --export Dockerfile          # export resolved deps
udr lock --dry-run                    # preview without writing
udr lock -y                           # skip prompts
udr lock --interactive                # select manifests + resolve conflicts
udr lock --json                       # output lock data as JSON
```

### `graph`

Show dependency tree for one or more packages.

```bash
udr graph flask django
udr graph numpy@pypi serde@crates
udr graph react -e npm
```

### `verify`

Validate a lock file — check all pinned versions still exist in their registries.

```bash
udr verify                    # uses udr-lock.json in current dir
udr verify --lock-file path/to/lock.json
```

### `list-ecosystems`

List all supported ecosystems.

```bash
udr list-ecosystems
udr list-ecosystems --json    # JSON output
```

### `update`

Re-resolve a single package and update the lock file.

```bash
udr update flask
udr update flask --directory /path/to/project
udr update flask --interactive
```

## Package spec syntax

```
name@ecosystem
```

Examples:

| Spec | Package | Ecosystem |
|---|---|---|
| `numpy` | numpy | pypi (default) |
| `numpy@pypi` | numpy | pypi |
| `@angular/core@npm` | @angular/core | npm |
| `express@npm` | express | npm |
| `serde@crates` | serde | crates |

The default ecosystem is `pypi`. Use `-e` / `--ecosystem` to change it for a single command.
