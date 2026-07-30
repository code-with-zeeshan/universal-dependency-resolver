# Desktop Application

## Overview

The UDR Desktop app is an Electron-based GUI bundling the backend (compiled via PyInstaller) with the same HTML/CSS/JS interface used by the web frontend. No Python, Node.js, or package managers required.

**Relationship to the web frontend:** The Desktop app wraps the standalone web frontend (`frontend/`) inside Electron, adding native features (system tray, auto-update, keyboard shortcuts). The same hash-routed pages (`#dashboard`, `#search`, `#graph`, etc.) work identically in both the browser and the Desktop app. The web frontend can also be used standalone with `udr serve` — no Electron needed.

---

## Downloads

| Platform | Architecture | File | Size |
|---|---|---|---|
| Windows | x86_64 | `udr-desktop-win32-x64-{version}.exe` | ~120 MB |
| macOS | Intel (x86_64) | `udr-desktop-darwin-x64-{version}.dmg` | ~120 MB |
| macOS | Apple Silicon (ARM64) | `udr-desktop-darwin-arm64-{version}.dmg` | ~110 MB |
| Linux | x86_64 | `udr-desktop-linux-x64-{version}.AppImage` | ~110 MB |
| Linux | ARM64 | `udr-desktop-linux-arm64-{version}.AppImage` | ~105 MB |

Available on the [GitHub Releases](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases) page.

---

## Launch

### Windows

```cmd
udr-desktop.exe
# Or double-click in File Explorer
```

Windows Defender may flag the unsigned binary. Click "More info" → "Run anyway".

### macOS

```bash
# Drag to Applications folder from the mounted .dmg
open /Applications/udr-desktop.app

# If Gatekeeper blocks it:
xattr -d com.apple.quarantine /Applications/udr-desktop.app
```

### Linux

```bash
chmod +x udr-desktop-*.AppImage
./udr-desktop-*.AppImage
```

### All Platforms

The app starts an embedded backend server on `http://127.0.0.1:8000` and opens the GUI in the default browser.

---

## Interface

The GUI is organized into 17 tabs across 4 sections.

### Overview

| Tab | Function |
|---|---|
| **Dashboard** | Summary cards: system info, recent scans, lock file status |

### Packages

| Tab | Function |
|---|---|
| **Resolve** | Enter package specs, run resolution, view results table |
| **Search** | Search packages across ecosystems, click to see details |
| **Details** | Package description, latest version, license, home page |
| **Versions** | Full version history with Python/OS requirements |
| **Dependencies** | Dependency tree for a specific package version |
| **Compatibility** | Known compatibility information and conflict data |

### System

| Tab | Function |
|---|---|
| **System Info** | OS, CPU, GPU, CUDA, memory, runtimes table |

### Project

| Tab | Function |
|---|---|
| **Scan** | Scan a GitHub repo or local directory (full lock pipeline) |
| **Graph** | Visual dependency tree for one or more packages |
| **SBOM** | Generate SPDX 2.3 or CycloneDX 1.5 Bill of Materials |
| **Lock** | Run full resolution pipeline, view/write lock file |
| **Check** | CVE, license, deprecated, and policy checks on lock data |
| **Verify** | Validate that all pinned versions still exist in registries |
| **Install** | Generate and execute native package manager install commands |
| **Restore** | Generate commands for all packages (direct + transitive) |
| **Update** | Re-resolve a specific package or auto-fix CVEs |

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+1` | Dashboard |
| `Ctrl+2` | Resolve |
| `Ctrl+3` | Search |
| `Ctrl+4` | Details |
| `Ctrl+5` | Lock |
| `Ctrl+6` | Scan |
| `Ctrl+R` | Re-run current operation |
| `Ctrl+Shift+R` | Clear cache and re-run |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| App won't start | Port 8000 in use | Kill existing `udr` process or change port via `UDR_DESKTOP_PORT` env var |
| "Backend not responding" | PyInstaller bundle damaged | Re-download from Releases |
| GPU not detected | Missing nvidia-ml-py in bundle | Check System Info tab — if GPU section missing, install `nvidia-smi` |
| Slow resolution on large projects | Default settings | Use `--timeout 300` or reduce `BFS_BATCH_SIZE` |
| "No manifests found" | Wrong directory | Use the Scan tab with explicit path |
| macOS "damaged" warning | Extended attributes | Run `xattr -c /Applications/udr-desktop.app` |
| Linux AppImage not launching | FUSE missing | Install `fuse` or use `--appimage-extract && ./squashfs-root/AppRun` |
