# API Reference

## Overview

**Base URL:** `http://localhost:8000` (configurable via `--host`/`--port`)

**API docs (Swagger UI):** `http://localhost:8000/api/v1/docs`

**Redoc:** `http://localhost:8000/api/v1/redoc`

**OpenAPI schema:** `http://localhost:8000/api/v1/openapi.json`

### Run modes

| Mode | Auth | Rate limiting | CMD |
|---|---|---|---|
| `local` | None (anonymous user) | Yes | `udr serve` / `udr serve --mode local` |
| `saas` | JWT Bearer + API key | Yes | `udr serve --mode saas` |

In `local` mode (`ENABLE_AUTH` defaults to `true`), the `get_current_user` dependency returns a mock anonymous user (id=1, username="anonymous"). All auth endpoints are **not mounted** in `local` mode.

In `saas` mode (`ENABLE_AUTH=true`), all endpoints require authentication via:
1. **JWT Bearer** in `Authorization: Bearer <token>` header (from `/auth/login` or `/auth/token`)
2. **API key** in `X-API-Key` header

### Rate limiting

Rate limits are per-endpoint (see tables below). When exceeded, returns `429 Too Many Requests`:

```json
{
  "error": {
    "message": "Rate limit exceeded: 10/minute",
    "type": "rate_limit_exceeded",
    "status_code": 429,
    "timestamp": "2026-06-28T12:00:00"
  }
}
```

Rate limiting uses slowapi with Redis (if `REDIS_URL` configured) or in-memory fallback.

### Error format

All errors return a consistent structure:

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

### Response envelope

Most endpoints return `{"status": "success", ...}`. Error responses use the error envelope above.

---

## Endpoint Summary

The API exposes **58 endpoints** organized into the following categories:

| # | Method | Path | Auth | Rate Limit |
|---|---|---|---|---|
| 1 | GET | `/` | No | 10/min |
| 2 | GET | `/api/v1/health` | No | 30/min |
| **Auth** (only in saas mode) | | | | |
| 3 | POST | `/api/v1/auth/register` | No | 5/hour |
| 4 | POST | `/api/v1/auth/login` | No | 10/min |
| 5 | POST | `/api/v1/auth/token` | No | 10/min |
| 6 | POST | `/api/v1/auth/refresh` | No | 30/min |
| 7 | POST | `/api/v1/auth/logout` | Yes | 30/min |
| 8 | GET | `/api/v1/auth/profile` | Yes | 60/min |
| 9 | PUT | `/api/v1/auth/profile` | Yes | 10/min |
| 10 | POST | `/api/v1/auth/change-password` | Yes | 5/hour |
| 11 | GET | `/api/v1/auth/api-keys` | Yes | 30/min |
| 12 | POST | `/api/v1/auth/api-keys` | Yes | 10/day |
| 13 | DELETE | `/api/v1/auth/api-keys/{key_id}` | Yes | 30/min |
| 14 | GET | `/api/v1/auth/verify` | Yes | 60/min |
| 15 | POST | `/api/v1/auth/check-username` | No | 30/min |
| 16 | GET | `/api/v1/auth/signing-key` | Yes | 30/min |
| 17 | POST | `/api/v1/auth/gen-key` | Yes | 10/day |
| **System** | | | | |
| 18 | GET | `/api/v1/system/info` | Yes | 30/min |
| 19 | POST | `/api/v1/system/check-compatibility` | Yes | 10/min |
| **Packages** | | | | |
| 20 | POST | `/api/v1/packages/resolve` | Yes | 10/min |
| 21 | POST | `/api/v1/packages/export` | Yes | 20/min |
| 22 | GET | `/api/v1/packages/export-formats` | Yes | 60/min |
| 23 | GET | `/api/v1/packages/search` | Yes | 60/min |
| 24 | GET | `/api/v1/packages/{eco}/{name}/details` | Yes | 120/min |
| 25 | GET | `/api/v1/packages/{eco}/{name}/versions` | Yes | 120/min |
| 26 | GET | `/api/v1/packages/{eco}/{name}/dependencies` | Yes | 120/min |
| 27 | GET | `/api/v1/packages/{eco}/{name}/compatibility` | Yes | 120/min |
| 28 | GET | `/api/v1/packages/ecosystems` | Yes | 60/min |
| **Scan** | | | | |
| 29 | POST | `/api/v1/scan/github` | Yes | none |
| 30 | POST | `/api/v1/scan/upload` | Yes | none |
| 31 | POST | `/api/v1/scan/local` | Yes | none |
| **Lock** | | | | |
| 32 | POST | `/api/v1/verify` | Yes | none |
| 33 | POST | `/api/v1/graph` | Yes | none |
| 34 | POST | `/api/v1/update` | Yes | none |
| 35 | POST | `/api/v1/generate-lock` | Yes | none |
| 36 | POST | `/api/v1/install-commands` | Yes | none |
| 37 | POST | `/api/v1/restore-commands` | Yes | none |
| 38 | POST | `/api/v1/why` | Yes | none |
| 39 | POST | `/api/v1/outdated` | Yes | none |
| 40 | POST | `/api/v1/diff` | Yes | none |
| 41 | POST | `/api/v1/lock/check` | Yes | none |
| 42 | POST | `/api/v1/lock/sign` | Yes | none |
| 43 | POST | `/api/v1/lock/update-with-fix` | Yes | none |
| 44 | POST | `/api/v1/lock/update-manifests` | Yes | none |
| 45 | POST | `/api/v1/lock/report` | Yes | none |
| 46 | POST | `/api/v1/lock/apply-pinning` | Yes | none |
| **Index Management** | | | | |
| 47 | GET | `/api/v1/index/status` | Yes | 30/min |
| 48 | POST | `/api/v1/index/pull` | Yes | 10/min |
| 49 | POST | `/api/v1/index/build` | Yes | 10/min |
| 50 | POST | `/api/v1/index/sync-all` | Yes | 10/min |
| **Check** | | | | |
| 51 | POST | `/api/v1/check/cve` | Yes | 10/min |
| 52 | POST | `/api/v1/check/license` | Yes | 10/min |
| 53 | POST | `/api/v1/check/deprecated` | Yes | 10/min |
| 54 | POST | `/api/v1/check/policy` | Yes | 10/min |
| **SBOM** | | | | |
| 55 | POST | `/api/v1/sbom` | Yes | 10/min |
| **Completion** | | | | |
| 56 | GET | `/api/v1/completion/{shell}` | Yes | 60/min |
| **Infrastructure** | | | | |
| 57 | GET | `/healthz` | No | none |
| 58 | GET | `/readyz` | No | none |
| 59 | GET | `/api/v1/docs` | No | none |
| 60 | GET | `/api/v1/redoc` | No | none |
| 61 | GET | `/api/v1/openapi.json` | No | none |

---

## General

### `GET /`

Root endpoint — returns API metadata and links.

**Rate limit:** 10/minute  
**Auth:** None

**Response:**

```json
{
  "name": "Universal Dependency Resolver API",
  "version": "1.4.0",
  "documentation": {
    "openapi": "/api/v1/docs",
    "redoc": "/api/v1/redoc"
  },
  "endpoints": {
    "health": "/api/v1/health",
    "system_info": "/api/v1/system/info",
    "package_info": "/api/v1/packages/{ecosystem}/{name}",
    "resolve": "/api/v1/packages/resolve",
    "export": "/api/v1/packages/export",
    "formats": "/api/v1/packages/export-formats"
  }
}
```

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Success |

---

### `GET /api/v1/health`

Health check — verifies database connection, Redis (if configured), and external APIs.

