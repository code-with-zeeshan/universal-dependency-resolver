# API Reference

The Swagger UI at `http://localhost:8000/api/v1/docs` is the authoritative reference. This document provides an overview.

**Base URL:** `http://localhost:8000/api/v1`

## Authentication

Auth is **disabled by default** (`ENABLE_AUTH=false`). All requests use an anonymous user context.

To enable auth: set `ENABLE_AUTH=true` and configure `SECRET_KEY`.

```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "pass"}'

# Use token
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/packages/search?q=flask

# Or use API key
curl -H "X-API-Key: udr_<key>" \
  http://localhost:8000/api/v1/packages/search?q=flask
```

## Package endpoints (`/api/v1/packages`)

| Method | Path | Description |
|---|---|---|
| GET | `/search?q=<query>` | Search packages across ecosystems |
| GET | `/ecosystems` | List supported ecosystems |
| GET | `/{ecosystem}/{name}/details` | Rich package details with metrics |
| GET | `/{ecosystem}/{name}/versions` | List all versions |
| GET | `/{ecosystem}/{name}/dependencies` | Get dependencies |
| GET | `/{ecosystem}/{name}/compatibility` | Compatibility info |
| POST | `/resolve` | Resolve dependencies |
| POST | `/export` | Export resolved dependencies |
| GET | `/export-formats` | Available export formats |

### Search

```
GET /api/v1/packages/search?q=flask&ecosystems=pypi&limit=5
```

| Param | Type | Description |
|---|---|---|
| `q` | string | **Required.** Search query |
| `ecosystems` | string | Comma-separated ecosystem list |
| `limit` | int | 1-100, default 20 |

### Resolve

```
POST /api/v1/packages/resolve
Content-Type: application/json

{
  "packages": [
    {"name": "flask", "ecosystem": "pypi", "version": ">=2.0.0"},
    {"name": "express", "ecosystem": "npm"}
  ],
  "system_info": {"os": {"system": "Linux"}},
  "options": {"auto_detect_system": true}
}
```

### Export

```
POST /api/v1/packages/export
Content-Type: application/json

{
  "resolved_packages": {"flask": {"version": "2.3.3"}},
  "format": "requirements.txt"
}
```

Supported formats: `requirements.txt`, `package.json`, `environment.yml`, `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `install.sh`, `install.bat`, `CMakeLists.txt`, `Cargo.toml`, `build.gradle`, `pom.xml`.

## System endpoints (`/api/v1/system`)

| Method | Path | Description |
|---|---|---|
| GET | `/info` | System information (OS, CPU, GPU, runtimes) |
| POST | `/check-compatibility` | Check dependency-system compatibility |

## Auth endpoints (`/api/v1/auth`)

Only available when `ENABLE_AUTH=true`.

| Method | Path | Description |
|---|---|---|
| POST | `/register` | Register new user |
| POST | `/login` | Login, receive JWT |
| POST | `/token` | OAuth2 token endpoint |
| POST | `/refresh` | Refresh access token |
| POST | `/logout` | Logout |
| GET | `/profile` | Get user profile |
| PUT | `/profile` | Update profile |
| POST | `/change-password` | Change password |
| GET | `/api-keys` | List API keys |
| POST | `/api-keys` | Create API key |
| DELETE | `/api-keys/{key_id}` | Revoke API key |
| GET | `/verify` | Verify token validity |
| POST | `/check-username` | Check username availability |
| POST | `/check-email` | Check email availability |

## Scan endpoints (`/api/v1/scan`)

| Method | Path | Description |
|---|---|---|
| POST | `/github` | Scan a GitHub repository |
| POST | `/upload` | Scan an uploaded archive (multipart) |
| POST | `/local` | Scan a local directory |

All scan endpoints detect manifests, resolve dependencies, and return results.

## Lock endpoints (`/api/v1`)

| Method | Path | Description |
|---|---|---|
| POST | `/verify` | Validate a lock file |
| POST | `/graph` | Get dependency graph from lock file |
| POST | `/update` | Re-resolve and update a package in lock file |

## Other

| Method | Path | Description |
|---|---|---|
| GET | `/` | API metadata and endpoint list |
| GET | `/api/v1/health` | Health check (database, external APIs) |

## Rate limiting

| Category | Limit | Window |
|---|---|---|
| Search | 60 requests | 1 minute |
| Resolve | 10 requests | 1 minute |
| Export | 20 requests | 1 minute |
| General | 30 requests | 1 minute |

## Response format

Success:

```json
{"status": "success", "data": {...}}
```

Error:

```json
{
  "error": {
    "message": "Package not found",
    "type": "http_error",
    "status_code": 404
  }
}
```

## Status codes

| Code | Description |
|---|---|
| 200 | Success |
| 400 | Bad request |
| 401 | Unauthorized (auth enabled) |
| 403 | Forbidden |
| 404 | Not found |
| 422 | Validation error |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
