# UDR - Universal Dependency Resolver

VSCode extension for the Universal Dependency Resolver (`udr`).

## Features

- **Lock File Viewer** — Tree view of `udr.lock` grouped by ecosystem with version, license, and CVE count
- **CVE Diagnostics** — Inline decorations and Problems panel entries for known vulnerabilities
- **Commands** — Run all `udr` CLI commands from the Command Palette
- **Manifest Editing** — Right-click anywhere in manifest files to add, update, or remove dependencies
- **Status Bar** — Quick overview of lock file health and CVE counts

## Commands

| Command | Description |
|---------|-------------|
| `UDR: Check lock file` | Run `udr check --cve --deprecated` |
| `UDR: Update package` | Re-resolve a specific package |
| `UDR: Generate SBOM` | Generate SPDX/CycloneDX SBOM |
| `UDR: Verify lock` | Validate lock file integrity |
| `UDR: Check policies` | Run `udr check --policy` |
| `UDR: Fix CVEs` | Auto-fix vulnerable packages |
| `UDR: Lock (resolve)` | Run `udr lock` |
| `UDR: Lock check (CI)` | Run `udr lock --check` |
| `UDR: Show dependency graph` | Open webview with dependency graph |
| `UDR: Add dependency` | Add a dependency to a manifest |
| `UDR: Update dependency` | Update a dependency version |
| `UDR: Remove dependency` | Remove a dependency |

## Requirements

- `udr` CLI installed and on PATH (or configure `udr.cliPath`)
- Workspace with a `udr.lock` file or supported manifest files

## Extension Settings

- `udr.cliPath`: Path to udr CLI (default: `udr`)
- `udr.backendUrl`: Backend API URL (default: `http://localhost:8199`)
- `udr.lockFileName`: Lock file name (default: `udr.lock`)
- `udr.autoCheckOnSave`: Auto-check CVE on lock file save
- `udr.cveSeverityThreshold`: Minimum severity for Problems panel
