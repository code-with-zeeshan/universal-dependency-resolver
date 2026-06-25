# SDK Status

## CLI Tool — ✅ DONE

The CLI tool is already built into the backend:

```bash
python -m backend.cli resolve flask>=2.0.0
python -m backend.cli lock flask>=2.0.0
python -m backend.cli scan /path/to/project
```

## Python SDK — BUILT-IN

The entire backend is importable as a Python library:

```python
from backend.core.data_aggregator import DataAggregator
from backend.core.conflict_resolver import ConflictResolver

aggregator = DataAggregator()
resolver = ConflictResolver()
info = await aggregator.get_package_info("flask", "pypi")
```

## Planned

- **JavaScript/TypeScript SDK** — Q3 2026 (wraps the REST API)
- **Go Client** — Stretch goal (low priority)

The REST API at `http://localhost:8000/api/v1/` is fully documented via OpenAPI at `/api/v1/docs`.

## Contribute

- Star the repo for priority: SDKs follow community demand
- PRs welcome for JS/TS and Go SDKs
