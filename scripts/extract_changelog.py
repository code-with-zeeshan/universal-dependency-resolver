#!/usr/bin/env python3
"""Extract the changelog section for a given version from CHANGELOG.md.

Usage: python3 scripts/extract_changelog.py <version>
  version: e.g., 1.3.2 (without v prefix)

Outputs only the changelog section for that specific version.
"""
import re
import sys

if len(sys.argv) < 2:
    print("Usage: extract_changelog.py <version>", file=sys.stderr)
    sys.exit(1)

target = sys.argv[1].lstrip("v")

with open("CHANGELOG.md") as f:
    text = f.read()

sections = re.split(r"(?=^## \[)", text, flags=re.MULTILINE)
header = sections[0]

for s in sections[1:]:
    m = re.match(r"^## \[(\d+\.\d+\.\d+)\]", s)
    if m and m.group(1) == target:
        sys.stdout.write(s.strip())
        sys.exit(0)

print(f"No changelog section found for version {target}", file=sys.stderr)
sys.exit(1)
