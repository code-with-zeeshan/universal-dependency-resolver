# Universal Dependency Resolver

<p align="center">
  <strong>Resolve any package, from any ecosystem, all at once.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/ud-resolver/"><img alt="PyPI" src="https://img.shields.io/pypi/v/ud-resolver?color=blue&label=%F0%9F%93%A6%20PyPI"></a>
  <a href="https://pypi.org/project/ud-resolver/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/ud-resolver?color=important&label=%F0%9F%90%8D%20Python"></a>
  <a href="https://github.com/code-with-zeeshan/universal-dependency-resolver/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/code-with-zeeshan/universal-dependency-resolver?color=success&label=%F0%9F%93%9C%20License"></a>
  <a href="https://github.com/code-with-zeeshan/universal-dependency-resolver/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/code-with-zeeshan/universal-dependency-resolver/ci.yml?color=blueviolet&label=%E2%9C%A8%20CI"></a>
  <a href="https://github.com/code-with-zeeshan/universal-dependency-resolver/actions"><img alt="Tests" src="https://img.shields.io/badge/3681%20unit+96%20integration+77%20e2e-passing-success?logo=pytest&color=success&label=%F0%9F%A7%AA%20Tests"></a>
  <a href="https://github.com/code-with-zeeshan/universal-dependency-resolver/actions"><img alt="Coverage" src="https://img.shields.io/badge/coverage-58%25-yellow?logo=codecov&label=%F0%9F%93%8A%20Coverage"></a>
  <a href="https://github.com/code-with-zeeshan/universal-dependency-resolver/actions"><img alt="mypy" src="https://img.shields.io/badge/mypy-0%20errors-brightgreen?label=%E2%9C%94%20Type%20checked"></a>
  <a href="https://github.com/code-with-zeeshan/universal-dependency-resolver/actions"><img alt="Ruff" src="https://img.shields.io/badge/Ruff-0%20errors-brightgreen?logo=ruff&color=success&label=%F0%9F%90%8D%20Lint"></a>
</p>

---

## One tool for all your dependencies

<div class="grid cards" markdown>

-   :material-package-variant-closed:{ .lg .middle } **25 Ecosystems**

    ---

    Resolve dependencies across **PyPI, npm, Crates.io, Go Modules, Maven, RubyGems, NuGet, Conda, APT, APK, and 17 more** — all in one lock file.

    [:octicons-arrow-right-24: See the full list](USER_GUIDE.md#supported-ecosystems)

-   :material-chip:{ .lg .middle } **System-Aware**

    ---

    Auto-detects **OS, CPU, GPU, CUDA version**. Selects the right `torch+cu121` variant. ROCm and Metal supported too.

    [:octicons-arrow-right-24: Learn more](USER_GUIDE.md#system-aware-resolution)

-   :material-shield-check:{ .lg .middle } **Supply Chain Security**

    ---

    Scan **CVEs across 18 ecosystems** at once. Generate SPDX/CycloneDX SBOMs. Sign lock files with Ed25519.

    [:octicons-arrow-right-24: Check features](USER_GUIDE.md#supply-chain-security)

-   :material-speedometer:{ .lg .middle } **SAT-Powered Solver**

    ---

    Auto-selects Z3, PubGrub, or Hybrid solver per workload. Version clustering. Per-ecosystem isolation. CUDA-aware conflict rules.

    [:octicons-arrow-right-24: How it works](ARCHITECTURE.md)

-   :fontawesome-solid-terminal:{ .lg .middle } **24 CLI Commands**

    ---

    `udr lock`, `udr check`, `udr sbom`, `udr graph`, `udr diff`, `udr why` — full toolkit for CI/CD and daily use.

    [:octicons-arrow-right-24: CLI reference](CLI.md)

-   :material-api:{ .lg .middle } **59 REST API Endpoints**

    ---

    Full programmatic API with Swagger docs. Authentication, rate limiting, webhooks.

    [:octicons-arrow-right-24: API reference](API.md)

</div>

---

## Quick Start

```bash
# Install
pip install ud-resolver

# For full capacity (SAT solvers + system detection):
pip install "ud-resolver[z3,pubgrub,system]"

# Resolve packages from any ecosystem
udr resolve flask>=2.0 react@^18 serde@crates

# Lock your entire project
udr lock

# Check CVEs across all dependencies
udr check --cve

# Start the API server
udr serve --port 8000
```

---

## By the Numbers

| Metric | Value |
|---|---|
| :white_check_mark: Supported ecosystems | **25** (18 resolvable + 7 query-only) |
| :microscope: Tests passing | **3681 unit + 96 integration + 77 e2e** |
| :control_knobs: CLI commands | **24** |
| :globe_with_meridians: API endpoints | **59** |
| :outbox_tray: Export formats | **15** |
| :package: PyPI downloads | [![Downloads](https://pepy.tech/badge/ud-resolver)](https://pepy.tech/project/ud-resolver) |

---

## How It Works

```mermaid
flowchart LR
    A["User Request<br/><code>udr resolve flask react</code>"] --> B
    B["Fetch metadata<br/>from registry APIs"] --> C
    C["Scan system<br/>OS · GPU · CUDA · Python"] --> D
    D["SAT Solver Engine<br/>Per-eco isolation · Version clustering<br/>CUDA-aware conflict resolution"] --> E
    E["Lock / Export<br/>15 formats · udr.lock"]

    B -->|"aiohttp"| F["PyPI · npm · Crates · Maven<br/>+ 14 more registries"]
    C -->|"nvidia-smi"| G["NVIDIA · AMD · Apple Silicon"]
    D -->|"AutoSolver → Z3 / PubGrub / Hybrid"| H["Prefer newer versions<br/>Resolve CUDA variants<br/>Detect cross-eco conflicts"]
```

---

## Components

| Component | What it is | Best for |
|---|---|---|
| :desktop: **CLI** | Terminal tool with 24 commands | CI/CD, scripts, ad-hoc |
| :books: **Python Library** | Importable `backend.*` modules | Embedding in tools |
| :globe_with_meridians: **API Server** | FastAPI REST server + Swagger UI | Programmatic access |
| :desktop: **Desktop App** | Standalone Electron GUI | GUI users, no terminal |
| :earth_africa: **Web UI** | Browser-based SPA | Lightweight browser access |
| :memo: **VS Code Extension** | In-editor dependency management | Developers using VS Code |

---

## Get Involved

:material-bug: Found a bug? [Open an issue](https://github.com/code-with-zeeshan/universal-dependency-resolver/issues)  
:material-lightbulb: Want a feature? [Suggest it](https://github.com/code-with-zeeshan/universal-dependency-resolver/issues)  
:material-star: Love the tool? [Star the repo](https://github.com/code-with-zeeshan/universal-dependency-resolver)

---

[MIT](https://github.com/code-with-zeeshan/universal-dependency-resolver/blob/main/LICENSE) &mdash; free for personal and commercial use.
