#!/usr/bin/env python3
"""Extract changelog section for a given version from CHANGELOG.md.

Usage: python3 scripts/extract_changelog.py <version>
  version: e.g., 1.2.4 (without v prefix)
  
Outputs all changelog sections from the given version onwards (newest to oldest).
"""
import re, sys

if len(sys.argv) < 2:
    print("Usage: extract_changelog.py <version>", file=sys.stderr)
    sys.exit(1)

target = sys.argv[1].lstrip("v")

with open("CHANGELOG.md") as f:
    text = f.read()

sections = re.split(r"(?=^## \[)", text, flags=re.MULTILINE)
header = sections[0]

match_sections = []
found = False
for s in sections[1:]:
    m = re.match(r"^## \[(\d+\.\d+\.\d+)\]", s)
    if m:
        if not found and m.group(1) == target:
            found = True
        if found:
            match_sections.append(s)

if match_sections:
    sys.stdout.write("".join(match_sections).strip())
else:
    print(f"No changelog section found for version {target}", file=sys.stderr)
    sys.exit(1)
