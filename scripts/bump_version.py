#!/usr/bin/env python3
"""Bump version in pyproject.toml, sync to desktop/package.json, commit, and tag.

Usage:
    python scripts/bump_version.py 1.2.5
    python scripts/bump_version.py 1.2.5 --push   # also pushes commit + tag
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def bump_pyproject(version: str) -> str:
    path = ROOT / "pyproject.toml"
    old = path.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', old, re.MULTILINE)
    if not m:
        raise SystemExit("version not found in pyproject.toml")
    old_ver = m.group(1)
    new = old.replace(f'version = "{old_ver}"', f'version = "{version}"', 1)
    path.write_text(new)
    print(f"  pyproject.toml: {old_ver} -> {version}")
    return old_ver


def main():
    p = argparse.ArgumentParser(description="Bump version across the repo")
    p.add_argument("version", help="New version (e.g. 1.2.5)")
    p.add_argument("--push", action="store_true", help="Also push commit and tag")
    args = p.parse_args()

    ver = args.version.lstrip("v")
    old_ver = bump_pyproject(ver)

    subprocess.run([sys.executable, "scripts/sync-version.py"], cwd=ROOT, check=True)

    subprocess.run(
        ["git", "add", "-A"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", f"Bump version {old_ver} -> {ver}"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        ["git", "tag", f"v{ver}"],
        cwd=ROOT,
        check=True,
    )

    if args.push:
        subprocess.run(["git", "push"], cwd=ROOT, check=True)
        subprocess.run(["git", "push", "origin", f"v{ver}"], cwd=ROOT, check=True)

    print(f"\nDone. Tag v{ver} created at commit above.")
    if not args.push:
        print("Run: git push --follow-tags  (or re-run with --push)")


if __name__ == "__main__":
    main()
