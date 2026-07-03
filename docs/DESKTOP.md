# Desktop App

The Universal Dependency Resolver ships as a standalone Electron desktop application — no Python, Node.js, or any runtime required.

## Getting Started

### Download

Download the latest release from [GitHub Releases](https://github.com/code-with-zeeshan/universal-dependency-resolver/releases):

| Platform | File |
|---|---|
| Windows 10+ | `UDR-Setup-x.y.z.exe` (NSIS installer) |
| macOS 11+ (Intel) | `UDR-x.y.z-x64.dmg` |
| macOS 11+ (Apple Silicon) | `UDR-x.y.z-arm64.dmg` |
| Linux (x86_64) | `UDR-x.y.z-x86_64.AppImage` |
| Linux (ARM64) | `UDR-x.y.z-arm64.AppImage` |

### Launch

- **Windows**: Run the installer, then launch from Start Menu or desktop shortcut
- **macOS**: Mount the `.dmg`, drag to Applications, then right-click → Open (first launch only, due to unsigned binary)
- **Linux**: `chmod +x UDR-*.AppImage && ./UDR-*.AppImage` (requires FUSE; if unavailable, use `--appimage-extract`)

The app starts the backend automatically on a free port (`127.0.0.1:8199` by default). The status indicator in the top-right corner turns **green** when ready.

---

## Interface Overview

The UI is a single-page application with a collapsible icon sidebar on the left. Hover over the sidebar to reveal section labels.

### Sidebar Sections

| Section | Tabs |
|---|---|
| **Overview** | Dashboard |
| **Packages** | Resolve, Search, Details, Versions, Dependencies, Compatibility |
| **System** | System |
| **Project** | Scan, Graph, Verify Lock, Install, Restore, Update |

---

## Tab Reference

### Dashboard
Shows API status, tool version, running mode, and ecosystem count. Quick-action buttons jump to the most common tasks.

### Resolve
Enter one or more package names (space-separated), select a default ecosystem, and click **Resolve**. The resolution result shows compatible versions, CUDA variants, and per-package details.

- Use `name@ecosystem` to override the ecosystem per package (e.g. `torch@pypi express@npm`)
- After resolving, click **Export** to generate output in any supported format (requirements.txt, Dockerfile, etc.)
- Keyboard shortcut: `Ctrl+K` to jump to this tab

### Search
Search for packages across all ecosystems. Results show package name, ecosystem, description, and latest version.

### Details
View full metadata for a single package — description, homepage, license, author, and repository URL.

### Versions
List all available versions for a package, with release dates.

### Dependencies
View direct and transitive dependencies for any package, grouped by ecosystem.

### Compatibility
Check system compatibility requirements for a package — supported OS, Python version, CUDA version, and architecture.

### System
Displays comprehensive system information: OS, CPU, memory, GPU, CUDA version, Python version, Node.js version, GCC version, Java version.

- Click **Refresh** to re-scan system info
- Click **Check Compatibility** to run a system compatibility check against common package requirements

### Scan
Detect dependency manifests (requirements.txt, package.json, Cargo.toml, pyproject.toml, go.mod, environment.yml, Gemfile, pom.xml, and more) in a project directory, GitHub repository, or uploaded ZIP file. After scanning, the tool resolves all detected packages and displays the results.

**Three input modes:**
- **Local Path** — browse or type a directory path on this machine
- **GitHub URL** — paste a GitHub repository URL (no cloning needed; downloads zipball)
- **Upload ZIP** — upload a `.zip` file

After a successful scan, click **Generate Lock File** to download a `udr.lock` with the resolved packages and system snapshot.

### Graph
Display a dependency tree for one or more packages. Shows direct and transitive dependencies in a hierarchical tree view.

### Verify Lock
Paste a `udr.lock` file (or load from disk) to verify that every pinned version still exists in its respective package registry.

### Install
Paste a `udr.lock` file (or load from disk) to generate native install commands for all **direct** dependencies, grouped by ecosystem. Each command includes a **Copy** button.

Commands run sequentially by ecosystem when executed:
- PyPI → `pip install`
- npm → `npm install`
- Crates → `cargo add`
- Go Modules → `go get`
- Conda → `conda install`
- RubyGems → `gem install`
- Packagist → `composer require`
- Pub/Dart → `dart pub add`
- NuGet → `dotnet add package`
- CocoaPods → `pod install`
- Maven → `mvn dependency:copy-dependencies`

### Restore
Same as Install but generates commands for **all** packages in the lock file (direct + transitive). Useful for full project restoration after cloning.

### Update
Re-resolve a single package in a lock file. Paste the lock file JSON, enter the package name, and click **Update**. Returns the updated lock data with the new resolved version.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+K` | Jump to Resolve tab |
| `Ctrl+R` | Reload frontend |
| `Ctrl+Shift+R` | Restart backend |
| `Ctrl+Shift+I` | Toggle DevTools |

---

## Menu

- **File → Reload Frontend** (`Cmd/Ctrl+R`)
- **File → Restart Backend** (`Cmd/Ctrl+Shift+R`)
- **File → Quit** (`Cmd/Ctrl+Q`)
- **Help → About UDR**
- **Help → Toggle DevTools** (`Ctrl+Shift+I`)

---

## Troubleshooting

| Symptom | Cause & Fix |
|---|---|
| Status indicator stays **yellow** | Backend starting up — wait a few seconds. If it stays yellow, restart the app. |
| Status indicator turns **red** | Backend failed to start. Click **Restart Backend** from the menu. If that fails, try running `udr serve` from the terminal to see the error. |
| **Blank white window** | Frontend loaded but backend not responding. Wait for the status to turn green, or restart. |
| **Windows antivirus warning** | PyInstaller binaries are sometimes flagged by Windows Defender. Add an exclusion for the installation directory. |
| **macOS "cannot be opened"** | The app is not signed. Right-click → Open, or go to System Settings → Privacy & Security → "Open Anyway". |
| **Linux AppImage not running** | Install FUSE: `sudo apt install fuse` (Ubuntu/Debian) or equivalent. Alternatively, extract: `./UDR-*.AppImage --appimage-extract && ./squashfs-root/AppRun`. |
| **"Backend binary not found"** | The bundled binary failed to extract. The app falls back to system Python — ensure `ud-resolver` is installed: `pip install ud-resolver`. |
