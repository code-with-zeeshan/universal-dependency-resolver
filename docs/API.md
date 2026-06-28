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

In `local` mode, the `get_current_user` dependency returns a mock anonymous user (id=1, username="anonymous"). All auth endpoints are **not mounted** in `local` mode.

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
| 16 | POST | `/api/v1/auth/check-email` | No | 30/min |
| **System** | | | | |
| 17 | GET | `/api/v1/system/info` | Yes | 30/min |
| 18 | POST | `/api/v1/system/check-compatibility` | Yes | 10/min |
| **Packages** | | | | |
| 19 | POST | `/api/v1/packages/resolve` | Yes | 10/min |
| 20 | POST | `/api/v1/packages/export` | Yes | 20/min |
| 21 | GET | `/api/v1/packages/export-formats` | Yes | 60/min |
| 22 | GET | `/api/v1/packages/search` | Yes | 60/min |
| 23 | GET | `/api/v1/packages/{eco}/{name}/details` | Yes | 120/min |
| 24 | GET | `/api/v1/packages/{eco}/{name}/versions` | Yes | 120/min |
| 25 | GET | `/api/v1/packages/{eco}/{name}/dependencies` | Yes | 120/min |
| 26 | GET | `/api/v1/packages/{eco}/{name}/compatibility` | Yes | 120/min |
| 27 | GET | `/api/v1/packages/ecosystems` | Yes | 60/min |
| **Scan** | | | | |
| 28 | POST | `/api/v1/scan/github` | Yes | none |
| 29 | POST | `/api/v1/scan/upload` | Yes | none |
| 30 | POST | `/api/v1/scan/local` | Yes | none |
| **Lock** | | | | |
| 31 | POST | `/api/v1/verify` | Yes | none |
| 32 | POST | `/api/v1/graph` | Yes | none |
| 33 | POST | `/api/v1/update` | Yes | none |
| **Infrastructure** | | | | |
| 34 | GET | `/metrics` | No | none |
| 35 | GET | `/api/v1/docs` | No | none |
| 36 | GET | `/api/v1/redoc` | No | none |
| 37 | GET | `/api/v1/openapi.json` | No | none |

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
  "version": "1.0.0",
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
  "version": "1.0.0",
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

Get list of all 13 supported package ecosystems with capabilities.

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
  "total": 13
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

Lock endpoints mirror `udr verify`, `udr graph`, and `udr update` CLI commands. They accept and return lock data as JSON so clients can manage lock state without file system access.

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
| `ENABLE_AUTH` | `false` | Enable JWT auth and auth endpoints |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins |
| `REDIS_URL` | — | Redis connection for rate limiting + caching |
| `SENTRY_DSN` | — | Sentry error tracking |
| `SECRET_KEY` | (auto) | JWT signing secret (auto-generated if not set) |
| `ENVIRONMENT` | `development` | `development` or `production` |
| `UDR_STANDALONE` | `false` | Skip database check on startup |
| `DATABASE_URL` | — | Database connection string (required unless standalone) |
