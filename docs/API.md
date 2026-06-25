# API Documentation

Auto-generated OpenAPI/Swagger docs at `http://localhost:8000/api/v1/docs` are the authoritative reference. This document provides a conceptual overview and usage examples.

## Overview

| Property | Value |
|----------|-------|
| **Base URL** | `http://localhost:8000/api/v1` |
| **Protocol** | HTTP (HTTPS in production) |
| **Format** | JSON |
| **Versioning** | URL-based (`/api/v1/`) |
| **Documentation** | OpenAPI 3.0 at `/api/v1/docs` |

### Supported Ecosystems

| Ecosystem | Identifier | Search | Dependencies |
|-----------|------------|--------|--------------|
| PyPI | `pypi` | Yes | Yes |
| NPM | `npm` | Yes | Yes |
| Conda | `conda` | Yes | Yes |
| Maven | `maven` | Yes | Yes |
| Crates.io | `crates` | Yes | Yes |

## Authentication

### JWT Tokens

```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "pass"}'

# Use token
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/packages/search?q=flask
```

### API Keys

```bash
curl -H "X-API-Key: udr_<key>" \
  http://localhost:8000/api/v1/packages/search?q=flask
```

### Auth Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | Register new user |
| `/auth/login` | POST | Login, receive JWT |
| `/auth/token` | POST | OAuth2 token endpoint |
| `/auth/refresh` | POST | Refresh access token |
| `/auth/logout` | POST | Logout (discard tokens) |
| `/auth/profile` | GET | Get user profile |
| `/auth/profile` | PUT | Update profile |
| `/auth/change-password` | POST | Change password |
| `/auth/api-keys` | GET | List API keys |
| `/auth/api-keys` | POST | Create API key |
| `/auth/api-keys/{id}` | DELETE | Revoke API key |
| `/auth/verify` | GET | Verify token validity |
| `/auth/check-username` | POST | Check username availability |
| `/auth/check-email` | POST | Check email availability |

## Rate Limiting

Per-endpoint limits (implemented via slowapi):

| Category | Limit | Window |
|----------|-------|--------|
| Search | 60 requests | 1 minute |
| Package Info | 30-120 requests | 1 minute |
| Dependencies | 120 requests | 1 minute |
| Resolution | 10 requests | 1 minute |
| Export | 20 requests | 1 minute |
| System Info | 30 requests | 1 minute |
| Auth (login) | 10 requests | 1 minute |
| Auth (register) | 5 requests | 1 hour |

## Response Format

### Successful Response

```json
{
  "status": "success",
  "data": { ... }
}
```

### Error Response