**Rate limit:** 30/minute  
**Auth:** None

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2026-06-28T12:00:00",
  "version": "1.4.0",
  "checks": {
    "database": {"status": "healthy"},
    "redis": {"status": "healthy"},
    "external_apis": {"status": "healthy"}
  }
}
```

Redis check is optional — if Redis is not configured it's omitted from the response. Database is required — if unhealthy, the overall `status` is `"unhealthy"`.

**Status codes:**
| Code | Condition |
|---|---|
| `200` | All critical dependencies healthy |
| `200` | Database unhealthy, overall status `"unhealthy"` |

---

## Auth

All auth endpoints are only mounted when `ENABLE_AUTH=true` (saas mode). In local mode, endpoints 3–16 are not available.

---

### `POST /api/v1/auth/register`

Register a new user.

**Rate limit:** 5/hour  
**Auth:** None

**Request body:**

```json
{
  "username": "johndoe",
  "email": "john@example.com",
  "password": "securepassword123",
  "full_name": "John Doe"
}
```

**Response (201 Created):**

```json
{
  "id": 1,
  "username": "johndoe",
  "email": "john@example.com",
  "full_name": "John Doe",
  "is_active": true,
  "scopes": []
}
```

**Status codes:**
| Code | Condition |
|---|---|
| `201` | User created successfully |
| `400` | Username or email already taken, invalid email format |
| `429` | Rate limit exceeded |

---

### `POST /api/v1/auth/login`

Login with username/password, receive JWT tokens.

**Rate limit:** 10/minute  
**Auth:** None

**Request body:**

```json
{
  "username": "johndoe",
  "password": "securepassword123"
}
```

**Response:**

```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "refresh_token": "dGhpcyBpcyBh..."
}
```

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Login successful |
| `401` | Invalid credentials |
| `429` | Rate limit exceeded |

---

### `POST /api/v1/auth/token`

OAuth2-compatible token endpoint. Accepts form-encoded credentials.

**Rate limit:** 10/minute  
**Auth:** None

**Request body (form-data):**

| Field | Type | Required |
|---|---|---|
| `grant_type` | string | no (must be "password" if provided) |
| `username` | string | yes |
| `password` | string | yes |

**Response:**

```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "refresh_token": "dGhpcyBpcyBh..."
}
```

---

### `POST /api/v1/auth/refresh`

Refresh an expired access token using a refresh token.

**Rate limit:** 30/minute  
**Auth:** None

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `refresh_token` | string | yes | Refresh token from `/login` or `/token` |

**Response:**

```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "refresh_token": "bmV3IHJlZnJl..."
}
```

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Token refreshed |
| `401` | Invalid or expired refresh token |

---

### `POST /api/v1/auth/logout`

Logout. Client should discard tokens.

**Rate limit:** 30/minute  
**Auth:** JWT Bearer or API key

**Response:**

```json
{
  "message": "Successfully logged out"
}
```

---

### `GET /api/v1/auth/profile`

Get authenticated user's profile.

**Rate limit:** 60/minute  
**Auth:** JWT Bearer or API key

**Response:**

```json
{
  "id": 1,
  "username": "johndoe",
  "email": "john@example.com",
  "full_name": "John Doe",
  "is_active": true,
  "scopes": []
}
```

---

### `PUT /api/v1/auth/profile`

Update profile (full_name, email).

**Rate limit:** 10/minute  
**Auth:** JWT Bearer or API key

**Request body:**

```json
{
  "full_name": "John Updated",
  "email": "john.new@example.com"
}
```

Both fields are optional — only provided fields are updated.

**Response:** Same as `GET /profile`.

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Profile updated |
| `400` | Email already in use by another account |

---

### `POST /api/v1/auth/change-password`

Change the authenticated user's password.

**Rate limit:** 5/hour  
**Auth:** JWT Bearer or API key

**Request body:**

```json
{
  "current_password": "oldpassword123",
  "new_password": "newpassword456"
}
```

**Response:**

```json
{
  "message": "Password changed successfully"
}
```

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Password changed |
| `400` | Current password is incorrect |

---

### `GET /api/v1/auth/api-keys`

List the user's active API keys (keys are masked).

**Rate limit:** 30/minute  
**Auth:** JWT Bearer or API key

**Response:**

```json
[
  {
    "id": 1,
    "name": "CI pipeline",
    "key": "********************aBcDeFgH",
    "description": "Used for GitHub Actions",
    "scopes": ["read"],
    "created_at": "2026-06-01T12:00:00",
    "expires_at": "2027-06-01T12:00:00"
  }
]
```

The full key is only returned on creation (see `POST /api-keys`). List view shows only the last 8 characters.

---

### `POST /api/v1/auth/api-keys`

Create a new API key. The full key is returned **only once** — store it immediately.

**Rate limit:** 10/day  
**Auth:** JWT Bearer or API key

**Request body:**

```json
{
  "name": "CI pipeline",
  "description": "Used for GitHub Actions",
  "scopes": ["read"],
  "expires_at": "2027-06-01T12:00:00"
}
```

**Response:**

```json
{
  "id": 1,
  "name": "CI pipeline",
  "key": "udr_abc123def456...",
  "description": "Used for GitHub Actions",
  "scopes": ["read"],
  "created_at": "2026-06-28T12:00:00",
  "expires_at": "2027-06-01T12:00:00"
}
```

The `key` field contains the **full** plaintext key — this is the only time it is returned.

---

### `DELETE /api/v1/auth/api-keys/{key_id}`

Revoke an API key by ID.

**Rate limit:** 30/minute  
**Auth:** JWT Bearer or API key

**Path parameters:**

| Parameter | Type | Description |
|---|---|---|
| `key_id` | int | API key ID from list |

**Response:**

```json
{
  "message": "API key revoked successfully"
}
```

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Key revoked |
| `404` | Key not found or doesn't belong to user |

---

### `GET /api/v1/auth/verify`

Verify the current token is valid.

**Rate limit:** 60/minute  
**Auth:** JWT Bearer or API key

**Response:**

```json
{
  "valid": true,
  "username": "johndoe",
  "user_id": 1
}
```

---

### `POST /api/v1/auth/check-username`

Check if a username is available for registration.

**Rate limit:** 30/minute  
**Auth:** None

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `username` | string | yes | Username to check |

**Response:**

```json
{
  "available": true
}
```

---

### `POST /api/v1/auth/check-email`

Check if an email is available for registration.

**Rate limit:** 30/minute  
**Auth:** None

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `email` | string | yes | Email address to check |

**Response:**

```json
{
  "available": true
}
```

---

### `GET /api/v1/auth/signing-key`

Show the current Ed25519 public signing key for lock-file signing. Mirrors `udr auth show-key`.

**Rate limit:** 30/minute  
**Auth:** JWT Bearer or API key

**Response:**

```json
{
  "status": "success",
  "algorithm": "Ed25519",
  "public_key_base64": "MCowBQYDK2VwAyEA...",
  "fingerprint": "a1b2c3d4e5f6...",
  "key_directory": "/home/user/.config/udr"
}
```

**Status codes:**

| Code | Condition |
|---|---|
| `200` | Key shown |
| `404` | No signing key found |

---

### `POST /api/v1/auth/gen-key`

Generate a new Ed25519 signing key pair for lock-file signing. Keys are stored in `~/.config/udr/`. Mirrors `udr auth gen-key`.

**Rate limit:** 10/day  
**Auth:** JWT Bearer or API key

**Response (201 Created):**

```json
{
  "status": "success",
  "message": "Ed25519 signing key generated",
  "public_key_base64": "MCowBQYDK2VwAyEA...",
  "fingerprint": "a1b2c3d4e5f6...",
  "key_directory": "/home/user/.config/udr"
}
```

**Status codes:**

| Code | Condition |
|---|---|
| `201` | Key generated |
| `500` | Key generation failed |

---

## System

All system endpoints require auth in saas mode (anonymous in local mode).

---

### `GET /api/v1/system/info`

Get system information (OS, CPU, GPU, CUDA, Python version).

**Rate limit:** 30/minute  
**Auth:** Yes (anonymous in local mode)

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `detailed` | bool | `false` | Return full system scan output |

**Response (non-detailed):**

```json
{
  "status": "success",
  "system": {
    "os": "Linux 6.2.0",
    "cpu": "Intel(R) Xeon(R)",
    "gpu": "NVIDIA A100",
    "cuda": "12.1",
    "python": "3.11.5"
  }
}
```

**Response (detailed):**

```json
{
  "status": "success",
  "data": {
    "platform": {"system": "Linux", "release": "6.2.0", "machine": "x86_64"},
    "cpu": {"brand": "Intel(R) Xeon(R)", "architecture": "x86_64", "count_logical": 8, "count_physical": 4},
    "memory": {"total": 33456789000, "available": 28000000000, "percent": 16.3},
    "gpu": {"available": true, "devices": [{"name": "NVIDIA A100", "memory_total": 40960}], "cuda": "12.1"},
    "runtime_versions": {"python": {"version": "3.11.5", "path": "/usr/bin/python3"}}
  }
}
```

---

### `POST /api/v1/system/check-compatibility`

Check if the system meets specified hardware/software requirements.

**Rate limit:** 10/minute  
**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "requirements": [
    {
      "type": "gpu",
      "minimum": {"cuda": "11.8", "memory_gb": 8},
      "required": true
    },
    {
      "type": "memory",
      "minimum": {"gb": 16},
      "required": true
    }
  ],
  "packages": ["tensorflow", "pytorch"]
}
```

