# API Integration Guide

## Overview

The UDR REST API provides programmatic access to all dependency resolution features. The API is served by a FastApplication (FastAPI + uvicorn) started via `udr serve`. It exposes **59 endpoints** across **9 route modules**.

**Base URL:** `http://localhost:8000` (configurable via `--host`/`--port`)

**API docs (Swagger UI):** `http://localhost:8000/api/v1/docs`

---

## Quick Start

```bash
# Start the server in local mode (no auth required)
udr serve

# Or with a specific port and host
udr serve --host 0.0.0.0 --port 9000

# Production mode with auth
udr serve --mode saas
```

```python
import httpx

BASE = "http://localhost:8000"

# Search for packages
r = httpx.get(f"{BASE}/api/v1/packages/search", params={"q": "numpy"})
print(r.json())

# Resolve dependencies
r = httpx.post(
    f"{BASE}/api/v1/packages/resolve",
    json={
        "packages": [
            {"name": "flask", "ecosystem": "pypi", "version": ">=2.0"},
            {"name": "requests", "ecosystem": "pypi"},
        ],
    },
)
print(r.json())
```

---

## Authentication

The API has two auth layers:

| Layer | Mechanism | Exempt Paths |
|---|---|---|
| API key middleware (global) | `X-API-Key` header or `API_KEY` env var | `/healthz`, `/readyz`, `/api/v1/health`, OPTIONS |
| JWT auth (per-route) | `Authorization: Bearer <token>` | Check, SBOM endpoints (API key only) |

### API Key Mode

When `ENABLE_AUTH` is true (default), set `API_KEY` in the environment:

```bash
export API_KEY=my-secret-key
udr serve
```

Then pass it on every request:

```bash
curl -H "X-API-Key: my-secret-key" http://localhost:8000/api/v1/system/info
```

### SaaS Mode (JWT + API Keys)

```bash
udr serve --mode saas
```

**Registration:**

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "johndoe", "email": "john@example.com", "password": "securepass123"}'
```

**Login:**

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "johndoe", "password": "securepass123"}'
# Returns: {"access_token": "eyJ...", "token_type": "bearer", "refresh_token": "..."}
```

**API key creation (requires JWT):**

```bash
curl -X POST http://localhost:8000/api/v1/auth/api-keys \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"name": "ci-token", "scopes": ["read"]}'
# Returns: {"id": 1, "key": "udr_abc123def...", ...}
# Save the key — it's only shown once.
```

---

## Endpoint Visibility

Of the 59 endpoints:

| Visibility | Count | Details |
|---|---|---|
| No auth | 8 | `/`, `/healthz`, `/readyz`, `/auth/register`, `/auth/login`, `/auth/token`, `/auth/refresh`, `/auth/check-username` |
| API key (no user) | 6 | `/check/cve`, `/check/license`, `/check/deprecated`, `/check/policy`, `/check/all`, `/sbom` |
| Full auth (JWT or API key) | 45 | All other endpoints |

15 auth endpoints (auth.py) are **only mounted in saas mode** (`ENABLE_AUTH=true`).

---

## Common Workflows

### CI/CD Lock Check (GitHub Actions)

After `udr lock`, call the API to verify lock data:

```python
import json, httpx

BASE = "http://udr-server:8000"
API_KEY = "your-api-key"

# Load the lock file
with open("udr.lock") as f:
    lock_data = json.load(f)

# Verify all versions still exist
r = httpx.post(
    f"{BASE}/api/v1/verify",
    json={"lock_data": lock_data},
    headers={"X-API-Key": API_KEY},
)
print(r.json())
```

### Multi-Ecosystem Monorepo

Resolve packages across ecosystems in one call:

```python
r = httpx.post(
    f"{BASE}/api/v1/packages/resolve",
    json={
        "packages": [
            {"name": "numpy", "ecosystem": "pypi", "version": ">=1.20"},
            {"name": "express", "ecosystem": "npm", "version": "^4.18"},
            {"name": "serde", "ecosystem": "crates", "version": ">=1.0"},
        ],
        "auto_detect_system": True,
    },
    headers={"X-API-Key": API_KEY},
)
```

### Generate Lock from Scratch (CI)

Use manifest content mode to generate lock data without filesystem access:

```python
manifest_content = {
    "requirements.txt": "flask>=2.0\nrequests>=2.28\n",
    "package.json": json.dumps({"dependencies": {"express": "^4.18.0"}}),
}

r = httpx.post(
    f"{BASE}/api/v1/generate-lock?export_format=requirements.txt",
    json={"manifest_contents": manifest_content},
    headers={"X-API-Key": API_KEY},
)
lock_data = r.json()["lock_data"]
export_content = r.json().get("export_content")
```

### CVE + License + Deprecated Check

Combined check in one call:

```python
packages = {
    "numpy": {"ecosystem": "pypi", "version": "1.24.0"},
    "requests": {"ecosystem": "pypi", "version": "2.28.0"},
}

r = httpx.post(
    f"{BASE}/api/v1/check/all",
    json={"packages": packages},
    headers={"X-API-Key": API_KEY},
)
result = r.json()
# Contains: cve, license, deprecated, policy sections
```

---

## Error Handling

All errors return a consistent envelope:

```json
{
  "error": {
    "message": "Package not found in ecosystem",
    "type": "http_error",
    "status_code": 404,
    "timestamp": "2026-06-28T12:00:00"
  }
}
```

Common HTTP status codes:

| Code | Meaning |
|---|---|
| `200` | Success |
| `201` | Created (auth register, gen-key) |
| `400` | Bad request (invalid input, missing fields) |
| `401` | Unauthorized (missing or invalid auth) |
| `404` | Not found (package, endpoint, resource) |
| `429` | Rate limit exceeded |
| `500` | Internal server error |

---

## Complete API Reference

See [API Reference](API.md) for the full endpoint documentation including request/response schemas, rate limits, and status codes for all 59 endpoints.
