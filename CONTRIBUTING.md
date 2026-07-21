# Contributing

Thanks for your interest in contributing. Here is what you need to know.

## Development Setup

```bash
# Clone and install
git clone https://github.com/code-with-zeeshan/universal-dependency-resolver.git
cd universal-dependency-resolver
python -m venv venv
source venv/bin/activate
make setup
```

Or manually:

```bash
pip install -e ".[dev]"
```

No PostgreSQL, Redis, or Docker required. SQLite + in-memory cache work out of the box.

```bash
# Run the server
udr serve --reload

# Or as a module
python -m backend.cli.main serve --reload

# Run tests
make test          # 3242+ unit tests
make test-all      # 3498+ tests (all)
cd desktop && node --test tests/  # desktop smoke tests

# Type check and lint
make typecheck     # mypy (0 errors target)
make lint          # ruff

# Validate YAML workflows
make yamllint
```

## Desktop development

```bash
cd desktop
npm install
npm run build    # Build desktop binary
npm run start    # Run in dev mode (uses system Python backend)
```

## Pull requests

1. Branch from `main`, name with prefix: `feature/`, `fix/`, `docs/`
2. Write tests for new functionality
3. Run `ruff check backend/` before committing
4. Keep PRs focused — one feature or fix per PR
5. Update `CHANGELOG.md` with your change

## Code standards

- Python: PEP 8, type hints required for all functions
- Ruff for linting and formatting
- Tests required for new code paths
- Desktop UI: inline HTML/CSS/JS in `desktop/index.html` (no framework)
- Commit messages: conventional commits (`feat:`, `fix:`, `docs:`, etc.)

## Where to contribute

- New ecosystem data sources in `backend/data_sources/`
- Additional export formats in `backend/core/export_generator.py`
- CLI improvements in `backend/cli/` (one module per command in `commands/`)
- Desktop UI improvements in `desktop/index.html`
- Documentation

## License

By contributing you agree that your contributions will be licensed under MIT.