**Requirement types supported:**

| Type | Checks | Minimum fields |
|---|---|---|
| `gpu` | GPU available, CUDA version, GPU memory, compute capability | `cuda`, `memory_gb`, `compute_capability` |
| `cpu` | Core count, CPU features, architecture | `cores`, `features`, `architecture` |
| `memory` | Total RAM, available RAM | `gb` |
| `disk` | Disk space, disk type | `gb`, `type` |
| `os` | OS name, version | `name`, `version` |
| `python` | Python version | `version` |
| `compiler` | Compiler installed (gcc, g++, clang, msvc) | compiler name → version |

**Response:**

```json
{
  "status": "success",
  "results": {
    "compatible": true,
    "checks": [
      {
        "type": "gpu",
        "status": "pass",
        "message": "",
        "details": {}
      }
    ],
    "warnings": [],
    "errors": [],
    "recommendations": [],
    "package_compatibility": {
      "pytorch": [
        {
          "type": "gpu",
          "status": "pass",
          "message": ""
        }
      ]
    }
  }
}
```

If any requirement fails, `compatible` is `false` and the error is listed in `errors`. Non-critical failures produce warnings.

---

## Packages

---

### `POST /api/v1/packages/resolve`

Resolve dependencies for multiple packages. Returns a SAT-solved set of compatible versions.

**Rate limit:** 10/minute  
**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "packages": [
    {"name": "numpy", "ecosystem": "pypi", "version": ">=1.20"},
    {"name": "pandas", "ecosystem": "pypi"},
    {"name": "express", "ecosystem": "npm", "version": "^4.18"}
  ],
  "system_info": {
    "gpu": {"available": true, "cuda": "12.1"},
    "os": {"system": "Linux"},
    "cpu": {"architecture": "x86_64"}
  },
  "auto_detect_system": true,
  "prefer_compatibility": true
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `packages` | array | (required) | Package specs with name, optional ecosystem (default: pypi), optional version constraint |
| `system_info` | object | `null` | Override auto-detected system info |
| `auto_detect_system` | bool | `true` | Auto-detect system hardware (OS, CPU, GPU, CUDA) |
| `prefer_compatibility` | bool | `true` | When true, prefer versions known to be compatible |

If `auto_detect_system` is `true` and `system_info` is `null`, the system is scanned automatically (cached for 5 minutes).

**Response:**

```json
{
  "status": "success",
  "data": {
    "resolved_packages": {
      "numpy": {"version": "1.26.0", "ecosystem": "pypi"},
      "pandas": {"version": "2.1.3", "ecosystem": "pypi"}
    },
    "warnings": []
  }
}
```

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Resolution complete (may have warnings) |
| `400` | Invalid package data |
| `500` | Internal resolution error |

---

### `POST /api/v1/packages/export`

Export resolved dependencies to a specific format.

**Rate limit:** 20/minute  
**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "resolved_packages": {
    "numpy": {"version": "1.26.0", "ecosystem": "pypi"}
  },
  "format": "requirements.txt",
  "system_info": {"os": "Linux", "python": "3.11"},
  "options": {}
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `resolved_packages` | object | (required) | Package name → version/ecosystem mapping |
| `format` | string | (required) | Export format identifier |
| `system_info` | object | `null` | Optional system context |
| `options` | object | `{}` | Format-specific options |

**Response:**

```json
{
  "status": "success",
  "format": "requirements.txt",
  "content": "numpy==1.26.0\npandas==2.1.3\n"
}
```

---

### `GET /api/v1/packages/export-formats`

List all available export formats.

**Rate limit:** 60/minute  
**Auth:** Yes (anonymous in local mode)

**Response:**

```json
{
  "status": "success",
  "formats": [
    {"format": "requirements.txt", "ecosystem": "pypi", "description": "Python pip requirements"},
    {"format": "Dockerfile", "ecosystem": "pypi", "description": "Docker image with Python dependencies"}
  ]
}
```

---

### `GET /api/v1/packages/search`

Search for packages across multiple ecosystems.

**Rate limit:** 60/minute  
**Auth:** Yes (anonymous in local mode)

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `q` | string | (required) | Search query |
| `ecosystems` | string | `null` | Comma-separated list (e.g. `pypi,npm`) |
| `limit` | int | `20` | Max results per ecosystem (1–100) |
| `sort_by` | string | `relevance` | Sort order: `relevance`, `downloads`, `name`, `updated` |
| `python_version` | string | `null` | Filter by Python version (e.g. `3.9`) |

**Response:**

```json
{
  "status": "success",
  "query": "numpy",
  "total_count": 42,
  "results": {
    "pypi": [
      {"name": "numpy", "version": "1.26.0", "summary": "NumPy is the fundamental package for array computing with Python"}
    ],
    "conda": []
  },
  "filters_applied": {
    "ecosystems": null,
    "python_version": null,
    "sort_by": "relevance"
  }
}
```

---

### `GET /api/v1/packages/{ecosystem}/{package_name}/details`

Get detailed information about a specific package.

**Rate limit:** 120/minute  
**Auth:** Yes (anonymous in local mode)

**Path parameters:**

| Parameter | Type | Description |
|---|---|---|
| `ecosystem` | string | Ecosystem identifier (e.g. `pypi`, `npm`, `crates`) |
| `package_name` | string | Package name |

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `include_metrics` | bool | `false` | Include download/usage metrics |

**Response:**

```json
{
  "status": "success",
  "data": {
    "name": "numpy",
    "ecosystem": "pypi",
    "info": {
      "summary": "NumPy is the fundamental package...",
      "home_page": "https://numpy.org",
      "license": "BSD-3-Clause",
      "versions": ["1.26.0", "1.25.2"],
      "dependencies": {}
    },
    "compatibility_matrix": {},
    "system_requirements": {},
    "compatibility_summary": {"overall": "high", "issues": []}
  }
}
```

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Success |
| `404` | Package not found in the specified ecosystem |

---

### `GET /api/v1/packages/{ecosystem}/{package_name}/versions`

Get all available versions of a package with filtering.

**Rate limit:** 120/minute  
**Auth:** Yes (anonymous in local mode)

