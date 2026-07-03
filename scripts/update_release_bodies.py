#!/usr/bin/env python3
"""Update GitHub release bodies from CHANGELOG.md using `gh` CLI.

Requires `gh` to be installed and authenticated.

Usage:
    python scripts/update_release_bodies.py
    python scripts/update_release_bodies.py --repo owner/repo
"""

import argparse
import re
import subprocess
import sys


def get_releases(repo: str) -> list[dict]:
    result = subprocess.run(
        ["gh", "release", "list", "--repo", repo, "--json", "tagName,id,body", "--limit", "100"],
        capture_output=True, text=True, check=True,
    )
    import json
    return json.loads(result.stdout)


def get_changelog_section(text: str, target_ver: str) -> str | None:
    sections = re.split(r"(?=^## \[)", text, flags=re.MULTILINE)
    for s in sections[1:]:
        m = re.match(r"^## \[(\d+\.\d+\.\d+)\]", s)
        if m and m.group(1) == target_ver:
            return s.strip()
    return None


def update_release(repo: str, tag: str, body: str) -> None:
    subprocess.run(
        ["gh", "release", "edit", tag, "--repo", repo, "--notes", body],
        capture_output=True, check=True,
    )


def main():
    parser = argparse.ArgumentParser(description="Update release bodies from CHANGELOG.md")
    parser.add_argument("--repo", default=None, help="GitHub repo (owner/name)")
    args = parser.parse_args()

    if args.repo:
        repo = args.repo
    else:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner"],
            capture_output=True, text=True, check=True,
        )
        import json
        repo = json.loads(result.stdout)["nameWithOwner"]

    try:
        with open("CHANGELOG.md") as f:
            changelog = f.read()
    except FileNotFoundError:
        print("CHANGELOG.md not found in current directory", file=sys.stderr)
        sys.exit(1)

    releases = get_releases(repo)
    if not releases:
        print("No releases found.", file=sys.stderr)
        sys.exit(1)

    updated = 0
    for rel in releases:
        tag = rel["tagName"]
        ver = tag.lstrip("v")
        body = get_changelog_section(changelog, ver)
        if not body:
            print(f"  No changelog entry for {tag}")
            continue
        current_body = (rel.get("body") or "").strip()
        if body == current_body:
            print(f"  Already up to date: {tag}")
            continue
        update_release(repo, tag, body)
        print(f"  Updated {tag}")
        updated += 1

    print(f"\nDone. {updated} release(s) updated.")


if __name__ == "__main__":
    main()