```json
{
  "error": {
    "message": "Package 'invalid-package' not found in pypi",
    "type": "http_error",
    "status_code": 404,
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

## Package Endpoints

All under `/api/v1/packages`.

### Search Packages

```http
GET /api/v1/packages/search?q=<query>&ecosystems=<list>&limit=<n>&sort_by=<field>&python_version=<ver>
```

**Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | string | Yes | Search query |
| `ecosystems` | string | No | Comma-separated list |
| `limit` | int | No | 1-100, default 20 |
| `sort_by` | string | No | `relevance`, `downloads`, `name`, `updated` |
| `python_version` | string | No | Filter by Python version |

**Example:**
```bash
curl "http://localhost:8000/api/v1/packages/search?q=flask&ecosystems=pypi&limit=5"
```

**Response:**
```json
{
  "status": "success",
  "query": "flask",
  "total_count": 42,
  "results": {
    "pypi": [
      { "name": "Flask", "version": "2.3.3", "description": "A simple framework...", "downloads": 50000000 }
    ]
  },
  "filters_applied": {
    "ecosystems": ["pypi"],
    "sort_by": "relevance"
  }
}
```

### Get Package Info

```http
GET /api/v1/packages/{ecosystem}/{name}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/packages/pypi/flask"
```

### Get Package Details

```http
GET /api/v1/packages/{ecosystem}/{name}/details?include_metrics=true
```

### Get Package Versions

```http
GET /api/v1/packages/{ecosystem}/{name}/versions?include_prerelease=true&compatible_with=os=linux,python=3.9
```

### Get Package Dependencies

```http
GET /api/v1/packages/{ecosystem}/{name}/dependencies?version=2.3.3&recursive=true&max_depth=2
```

### Get Package Compatibility

```http
GET /api/v1/packages/{ecosystem}/{name}/compatibility?version=2.13.0
```

### Report Compatibility

```http
POST /api/v1/packages/{ecosystem}/{name}/compatibility/report
```

```json
{
  "version": "2.13.0",
  "system_info": { "os": "linux", "python_version": "3.9" },
  "works": true,
  "notes": "Installed successfully"
}
```

### Resolve Dependencies

```http
POST /api/v1/packages/resolve
```

```json
{
  "packages": [
    { "name": "flask", "ecosystem": "pypi", "version": ">=2.0.0" },
    { "name": "django", "ecosystem": "pypi", "version": ">=4.0.0" }
  ],
  "system_info": { "os": "linux", "python": "3.9" },
  "options": {
    "auto_detect_system": true,
    "prefer_compatibility": true
  }
}
```

### Export Configuration

```http
POST /api/v1/packages/export
```

```json
{
  "resolved_packages": { "flask": "2.3.3", "django": "4.2.5" },
  "format": "requirements.txt",
  "options": { "include_comments": true, "pin_versions": true }
}
```

### Get Export Formats

```http
GET /api/v1/packages/export-formats
```

Returns 12 supported formats: requirements.txt, package.json, environment.yml, pyproject.toml, Dockerfile, docker-compose.yml, install.sh, install.bat, CMakeLists.txt, cargo.toml, build.gradle, pom.xml.

### Compare Packages

```http
GET /api/v1/packages/compare?packages=flask:pypi,express:npm
```

### List Ecosystems

```http
GET /api/v1/packages/ecosystems
```

## System Endpoints

All under `/api/v1/system`.

### Get System Info

```http
GET /api/v1/system/info?detailed=true
```

**Response (simple):**
```json
{
  "status": "success",
  "system": {
    "os": "Linux 5.15.0",
    "cpu": "Intel(R) Core(TM) i7",
    "gpu": "NVIDIA GeForce RTX 2060",
    "cuda": "12.0",
    "python": "3.13.1"
  }
}
```

### Check System Compatibility

```http
POST /api/v1/system/check-compatibility
```

### Get GPU Info

```http
GET /api/v1/system/gpu/info
```

### Get Runtime Info

```http
GET /api/v1/system/runtime/{runtime}
```

Runtimes: python, node, java, docker, rust, go, julia, r, dotnet, ruby, php, kotlin, scala.

### Analyze Environment File

```http
POST /api/v1/system/analyze-environment
```

Upload a requirements.txt, package.json, pyproject.toml, etc. to analyze packages and detect conflicts.

### Run Benchmarks

```http
GET /api/v1/system/benchmarks?comprehensive=true
```

CPU, memory, disk, GPU (if available) benchmarks.

## Scan Endpoints

### Scan GitHub Repository

```http
POST /api/v1/scan/github
Content-Type: application/json

{ "repo_url": "https://github.com/user/project", "branch": "main" }
```

Downloads repo, detects manifests (package.json, requirements.txt, etc.), resolves all dependencies.

### Scan Uploaded Archive

```http
POST /api/v1/scan/upload
Content-Type: multipart/form-data

file: <project.zip>
```

### Scan Local Directory

```http
POST /api/v1/scan/local
Content-Type: application/json

{ "directory_path": "/path/to/project" }
```

Only works when backend runs on the same machine.

## Health Check

```http
GET /api/v1/health
```

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0",
  "checks": {
    "database": { "status": "healthy" },
    "external_apis": { "status": "healthy" }
  }
}
```

Redis is checked only if `REDIS_URL` is configured. Its status does not affect overall health.

## Root Endpoint

```http
GET /
```

Returns API name, version, and links to docs and endpoints.

## HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 409 | Conflict |
| 422 | Validation Error |
| 429 | Rate Limit Exceeded |
| 500 | Internal Server Error |
| 502 | Bad Gateway |
| 503 | Service Unavailable |