**Path parameters:**

| Parameter | Type | Description |
|---|---|---|
| `ecosystem` | string | Ecosystem identifier |
| `package_name` | string | Package name |

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `compatible_with` | string | `null` | System spec filter: `os=linux,python=3.9,cuda=11.2` |
| `include_yanked` | bool | `false` | Include yanked/deprecated versions |
| `include_prerelease` | bool | `false` | Include pre-release versions (alpha, beta, rc) |

**Response:**

```json
{
  "status": "success",
  "package": "numpy",
  "ecosystem": "pypi",
  "total_versions": 42,
  "filtered_count": 3,
  "versions": [
    {
      "version": "1.26.0",
      "yanked": false,
      "requires_python": ">=3.9",
      "upload_time": "2023-09-16T12:00:00"
    }
  ],
  "filters": {
    "compatible_with": null,
    "include_yanked": false,
    "include_prerelease": false
  }
}
```

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Success |
| `400` | Unknown ecosystem |

---

### `GET /api/v1/packages/{ecosystem}/{package_name}/dependencies`

Get dependencies for a specific package version.

**Rate limit:** 120/minute  
**Auth:** Yes (anonymous in local mode)

**Path parameters:**

| Parameter | Type | Description |
|---|---|---|
| `ecosystem` | string | Ecosystem identifier |
| `package_name` | string | Package name |

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `version` | string | `null` (latest) | Specific version to inspect |
| `recursive` | bool | `false` | Get full transitive dependency tree |
| `max_depth` | int | `3` | Maximum recursion depth (1–5) |

**Response (non-recursive):**

```json
{
  "status": "success",
  "package": "numpy",
  "version": "1.26.0",
  "dependencies": []
}
```

**Response (recursive):**

```json
{
  "status": "success",
  "package": "pandas",
  "version": "2.1.3",
  "dependency_tree": {
    "name": "pandas",
    "version": "2.1.3",
    "dependencies": {
      "numpy": {
        "name": "numpy",
        "version": ">=1.23.2",
        "dependencies": {}
      }
    }
  },
  "total_dependencies": 1
}
```

---

### `GET /api/v1/packages/{ecosystem}/{package_name}/compatibility`

Get known compatibility information for a package.

**Rate limit:** 120/minute  
**Auth:** Yes (anonymous in local mode)

**Path parameters:**

| Parameter | Type | Description |
|---|---|---|
| `ecosystem` | string | Ecosystem identifier |
| `package_name` | string | Package name |

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `version` | string | `null` | Specific version to check |

**Response:**

```json
{
  "status": "success",
  "package": "numpy",
  "ecosystem": "pypi",
  "version": "1.26.0",
  "compatibility": {
    "known_conflicts": [],
    "verified_combinations": [],
    "system_requirements": {},
    "version_specific": {},
    "community_reports": [],
    "statistics": {}
  }
}
```

---

### `GET /api/v1/packages/ecosystems`

Get list of all 27 supported package ecosystems with capabilities.

**Rate limit:** 60/minute  
**Auth:** Yes (anonymous in local mode)

**Response:**

```json
{
  "status": "success",
  "ecosystems": {
    "pypi": {
      "name": "Python Package Index",
      "language": "Python",
      "package_manager": "pip",
      "supports_search": true,
      "supports_versions": true,
      "supports_dependencies": true
    }
  },
  "total": 27
}
```

**Supported ecosystems:**

| Key | Language | Package manager |
|---|---|---|
| `pypi` | Python | pip |
| `npm` | JavaScript/TypeScript | npm/yarn |
| `conda` | Python/Multi | conda |
| `maven` | Java | maven/gradle |
| `crates` | Rust | cargo |
| `gomodules` | Go | go mod |
| `nuget` | C#/.NET | dotnet/nuget |
| `rubygems` | Ruby | gem/bundler |
| `packagist` | PHP | composer |
| `cocoapods` | Objective-C/Swift | cocoapods |
| `homebrew` | System | brew |
| `apt` | System | apt/apt-get |
| `apk` | System | apk |
| `pub` | Dart/Flutter | dart pub |
| `gradle` | Java/Kotlin | gradle |
| `swift` | Swift | swift |
| `hex` | Elixir | mix |
| `haskell` | Haskell | cabal/stack |
| `nix` | NixOS | nix |
| `guix` | GNU Guix | guix |
| `docker` | Container | docker |
| `helm` | Kubernetes | helm |
| `terraform` | Infrastructure | terraform |
| `vcpkg` | C++ | vcpkg |
| `conan` | C/C++ | conan |
| `docs` | Documentation | docs |
| `custom_db` | Custom | custom |

---

## Scan

Scan endpoints run the full resolution pipeline (manifest detection → fetch metadata → SAT resolution) on external projects.

---

### `POST /api/v1/scan/github`

Scan a GitHub repository by URL. Downloads repo as a zipball, detects manifests, resolves all dependencies.

**Auth:** Yes (anonymous in local mode)

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `export` | string | `null` | Export format (e.g. `requirements.txt`, `Dockerfile`) |

**Request body:**

```json
{
  "repo_url": "https://github.com/user/repo",
  "branch": "main"
}
```

**Response:**

```json
{
  "status": "success",
  "source": "github",
  "repo_url": "https://github.com/user/repo",
  "manifests": [
    {"filename": "requirements.txt", "ecosystem": "pypi"}
  ],
  "packages": [
    {
      "name": "numpy",
      "ecosystem": "pypi",
      "constraint": ">=1.20",
      "resolved_version": "1.26.0",
      "cuda_variant": false,
      "cuda_version": null
    }
  ],
  "resolution": {"resolved_packages": {"numpy": {"version": "1.26.0"}}},
  "system": {
    "os": "Linux 6.2.0",
    "python": "3.11.5",
    "cpu": "Intel(R) Xeon(R)",
    "gpu": "NVIDIA A100",
    "cuda": "12.1"
  },
  "export": null
}
```

**Possible `status` values:**
| Value | Meaning |
|---|---|
| `"success"` | Resolution complete |
| `"no_manifests"` | No recognized manifest files found |
| `"no_packages"` | Manifests found but no parseable packages |

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Scan complete (check `status` field for resolution result) |
| `400` | Invalid GitHub URL, or API returned non-200 |

---

### `POST /api/v1/scan/upload`

Upload a ZIP archive of a project. Extracts, detects manifests, resolves dependencies.

**Auth:** Yes (anonymous in local mode)

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `export` | string | `null` | Export format |

**Request body:** `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `file` | binary | `.zip` file (max size limited by `RequestSizeLimitMiddleware`) |

**Response:** Same structure as `/scan/github`, with `source: "upload"` and `filename` field.

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Scan complete |
| `400` | File is not a `.zip`, or zip contains illegal paths |

---

### `POST /api/v1/scan/local`

Scan a local directory path. Only works when backend runs on the same machine.

**Auth:** Yes (anonymous in local mode)

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `export` | string | `null` | Export format |

**Request body:**

```json
{
  "directory_path": "/home/user/projects/myapp"
}
```

**Response:** Same structure as `/scan/github`, with `source: "local"` and `directory_path` field.

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Scan complete |
| `400` | Directory does not exist |

---

## Lock

Lock endpoints mirror `udr verify`, `udr graph`, `udr update`, `udr lock --check`, `udr lock --sign`, `udr lock --report`, `udr lock --pin/--block/--freeze`, `udr update --fix-cve`, and `udr auth gen-key/show-key` CLI commands. They accept and return lock data as JSON so clients can manage lock state without file system access.

---

### `POST /api/v1/verify`

Validate a lock file — check that every resolved version still exists in its registry. Mirrors `udr verify`.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "lock_data": {
    "packages": {
      "numpy": {
        "ecosystem": "pypi",
        "resolved_version": "1.26.0"
      },
      "old-package": {
        "ecosystem": "pypi",
        "resolved_version": "0.5.0"
      }
    }
  }
}
```

