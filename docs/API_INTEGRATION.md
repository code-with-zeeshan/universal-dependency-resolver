# API Integration Guide

How to integrate the UDR API into your system.

---

## Quick Start

```bash
# Start the server
udr serve --port 8000 --host 0.0.0.0

# Or with env overrides
ENABLE_AUTH=false UDR_PORT=8000 udr serve
```

With auth disabled, all 54 API routes are available immediately.

---

## Configuration Reference

| Env Var | Default | Description |
|---|---|---|
| `ENABLE_AUTH` | `true` | `false` = public mode (no auth), `true` = SaaS mode (JWT + API key) |
| `UDR_PORT` | `8000` | Server listen port |
| `UDR_HOST` | `0.0.0.0` | Server bind address |
| `DATABASE_URL` | `sqlite:///...` | Database connection string |
| `API_RATE_LIMIT` | `100` | Requests per minute (SaaS mode) |
| `SOLVER_API_TIMEOUT` | `60` | SAT solver timeout in seconds |
| `REDIS_URL` | *(optional)* | Enables Redis-backed rate limiting |

---

## Making API Calls

### Python (httpx)

```python
import httpx

BASE = "http://localhost:8000/api/v1"

def sync_example():
    with httpx.Client() as client:
        # Lock from manifest content (mirrors `udr lock`)
        r = client.post(f"{BASE}/generate-lock", json={
            "manifest_contents": {
                "requirements.txt": "numpy>=1.24\npandas>=2.0\nclick>=8.0"
            }
        })
        lock = r.json()["lock_data"]
        print(f"Resolved {len(lock['packages'])} packages")

        # Get install commands
        r = client.post(f"{BASE}/install-commands", json={
            "lock_data": lock
        })
        for cmd in r.json()["commands"]:
            print(f"  {cmd['ecosystem']}: {cmd['command']}")

        # Check outdated packages
        r = client.post(f"{BASE}/outdated", json={"lock_data": lock})
        for pkg in r.json()["packages"]:
            print(f"  {pkg['name']}: {pkg['current']} → {pkg['latest']}")
```

### Python (async)

```python
import asyncio
import httpx

async def example():
    async with httpx.AsyncClient() as client:
        # Scan a GitHub repo
        r = await client.post(f"{BASE}/scan/github", json={
            "repo_url": "https://github.com/user/project",
            "branch": "main"
        })
        data = r.json()

        if data["status"] == "success":
            # Generate lock from scan results
            r2 = await client.post(f"{BASE}/generate-lock", json={
                "packages": data["packages"],
                "resolution": data["resolution"],
                "system": data["system"],
                "manifests": data["manifests"],
            })
            lock = r2.json()["lock_data"]

            # Verify lock integrity against registries
            r3 = await client.post(f"{BASE}/verify", json={"lock_data": lock})
            print(r3.json())

asyncio.run(example())
```

### cURL

```bash
# Lock from manifest content
curl -s http://localhost:8000/api/v1/generate-lock \
  -H "Content-Type: application/json" \
  -d '{
    "manifest_contents": {
      "requirements.txt": "numpy>=1.24\npandas>=2.0"
    }
  }' | jq .lock_data.packages | head

# Resolve specific packages with CUDA
curl -s http://localhost:8000/api/v1/packages/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "packages": [
      {"name": "torch", "ecosystem": "pypi"},
      {"name": "tensorflow", "ecosystem": "pypi"}
    ],
    "system_info": {"gpu": {"available": true, "cuda": "12.1"}}
  }' | jq .

# Search packages across all ecosystems
curl -s "http://localhost:8000/api/v1/packages/search?q=requests&ecosystem=pypi" | jq .

# Get package details
curl -s "http://localhost:8000/api/v1/packages/pypi/requests/details" | jq .

# Why was this version selected?
curl -s http://localhost:8000/api/v1/why \
  -H "Content-Type: application/json" \
  -d '{"lock_data": {...}, "package": "urllib3"}' | jq .
```

### Node.js / TypeScript

