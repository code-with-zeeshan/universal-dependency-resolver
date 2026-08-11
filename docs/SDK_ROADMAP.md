# SDK Roadmap

## Current Status

| SDK | Status | Package | Notes |
|---|---|---|---|
| **CLI** | ✅ Complete | `ud-resolver` on PyPI | 26 commands, full resolution pipeline |
| **Python Library** | ✅ Complete | `backend.core`, `backend.orchestrator` | Fully importable as a library |
| **REST API** | ✅ Complete | Bundled in `udr serve` | 59 endpoints, OpenAPI docs at `/api/v1/docs` |
| **Desktop App** | ✅ Complete | Electron + PyInstaller | Cross-platform standalone binary |
| **VS Code Extension** | ✅ Complete | `vscode-extension/` | 13 commands, lock tree view, CVE diagnostics, manifest editing. Extension marketplace publishing pending. |
| **JavaScript/TypeScript** | 🔮 Planned | Community interest | Wraps REST API |
| **Go** | 🔮 Planned | Community interest | Wraps REST API |

## Python SDK

The entire backend is importable as a Python SDK:

```python
# Resolution
from backend.orchestrator.resolve import create_solver, ResolutionResult
from backend.core.data_aggregator import DataAggregator
from backend.core.system_scanner import SystemScanner

aggregator = DataAggregator()
scanner = SystemScanner()
system_info = scanner.scan_all()

# Fetch package data
package_data = aggregator.get_package_info("numpy", "pypi")

# Resolve
solver = create_solver(use_optimization=True, solver_timeout=30000)
result = solver.resolve_dependencies(
    packages=[{"name": "numpy", "ecosystem": "pypi", "version": ">=1.20"}],
    system_info=system_info,
)
print(result)
```

```python
# Vulnerability checking
from backend.core.data_aggregator import DataAggregator

aggregator = DataAggregator()
vulns = aggregator.check_vulnerabilities("numpy", "1.24.0", "pypi")
for v in vulns:
    print(f"{v['id']}: {v['severity']} - {v['summary']}")
```

```python
# License checking
from backend.core.license_checker import check_license_compatibility

result = check_license_compatibility("MIT")
print(result)
```

## REST API

All functionality is available via the REST API. See [API Reference](API.md) for full documentation.

The OpenAPI schema is auto-generated and available at:

- **Swagger UI:** `http://localhost:8000/api/v1/docs`
- **Redoc:** `http://localhost:8000/api/v1/redoc`
- **Raw schema:** `http://localhost:8000/api/v1/openapi.json`

## Planned SDKs

**JavaScript/TypeScript** and **Go** SDKs will be created based on community interest. Both would wrap the REST API rather than reimplementing the solver logic. Track progress on the [GitHub issues](https://github.com/code-with-zeeshan/universal-dependency-resolver/issues).