**Response:**

```json
{
  "status": "ok",
  "total": 2,
  "ok": 1,
  "issues": [
    {
      "name": "old-package",
      "issue": "Version 0.5.0 no longer available",
      "severity": "error"
    }
  ]
}
```

**Severity levels:**
| Severity | Meaning |
|---|---|
| `"error"` | Version not found on registry, or package no longer exists |
| `"warning"` | Package has no resolved version (was unresolved) |

Overall `status` is `"ok"` if no errors, `"issues"` if any packages have errors.

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Verification complete (check `status` field) |
| `400` | No packages in lock data |

---

### `POST /api/v1/graph`

Get dependency tree for one or more packages. Mirrors `udr graph`.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "packages": ["numpy", "pandas"],
  "ecosystem": "pypi"
}
```

**Response:**

```json
{
  "status": "success",
  "trees": [
    {
      "name": "numpy",
      "version": "1.26.0",
      "ecosystem": "pypi",
      "children": []
    },
    {
      "name": "pandas",
      "version": "2.1.3",
      "ecosystem": "pypi",
      "children": [
        {
          "name": "numpy",
          "version": ">=1.23.2",
          "ecosystem": "pypi",
          "children": []
        }
      ]
    }
  ]
}
```

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Graph generated |
| `404` | No packages could be fetched/resolved |

---

### `POST /api/v1/update`

Re-resolve a single package and return updated lock data. Mirrors `udr update <package> --json`.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "lock_data": {
    "packages": {
      "flask": {
        "ecosystem": "pypi",
        "resolved_version": "2.0.0"
      }
    }
  },
  "package": "flask",
  "ecosystem": "pypi"
}
```

`ecosystem` is optional — defaults to the value in `lock_data.packages[package].ecosystem`.

**Response:**

```json
{
  "status": "success",
  "package": "flask",
  "old_version": "2.0.0",
  "new_version": "3.0.0",
  "updated": true,
  "lock_data": {
    "packages": {
      "flask": {
        "ecosystem": "pypi",
        "resolved_version": "3.0.0",
        "cuda_variant": false,
        "cuda_version": null
      }
    },
    "generated_at": "2026-06-28T12:00:00"
  }
}
```

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Package re-resolved (check `updated` field) |
| `404` | Package not found in lock data, or no data fetched |
| `500` | Resolution failed |

### `POST /api/v1/generate-lock`

Generate a `udr.lock` structure from project manifests or pre-parsed package data. Supports two modes:

1. **Pre-parsed mode** (original): POST `packages`, `manifests`, `system`, `resolution`.
2. **Manifest content mode** (mirrors `udr lock --json`): POST `manifest_contents` as a dict of `{filename: content}`.

Optionally pass `?export_format=requirements.txt` to chain export generation (mirrors `udr lock --export`).

**Auth:** Yes (anonymous in local mode)

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `export_format` | string | — | Optional export format (e.g. `requirements.txt`, `Dockerfile`) |

**Request body (pre-parsed mode):**

```json
{
  "packages": [
    {
      "name": "numpy",
      "ecosystem": "pypi",
      "resolved_version": "1.26.0",
      "constraint": ">=1.20",
      "source": "requirements.txt"
    }
  ],
  "manifests": [{"filename": "requirements.txt", "ecosystem": "pypi"}],
  "system": {
    "platform": {"system": "Linux", "release": "6.2.0"},
    "cpu": {"brand": "Intel(R) Xeon(R)"},
    "gpu": {"available": true, "devices": [{"name": "NVIDIA A100"}], "cuda": "12.1"},
    "runtime_versions": {"python": {"version": "3.11.5"}}
  },
  "resolution": {
    "resolved_packages": {},
    "warnings": []
  }
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `packages` | array | (required) | Packages found in manifests (name, ecosystem, version, constraint, source) |
| `manifests` | array | `[]` | Manifest files detected |
| `system` | object | `null` | System scan data (platform, cpu, gpu, runtime_versions) |
| `resolution` | object | `null` | Resolution results (resolved_packages, warnings) |
| `manifest_contents` | dict | `null` | **Alternative mode**: filename → content mapping of manifest files |
| `manifest_filter` | string | `null` | Only process this manifest filename (used with `manifest_contents`) |

**Response:**

```json
{
  "status": "success",
  "lock_data": {
    "version": "2.0",
    "generated_at": "2026-07-05T12:00:00",
    "resolver": "sat",
    "system": {"os": "Linux 6.2.0", "python": "3.11.5", "cpu": "Intel(R) Xeon(R)", "gpu": "NVIDIA A100", "cuda": "12.1"},
    "manifests": ["requirements.txt"],
    "packages": {
      "numpy": {
        "name": "numpy",
        "ecosystem": "pypi",
        "resolved_version": "1.26.0",
        "direct": true,
        "cuda_variant": false,
        "cuda_version": null,
        "original_constraint": ">=1.20",
        "source": "requirements.txt",
        "vulnerabilities": []
      }
    },
    "warnings": []
  }
}
```

When `?export_format=` is specified, the response also includes:

```json
{
  "status": "success",
  "lock_data": { ... },
  "export_content": "numpy==1.26.0\n",
  "export_format": "requirements.txt"
}
```

---

### `POST /api/v1/install-commands`

Generate native package manager install commands for direct dependencies from lock data. Mirrors `udr install`.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "lock_data": {
    "packages": {
      "numpy": {
        "ecosystem": "pypi",
        "resolved_version": "1.26.0",
        "direct": true
      }
    }
  }
}
```

**Response:**

```json
{
  "status": "success",
  "commands": [
    {"ecosystem": "pypi", "command": "pip install numpy==1.26.0", "package_count": 1}
  ],
  "total_packages": 1
}
```

**Status codes:**
| Code | Condition |
|---|---|
| `200` | Commands generated (may be empty if no direct deps) |

---

### `POST /api/v1/restore-commands`

Generate native package manager install commands for **all** packages (direct + transitive) from lock data. Mirrors `udr restore`.

**Auth:** Yes (anonymous in local mode)

**Request body:** Same as `/install-commands`.

**Response:** Same structure as `/install-commands`, but includes transitive dependencies.

---

### `POST /api/v1/why`

Explain why a package version was selected — dependency chain, direct/transitive status, constraint. Mirrors `udr why`.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "lock_data": {
    "packages": {
      "flask": {
        "ecosystem": "pypi",
        "resolved_version": "2.3.3",
        "direct": true,
        "original_constraint": ">=2.0"
      },
      "click": {
        "ecosystem": "pypi",
        "resolved_version": "8.1.7",
        "direct": false,
        "original_constraint": "*"
      }
    }
  },
  "package": "click"
}
```

**Response:**

```json
{
  "status": "success",
  "package": "click",
  "version": "8.1.7",
  "ecosystem": "pypi",
  "direct": false,
  "original_constraint": "*",
  "source": "transitive",
  "dependency_chain": [
    {"package": "flask", "version": "2.3.3", "required_as": ">=8.0"}
  ]
}
```

For direct dependencies, `dependency_chain` is an empty array.

**Status codes:**

| Code | Condition |
|---|---|
| `200` | Info returned |
| `404` | Package not found in lock data |

---

### `POST /api/v1/outdated`

Check all packages in lock data against registries for newer versions. Mirrors `udr outdated --json`.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "lock_data": {
    "packages": {
      "numpy": {
        "ecosystem": "pypi",
        "resolved_version": "1.25.0",
        "direct": true
      }
    }
  },
  "ecosystem": "pypi"
}
```

`ecosystem` is optional — if provided, only checks packages from that ecosystem.

