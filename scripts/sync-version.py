#!/usr/bin/env python3
"""Sync version from pyproject.toml to desktop/package.json."""

import json
import re
from pathlib import Path


def main() -> None:
    """Sync version from pyproject.toml to desktop/package.json."""
    root = Path(__file__).resolve().parent.parent
    pyproject = root / "pyproject.toml"
    desktop_pkg = root / "desktop" / "package.json"

    text = pyproject.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise SystemExit("version not found in pyproject.toml")
    version = m.group(1)

    pkg = json.loads(desktop_pkg.read_text())
    old_version = pkg.get("version")
    if old_version != version:
        pkg["version"] = version
        desktop_pkg.write_text(json.dumps(pkg, indent=2) + "\n")
        print(f"desktop/package.json: {old_version} -> {version}")
    else:
        print(f"desktop/package.json: already at {version}")


if __name__ == "__main__":
    main()
