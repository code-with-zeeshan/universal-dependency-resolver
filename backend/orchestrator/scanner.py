"""GitHub repository download — shared by CLI and API."""

import io
import tempfile
import zipfile
from pathlib import Path

import aiohttp


async def _download_github_repo(url: str, branch: str) -> Path:
    import re

    match = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
    if not match:
        raise ValueError(f"Invalid GitHub URL: {url}")
    owner, repo = match.group(1), match.group(2).rstrip(".git")
    api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
    headers = {"User-Agent": "UDR/1.0"}
    async with aiohttp.ClientSession() as session:
        async with session.get(
            api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            if resp.status != 200:
                raise ValueError(f"GitHub API returned {resp.status} for {url}")
            data = await resp.read()
    tmp = Path(tempfile.mkdtemp(prefix="udr_scan_"))
    z = zipfile.ZipFile(io.BytesIO(data))
    _safe_extractall(z, tmp)
    contents = list(tmp.iterdir())
    if contents and contents[0].is_dir():
        return contents[0]
    return tmp


def _safe_extractall(z: zipfile.ZipFile, target_dir: Path) -> None:
    target = target_dir.resolve()
    for entry in z.infolist():
        dest = target / entry.filename
        try:
            resolved = dest.resolve()
        except (ValueError, RuntimeError):
            raise ValueError(f"Path traversal detected (unresolvable): {entry.filename}")
        if not str(resolved).startswith(str(target)):
            raise ValueError(f"Path traversal detected: {entry.filename}")
    z.extractall(path=str(target))