**Response:**

```json
{
  "status": "success",
  "outdated_count": 1,
  "packages": [
    {
      "name": "numpy",
      "ecosystem": "pypi",
      "current": "1.25.0",
      "latest": "1.26.0",
      "type": "direct"
    }
  ]
}
```

**Status codes:**

| Code | Condition |
|---|---|
| `200` | Check complete |

---

### `POST /api/v1/diff`

Compare two lock data objects and report package differences. Mirrors `udr diff --json`.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "lock_a": {
    "packages": {
      "numpy": {"ecosystem": "pypi", "resolved_version": "1.25.0"}
    }
  },
  "lock_b": {
    "packages": {
      "numpy": {"ecosystem": "pypi", "resolved_version": "1.26.0"}
    }
  }
}
```

**Response:**

```json
{
  "status": "success",
  "added": [],
  "removed": [],
  "changed": [
    {"name": "numpy", "ecosystem": "pypi", "from": "1.25.0", "to": "1.26.0"}
  ],
  "unchanged_count": 0
}
```

**Status codes:**

| Code | Condition |
|---|---|
| `200` | Diff computed |

---

### `POST /api/v1/lock/check`

CI drift detection — re-resolves manifests and compares against the existing lock data without writing. Mirrors `udr lock --check`.

**Auth:** Yes (anonymous in local mode)

**Request:**

```json
{
  "manifest_contents": {
    "requirements.txt": "numpy>=1.20\nflask>=2.0\n"
  },
  "existing_lock_data": {
    "packages": {
      "numpy": {"ecosystem": "pypi", "resolved_version": "1.26.0", "direct": true}
    }
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `manifest_contents` | dict | yes | Filename → raw content of manifest files |
| `existing_lock_data` | dict | yes | The current lock data to check against |

**Response (no drift):**

```json
{
  "status": "ok",
  "drift_detected": false,
  "added": [],
  "removed": [],
  "changed": [],
  "unchanged_count": 5
}
```

**Response (drift detected):**

```json
{
  "status": "drift",
  "drift_detected": true,
  "added": [{"name": "new-pkg", "version": "1.0.0", "ecosystem": "pypi"}],
  "removed": [{"name": "old-pkg", "version": "0.5.0", "ecosystem": "pypi"}],
  "changed": [{"name": "numpy", "ecosystem": "pypi", "from": "1.25.0", "to": "1.26.0"}],
  "unchanged_count": 3
}
```

**Status codes:**

| Code | Condition |
|---|---|
| `200` | Re-resolution complete; check `drift_detected` to determine outcome |

---

### `POST /api/v1/lock/sign`

Sign lock data with Ed25519 key. Mirrors `udr lock --sign`.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "lock_data": {"packages": {}}
}
```

**Response:**

```json
{
  "status": "success",
  "lock_data": {
    "packages": {},
    "signature": {
      "algorithm": "ed25519",
      "value": "base64...",
      "public_key": "base64..."
    }
  },
  "signature": "base64...",
  "public_key": "base64...",
  "algorithm": "ed25519"
}
```

The `lock_data` object is returned with the `signature` section embedded inside it. The top-level fields (`signature`, `public_key`, `algorithm`) mirror the embedded values for convenience.

**Status codes:**

| Code | Condition |
|---|---|
| `200` | Signed successfully |
| `400` | No signing key found (generate one with `POST /auth/gen-key`) |

---

### `POST /api/v1/lock/update-with-fix`

Check packages for known CVEs and automatically bump constraints to fixed versions. Mirrors `udr update --fix-cve`.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "lock_data": {
    "packages": {
      "numpy": {"ecosystem": "pypi", "resolved_version": "1.24.0"}
    }
  },
  "package": "numpy"
}
```

If `package` is omitted, all packages are checked.

**Response:**

```json
{
  "status": "success",
  "fixes": {"numpy": "1.24.3"},
  "lock_data": {"packages": {"numpy": {"ecosystem": "pypi", "resolved_version": "1.24.0", "constraint": ">=1.24.3"}}}
}
```

**Status codes:**

| Code | Condition |
|---|---|
| `200` | Check complete (check `fixes` count) |

---

### `POST /api/v1/lock/update-manifests`

Suggest version bump targets from lock data. Mirrors `udr update`.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "lock_data": {"packages": {"flask": {"ecosystem": "pypi", "resolved_version": "3.0.0", "constraint": ">=2.0"}}},
  "manifest_contents": {"requirements.txt": "flask>=2.0\n"}
}
```

**Response:**

```json
{
  "status": "success",
  "suggestions": {
    "pypi": [{"package": "flask", "current_constraint": ">=2.0", "resolved_version": "3.0.0", "ecosystem": "pypi"}]
  },
  "note": "Use `udr update` to apply manifest changes (requires filesystem access)."
}
```

This endpoint is analysis-only. It does not write to files — use the CLI for actual manifest updates.

---

### `POST /api/v1/lock/report`

Generate a human-readable summary report from lock data. Mirrors `udr lock --report`.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "lock_data": {"packages": {"numpy": {"ecosystem": "pypi", "resolved_version": "1.26.0", "direct": true}}}
}
```

**Response:**

```json
{
  "status": "success",
  "report": "=== Dependency Lock Report ===\n...",
  "summary": {"total": 1, "direct": 1, "transitive": 0, "ecosystems": {"pypi": 1}, "vulnerabilities": 0},
  "cves": [
    {"package": "numpy", "id": "CVE-2023-1234", "severity": "HIGH"}
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `report` | string | Formatted plain-text report |
| `summary` | object | Aggregated counts (total, direct, transitive, ecosystems, vulnerabilities) |
| `cves` | array | CVE entries found in packages (empty if none) |

---

### `POST /api/v1/lock/apply-pinning`

Apply pin/block/freeze constraints to lock data. Mirrors `udr lock --pin/--block/--freeze --pin-mode`.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "lock_data": {"packages": {"numpy": {"ecosystem": "pypi", "resolved_version": "1.26.0", "direct": true}}},
  "pin": ["numpy==1.25.0"],
  "block": ["torch"],
  "pin_mode": "major",
  "freeze": false
}
```

**Response:**

```json
{
  "status": "success",
  "lock_data": {"packages": {"numpy": {"ecosystem": "pypi", "resolved_version": "1.25.0", "direct": true, "constraint": "==1.25.0"}}},
  "pinning_policy": {"pinned": {"numpy": "1.25.0"}}
}
```

---

## Index Management

Manage offline SQLite indexes used for local package resolution without network access. Mirrors the `udr index` CLI subcommand.

### `GET /api/v1/index/status`

List local offline indexes and their metadata.

**Auth:** Yes (anonymous in local mode)

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `ecosystem` | string | — | Filter to one ecosystem |

**Response:**

```json
{
  "status": "success",
  "indexes": [
    {
      "ecosystem": "pypi",
      "path": "/home/user/.cache/udr/indexes/pypi.db",
      "size_bytes": 1048576,
      "packages": 15000,
      "versions": 120000,
      "metadata": {
        "index_version": "1",
        "updated_at": "2026-07-06T10:00:00Z"
      }
    }
  ]
}
```

**Status codes:**

| Code | Condition |
|---|---|
| `200` | Indexes listed |
| `404` | No index for the specified ecosystem |

---

### `POST /api/v1/index/pull`

Download a pre-built SQLite index from a remote URL and install it locally.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "url": "https://index-server.example.com/pypi.db",
  "ecosystem": "pypi"
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `url` | string | (required) | URL to download the index from (http/https) |
| `ecosystem` | string | auto-detected | Ecosystem name (derived from URL filename if omitted) |

**Response:**

