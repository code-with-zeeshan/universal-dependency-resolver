"""GitHub repository download — shared by CLI and API."""

import io
import tempfile
import zipfile
from pathlib import Path


def _download_github_repo(url: str, branch: str) -> Path:
    import re
    import urllib.request

    match = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
    if not match:
        raise ValueError(f"Invalid GitHub URL: {url}")
    owner, repo = match.group(1), match.group(2).rstrip(".git")
    api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
    req = urllib.request.Request(api_url, headers={"User-Agent": "UDR/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status != 200:
            raise ValueError(f"GitHub API returned {resp.status} for {url}")
        data = resp.read()
    tmp = Path(tempfile.mkdtemp(prefix="udr_scan_"))
    z = zipfile.ZipFile(io.BytesIO(data))
    z.extractall(path=str(tmp))
    contents = list(tmp.iterdir())
    if contents and contents[0].is_dir():
        return contents[0]
    return tmp