```typescript
const BASE = "http://localhost:8000/api/v1";

async function lockAndInstall() {
  // Upload project archive
  const form = new FormData();
  const zipFile = fs.readFileSync("project.zip");
  form.append("file", new Blob([zipFile]), "project.zip");

  const scanRes = await fetch(`${BASE}/scan/upload?export=requirements.txt`, {
    method: "POST",
    body: form,
  });
  const scan = await scanRes.json();

  // Generate lock
  const lockRes = await fetch(`${BASE}/generate-lock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      manifest_contents: {
        "requirements.txt": scan.export,
      },
    }),
  });
  const { lock_data } = await lockRes.json();
  console.log(`Locked ${Object.keys(lock_data.packages).length} packages`);
}
```

---

## Workflows

### CI Pipeline (GitHub Actions)

```yaml
jobs:
  verify-deps:
    steps:
      - uses: actions/checkout@v4
      - run: |
          curl -s http://udr-server:8000/api/v1/generate-lock \
            -H "Content-Type: application/json" \
            -d "$(python3 ci/build_manifest_payload.py)" \
            | jq . > udr.lock
          git diff --exit-code udr.lock
```

### Multi-Ecosystem Monorepo

```json
// POST /api/v1/generate-lock
{
  "manifest_contents": {
    "backend/requirements.txt": "fastapi>=0.100\nsqlalchemy>=2.0",
    "frontend/package.json": "{\"dependencies\": {\"react\": \"^18.2\"}}",
    "services/Cargo.toml": "[dependencies]\nserde = \"1.0\"\ntokio = { version = \"1\", features = [\"full\"] }"
  },
  "manifest_filter": "requirements.txt",
  "system": {
    "gpu": {"available": true, "cuda": "12.1"}
  }
}
```

---

## Auth Mode (SaaS)

When `ENABLE_AUTH=true`, all endpoints require authentication.

```python
BASE = "http://localhost:8000/api/v1"

with httpx.Client() as client:
    # Register
    r = client.post(f"{BASE}/auth/register", json={
        "email": "user@example.com",
        "password": "securepass"
    })
    token = r.json()["access_token"]

    # Or login
    r = client.post(f"{BASE}/auth/login", json={
        "email": "user@example.com",
        "password": "securepass"
    })
    token = r.json()["access_token"]

    # Use JWT in subsequent requests
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(f"{BASE}/generate-lock", json={
        "manifest_contents": {"requirements.txt": "numpy>=1.24"}
    }, headers=headers)

    # API key alternative
    headers = {"X-API-Key": "your-api-key"}
```

### Auth Endpoints (14 total)

| Endpoint | Purpose |
|---|---|
| `POST /auth/register` | Create account |
| `POST /auth/login` | Get JWT |
| `POST /auth/token` | OAuth2-compatible token endpoint |
| `POST /auth/refresh` | Refresh JWT |
| `GET /api/v1/auth/profile` | Current user info |
| `PUT /auth/me` | Update profile |
| `POST /api/v1/auth/change-password` | Change password |
| `POST /auth/api-keys` | Create API key |
| `GET /auth/api-keys` | List API keys |
| `DELETE /auth/api-keys/{id}` | Revoke API key |
| `POST /auth/logout` | Invalidate session |
| `POST /auth/check-username` | Check username availability |
| `POST /auth/gen-key` | Generate signing key |
| `GET /auth/signing-key` | Get signing public key |
| `POST /auth/verify` | Verify auth status |

---

## Endpoint Visibility

| Visibility | Count | Notes |
|---|---|---|
| Public (no auth) | 43 | Business + infra routes |
| Auth-only | 16 | Only mounted when `ENABLE_AUTH=true` |
| **Total** | **54** | |

---

## Error Handling

All errors return a consistent envelope:

```json
{
  "error": {
    "message": "Package not found in ecosystem",
    "type": "http_error",
    "status_code": 404,
    "timestamp": "2026-07-03T12:00:00"
  }
}
```

Common status codes:

| Code | Meaning |
|---|---|
| `400` | Invalid request (missing fields, bad format) |
| `404` | Package/manifest not found |
| `422` | Validation error |
| `429` | Rate limit exceeded |
| `500` | Internal error (check server logs) |

---

## CLI ↔ API Mapping

See `docs/API.md` for the full endpoint reference, or `docs/CLI.md` for CLI usage.
