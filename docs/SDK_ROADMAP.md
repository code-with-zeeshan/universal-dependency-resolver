# SDK Status

## CLI — Done

The CLI is built into the `ud-resolver` package:

```bash
udr resolve flask>=2.0.0
udr lock
udr check
```

## Python SDK — Done

The entire backend is importable:

```python
from backend.core.data_aggregator import DataAggregator
from backend.core.conflict_resolver import ConflictResolver

aggregator = DataAggregator()
resolver = ConflictResolver()
info = await aggregator.get_package_info("flask", "pypi")
```

## Planned

- **JavaScript/TypeScript SDK** — wraps the REST API (community interest driven)
- **Go client** — stretch goal

The REST API at `http://localhost:8000/api/v1/` is fully documented via OpenAPI at `/api/v1/docs`.

## Contribute

PRs welcome for JS/TS and Go SDKs. Open an issue or upvote existing ones to signal demand.