```json
{
  "status": "success",
  "ecosystem": "pypi",
  "index": {
    "ecosystem": "pypi",
    "path": "/home/user/.cache/udr/indexes/pypi.db",
    "size_bytes": 1048576,
    "packages": 15000
  }
}
```

**Status codes:**

| Code | Condition |
|---|---|
| `200` | Index downloaded and installed |
| `400` | Invalid URL or could not determine ecosystem |
| `502` | Download failed |

---

### `POST /api/v1/index/build`

Build an offline index from package version data.

**Auth:** Yes (anonymous in local mode)

**Request body:**

```json
{
  "ecosystem": "pypi",
  "packages": [
    {
      "name": "requests",
      "versions": [
        {
          "version": "2.31.0",
          "release_date": "2023-05-22",
          "requires_python": ">=3.7",
          "dependencies": {"urllib3": ">=1.21.1,<3"}
        }
      ]
    }
  ]
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `ecosystem` | string | (required) | Target ecosystem |
| `packages` | array | (required) | Package version data (name + versions list) |

**Response:**

```json
{
  "status": "success",
  "ecosystem": "pypi",
  "packages_indexed": 1,
  "index": {
    "ecosystem": "pypi",
    "packages": 15001
  }
}
```

**Status codes:**

| Code | Condition |
|---|---|
| `200` | Index built |
| `400` | No packages provided |

---

### `POST /api/v1/index/sync-all`

Sync local indexes for all ecosystems from remote registries. Mirrors `udr index sync --all`.

**Auth:** Yes (anonymous in local mode)

**Response:**

```json
{
  "status": "success",
  "results": [
    {"ecosystem": "pypi", "status": "ok", "packages_synced": 15000},
    {"ecosystem": "npm", "status": "error", "error": "timeout"}
  ],
  "total": 15000
}
```

**Status codes:**

| Code | Condition |
|---|---|
| `200` | Sync completed (individual results may have errors) |

---

## Check

Check endpoints scan lock file package data for security, compliance, and policy violations.

### `POST /api/v1/check/cve`

Scan lock file packages against the OSV vulnerability database for known CVEs. Mirrors `udr check --cve`.

**Rate limit:** 10/minute  
**Auth:** Yes (anonymous in local mode)

**Request:**

```json
{
  "packages": {
    "numpy": {"ecosystem": "pypi", "resolved_version": "1.24.0"},
    "flask": {"ecosystem": "pypi", "resolved_version": "2.0.0"}
  }
}
```

The `packages` dict maps package name → metadata dict (must include `ecosystem` and `resolved_version`).

**Response:**

```json
{
  "status": "success",
  "total_vulnerabilities": 2,
  "results": [
    {
      "package": "numpy",
      "version": "1.24.0",
      "cve_id": "CVE-2023-1234",
      "severity": "HIGH",
      "summary": "Buffer overflow in numpy.ufunc"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | `"success"` always |
| `total_vulnerabilities` | int | Count of found CVEs |
| `results` | array | Per-package CVE entries (package, version, cve_id, severity, summary) |

**Status codes:**

| Code | Condition |
|---|---|
| `200` | Scan complete |

---

### `POST /api/v1/check/license`

Check lock file packages for license compliance using the SPDX alias table. Mirrors `udr check --license`.

**Rate limit:** 10/minute  
**Auth:** Yes (anonymous in local mode)

**Request:** Same shape as `/check/cve` — `{"packages": {"name": {"ecosystem": "...", "resolved_version": "..."}}}`.

**Response:**

```json
{
  "status": "violation",
  "total_checked": 5,
  "denied": ["package-a"],
  "warnings": ["package-b"],
  "results": {
    "package-a": {"license": "GPL-3.0", "status": "denied"},
    "package-b": {"license": "LGPL-2.1", "status": "warning"},
    "package-c": {"license": "MIT", "status": "allowed"}
  }
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"`, `"warning"`, or `"violation"` |
| `total_checked` | int | Number of packages with license data |
| `denied` | array | Package names with denied licenses |
| `warnings` | array | Package names with warning-level licenses |
| `results` | dict | Package → `{license, status}` mapping |

---

### `POST /api/v1/check/deprecated`

Check lock file packages for deprecated/yanked version markers. Mirrors `udr check --deprecated`.

**Rate limit:** 10/minute  
**Auth:** Yes (anonymous in local mode)

**Request:** Same shape as `/check/cve`.

**Response:**

```json
{
  "status": "issues_found",
  "total_deprecated": 1,
  "has_yanked": true,
  "results": [
    {"package": "old-pkg", "version": "0.5.0", "status": "yanked"}
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | `"success"` if no issues, `"issues_found"` if any deprecated/yanked |
| `total_deprecated` | int | Count of deprecated/yanked packages |
| `has_yanked` | bool | Whether any are yanked (vs just deprecated) |
| `results` | array | Per-package entries with `status`: `"deprecated"` or `"yanked"` |

---

### `POST /api/v1/check/policy`

Evaluate lock file packages against a policy file with 10 rule types. Mirrors `udr check --policy`.

**Rate limit:** 10/minute  
**Auth:** Yes (anonymous in local mode)

**Request:**

```json
{
  "packages": {
    "numpy": {"ecosystem": "pypi", "resolved_version": "1.24.0", "license": "BSD-3-Clause"}
  },
  "policy_yaml": "rules:\n  - rule: no-gpl\n    severity: error\n  - rule: max-vulnerabilities\n    max: 3\n    severity: warning\n"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `packages` | dict | yes | Package name → metadata (same shape as `/check/cve`) |
| `policy_yaml` | string | no | Inline YAML policy content. If omitted, reads `udr-policy.yaml` from server filesystem |

**Response:**

```json
{
  "status": "violation",
  "total_violations": 1,
  "results": [
    {"rule": "no-gpl", "severity": "error", "message": "numpy is under GPL-3.0 license"},
    {"rule": "max-vulnerabilities", "severity": "warning", "message": "3 vulnerabilities found (max 3)"}
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"`, `"warning"`, or `"violation"` based on error-severity violations |
| `total_violations` | int | Count of all violations (error + warning) |
| `results` | array | Per-rule violations with `rule`, `severity`, and `message` |

---

## SBOM

### `POST /api/v1/sbom`

Generate a Software Bill of Materials from lock data in SPDX 2.3 or CycloneDX 1.5 format. Mirrors `udr sbom`.

**Rate limit:** 10/minute  
**Auth:** Yes (anonymous in local mode)

**Request:**

```json
{
  "lock_data": {
    "packages": {
      "numpy": {"ecosystem": "pypi", "resolved_version": "1.26.0", "license": "BSD-3-Clause"}
    }
  },
  "format": "spdx"
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `lock_data` | dict | (required) | Lock file data with packages section |
| `format` | string | `"spdx"` | Output format: `"spdx"` or `"cyclonedx"` |

**Response (SPDX):**

```json
{
  "status": "success",
  "format": "spdx",
  "sbom": {
    "spdxVersion": "SPDX-2.3",
    "dataLicense": "CC0-1.0",
    "SPDXID": "SPDXRef-DOCUMENT",
    "name": "udr-sbom",
    "packages": [
      {
        "SPDXID": "SPDXRef-numpy",
        "name": "numpy",
        "versionInfo": "1.26.0",
        "supplier": "NOASSERTION",
        "licenseConcluded": "BSD-3-Clause",
        "externalRefs": [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl", "referenceLocator": "pkg:pypi/numpy@1.26.0"}]
      }
    ],
    "relationships": []
  }
}
```

With `"format": "cyclonedx"`, the `sbom` object follows the CycloneDX 1.5 JSON schema instead.

**Status codes:**

| Code | Condition |
|---|---|
| `200` | SBOM generated |
| `400` | Unsupported format |

---

## Completion

### `GET /api/v1/completion/{shell}`

Generate a shell completion script for `udr` commands. Returns raw shell script text suitable for sourcing.

**Auth:** Yes (anonymous in local mode)

**Path parameters:**

| Parameter | Type | Description |
|---|---|---|
| `shell` | string | One of `bash`, `zsh`, or `fish` |

**Response:** `text/plain` — a shell script.

```bash
# Example: save and source
curl http://localhost:8000/api/v1/completion/bash > udr-completion.sh
source udr-completion.sh
```

**Status codes:**

| Code | Condition |
|---|---|
| `200` | Completion script returned |
| `400` | Unsupported shell |

---

## Infrastructure

### `GET /metrics`

Prometheus metrics endpoint. Not included in OpenAPI schema. Only available when `prometheus-fastapi-instrumentator` is installed.

### `GET /api/v1/docs`

Swagger UI documentation (auto-generated by FastAPI).

### `GET /api/v1/redoc`

ReDoc documentation (auto-generated by FastAPI).

### `GET /api/v1/openapi.json`

OpenAPI 3.0 JSON schema (auto-generated by FastAPI).

---

## CLI ↔ API Mapping

Every API endpoint maps to a CLI command when `udr serve` is running:

| API Endpoint | Method | CLI Equivalent | Notes |
|---|---|---|---|
| `GET /api/v1/health` | GET | `udr check` | System health |
| `GET /api/v1/system/info` | GET | `udr check` | System info |
| `POST /api/v1/packages/resolve` | POST | `udr resolve` | Same request/response shape |
| `POST /api/v1/packages/export` | POST | `udr lock --export` | Export resolved deps |
| `GET /api/v1/packages/export-formats` | GET | — | API-only: list available export formats |
| `GET /api/v1/packages/search` | GET | `udr search` | Same query parameters, response shape |
| `GET /api/v1/packages/{eco}/{name}/details` | GET | `udr details` | Same |
| `GET /api/v1/packages/ecosystems` | GET | `udr list-ecosystems` | Same response shape |
| `POST /api/v1/generate-lock` | POST | `udr lock --json` | Also supports `?export_format=` (mirrors `--export`) |
| `POST /api/v1/graph` | POST | `udr graph` | Same |
| `POST /api/v1/verify` | POST | `udr verify` | Same |
| `POST /api/v1/update` | POST | `udr update` | Same |
| `POST /api/v1/install-commands` | POST | `udr install` | API returns commands, doesn't run them |
| `POST /api/v1/restore-commands` | POST | `udr install --restore` | Same |
| `POST /api/v1/scan/github` | POST | `udr scan --github` | Same |
| `POST /api/v1/scan/local` | POST | `udr scan --directory` | Same |
| `POST /api/v1/why` | POST | `udr why` | Same |
| `POST /api/v1/outdated` | POST | `udr outdated` | Same |
| `POST /api/v1/diff` | POST | `udr diff` | Same |
| `GET /api/v1/index/status` | GET | `udr index status` | Same response shape |
| `POST /api/v1/index/pull` | POST | `udr index pull` | Same |
| `POST /api/v1/index/build` | POST | `udr index build` | Same |
| `POST /api/v1/index/sync-all` | POST | `udr index sync --all` | Same |
| `POST /api/v1/check/cve` | POST | `udr check --cve` | CVE scanning from lock data |
| `POST /api/v1/check/license` | POST | `udr check --license` | License compliance |
| `POST /api/v1/check/deprecated` | POST | `udr check --deprecated` | Deprecated/yanked check |
| `POST /api/v1/check/policy` | POST | `udr check --policy` | Policy engine |
| `POST /api/v1/sbom` | POST | `udr sbom` | SPDX/CycloneDX SBOM |
| `POST /api/v1/lock/check` | POST | `udr lock --check` | CI drift detection |
| `POST /api/v1/lock/sign` | POST | `udr lock --sign` | Ed25519 signing |
| `POST /api/v1/lock/update-with-fix` | POST | `udr update --fix-cve` | CVE auto-fix |
| `POST /api/v1/lock/update-manifests` | POST | `udr update` | Suggests version bumps |
| `POST /api/v1/lock/report` | POST | `udr lock --report` | Human-readable summary |
| `POST /api/v1/lock/apply-pinning` | POST | `udr lock --pin/--block/--freeze` | Pin/block/freeze constraints |
| `GET /api/v1/auth/signing-key` | GET | `udr auth show-key` | Show signing key |
| `POST /api/v1/auth/gen-key` | POST | `udr auth gen-key` | Generate signing key |
| `GET /api/v1/completion/{shell}` | GET | `udr completion {shell}` | Returns raw shell script |

**API-only endpoints** (no CLI equivalent): `/api/v1/packages/{eco}/{name}/versions`, `/api/v1/packages/{eco}/{name}/dependencies`, `/api/v1/packages/{eco}/{name}/compatibility`, `/api/v1/packages/export-formats`, `/api/v1/system/check-compatibility`, `/api/v1/lock/*`, `/api/v1/check/*`, `/api/v1/sbom`, auth endpoints.

**CLI-only features** (no API equivalent): `udr serve` (starts the API), interactive TUI modes (`-i/--interactive`), manifest file writing (`lock -y`, `lock --dry-run`), local package manager execution (`install`), `udr why --all`.

---

## Middleware & Request Processing

Requests pass through middleware in this order:

| Order | Middleware | Purpose |
|---|---|---|
| 1 | `SlowAPIMiddleware` | Rate limiting (slowapi) |
| 2 | `MaintenanceModeMiddleware` | Block requests during maintenance |
| 3 | `SecurityHeadersMiddleware` | CORS, CSP, HSTS, X-Frame-Options |
| 4 | `RequestSizeLimitMiddleware` | Max request body size |
| 5 | `CompressionMiddleware` | Gzip compression |
| 6 | `CacheMiddleware` | GET response caching |
| 7 | `MetricsMiddleware` | Request/response metrics |
| 8 | `PerformanceMiddleware` | Slow request logging, X-Response-Time |
| 9 | `LoggingMiddleware` | Request/response structured logs |
| 10 | `AuditLogMiddleware` | Audit logs for POST/PUT/PATCH/DELETE |
| 11 | `CSRFProtectionMiddleware` | Double-submit cookie CSRF |
| 12 | `CorrelationIDMiddleware` | X-Correlation-ID propagation |
| 13 | `add_process_time_header` | X-Process-Time header |
| 14 | `log_requests` | Structured request logging |
| 15 | `CORSMiddleware` | CORS (configurable via `ALLOWED_ORIGINS` env var) |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ENABLE_AUTH` | `true` | Enable JWT auth and auth endpoints |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins |
| `REDIS_URL` | — | Redis connection for rate limiting + caching |
| `SENTRY_DSN` | — | Sentry error tracking |
| `SECRET_KEY` | (auto) | JWT signing secret (auto-generated if not set) |
| `ENVIRONMENT` | `development` | `development` or `production` |
| `UDR_STANDALONE` | `false` | Skip database check on startup |
| `DATABASE_URL` | — | Database connection string (required unless standalone) |
| `SOLVER_REJECT_DEPRECATED` | `false` | Reject deprecated/yanked packages during resolution |
| `TARGET_OS` | — | Target OS for cross-compilation (`linux`, `windows`, `darwin`) |
| `TARGET_ARCH` | — | Target CPU architecture for cross-compilation (`x86_64`, `aarch64`) |
| `TARGET_CUDA` | — | Target CUDA version for cross-compilation (e.g. `12.1`) |
| `PIN_INTEGRITY` | `false` | Verify package integrity hashes in lock file |
| `BFS_BATCH_SIZE` | `20` | Batch size for parallel BFS dependency fetching |
| `INDEX_AUTO_SYNC` | `false` | Auto-sync stale local indexes before resolution |
