# UDR Frontend — Browser-Based WASM Frontend

A standalone single-page web application for the Universal Dependency Resolver. Talks to the backend REST API — no build step, no npm, no CDN dependencies. Pure vanilla HTML/CSS/JS.

## Quick Start

1. **Ensure the backend API is running** on `http://localhost:8199`:
   ```bash
   cd /home/user/universal-dependency-resolver
   python run.py  # starts on port 8199
   ```

2. **Serve the frontend** with any static file server:
   ```bash
   cd frontend
   python -m http.server 3000
   # or: npx serve .
   # or: python -m http.server 3000 --bind 0.0.0.0
   ```

3. **Open in browser**: [http://localhost:3000](http://localhost:3000)

4. The header status indicator should show **Connected** (green dot).

## Features

| Page | Route | Description |
|------|-------|-------------|
| **Dashboard** | `#dashboard` | API health, lock file summary, quick actions |
| **Search** | `#search` | Cross-ecosystem package search with detail drill-down |
| **Graph** | `#graph` | Dependency tree visualization with collapsible nodes |
| **Lock Viewer** | `#lock` | Upload, inspect, verify, and export `udr.lock` files |
| **CVE Check** | `#cve` | OSV-based vulnerability scanning with severity coloring |
| **SBOM** | `#sbom` | Generate SPDX 2.3 and CycloneDX 1.5 SBOMs |
| **Policy** | `#policy` | YAML-based policy enforcement (licenses, vulns, blocked packages) |
| **System** | `#system` | Backend system scanner results (CPU, GPU, CUDA, runtimes) |

## Architecture

```
frontend/
  index.html         — Single HTML file, loads CSS + JS
  css/style.css      — Dark theme, responsive, CSS custom properties
  js/
    api.js           — BackendAPI class (fetch wrapper, 20+ methods)
    utils.js         — Formatting, SBOM generation, OSV queries, policy engine
    app.js           — Router, state management, page rendering
  README.md          — This file
```

- **Hash-based routing**: `#dashboard`, `#search`, `#graph`, etc.
- **State management**: In-memory `App.state` object (lock data, search results, CVE results)
- **File loading**: Drag-and-drop or click-to-browse for lock files and policy YAML
- **No build step**: Vanilla JS modules loaded via `<script>` tags

## API Endpoints Used

| Endpoint | Method | Used By |
|----------|--------|---------|
| `/healthz` | GET | Header status indicator |
| `/api/v1/health` | GET | Dashboard health checks |
| `/api/v1/system/info` | GET | System info page, dashboard |
| `/api/v1/packages/search` | GET | Package search |
| `/api/v1/packages/{eco}/{name}/details` | GET | Package detail view |
| `/api/v1/packages/{eco}/{name}/versions` | GET | Package versions |
| `/api/v1/packages/{eco}/{name}/dependencies` | GET | Package dependencies |
| `/api/v1/graph` | POST | Dependency graph |
| `/api/v1/verify` | POST | Lock verification |
| `/api/v1/outdated` | POST | Outdated check |
| `/api/v1/install-commands` | POST | Install commands |

CVE scanning queries the [OSV API](https://osv.dev) directly from the browser.

## Customization

To point to a different backend URL, edit the `baseURL` parameter in `js/api.js`:

```js
const api = new BackendAPI('http://your-host:8199');
```
