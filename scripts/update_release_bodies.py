#!/usr/bin/env python3
"""Update GitHub release bodies from CHANGELOG.md for all existing releases."""
import re, os, sys, json, urllib.request

TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    print("Set GH_TOKEN or GITHUB_TOKEN env var")
    sys.exit(1)

REPO = "code-with-zeeshan/universal-dependency-resolver"

with open("CHANGELOG.md") as f:
    text = f.read()

sections = re.split(r"(?=^## \[)", text, flags=re.MULTILINE)

headers = {
    "Accept": "application/vnd.github.v3+json",
    "Authorization": f"Bearer {TOKEN}",
}

# Fetch all releases
req = urllib.request.Request(
    f"https://api.github.com/repos/{REPO}/releases", headers=headers
)
releases = json.loads(urllib.request.urlopen(req).read())

for r in releases:
    tag = r["tag_name"]
    ver = tag.lstrip("v")
    body_sections = []
    found = False
    for s in sections[1:]:
        m = re.match(r"^## \[(\d+\.\d+\.\d+)\]", s)
        if m:
            if not found and m.group(1) == ver:
                found = True
            if found:
                body_sections.append(s)
    if body_sections:
        body = "".join(body_sections).strip()
        if body != r.get("body", "").strip():
            data = json.dumps({"body": body}).encode()
            req2 = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/releases/{r['id']}",
                data=data,
                headers={**headers, "Content-Type": "application/json"},
                method="PATCH",
            )
            urllib.request.urlopen(req2)
            print(f"Updated {tag}")
        else:
            print(f"Already up to date: {tag}")
    else:
        print(f"No changelog for {tag}")
