# backend/api/routes/scan.py
import asyncio
import io
import json
import logging
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from backend.manifest_detector import ManifestDetector
from backend.core.data_aggregator import DataAggregator
from backend.core.conflict_resolver import ConflictResolver
from backend.core.system_scanner import SystemScanner
from backend.core.export_generator import ExportGenerator
from backend.cli import (
    _aggregator_to_resolver_input,
    _resolve_transitive,
    _apply_cuda_variants,
    _parse_package_spec,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class GitHubScanRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = "main"


class LocalScanRequest(BaseModel):
    directory_path: str


def _download_github_repo(url: str, branch: str) -> Path:
    """Download a GitHub repo as zipball and extract to temp dir."""
    import re
    import requests

    match = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")
    owner, repo = match.group(1), match.group(2).rstrip(".git")
    api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
    resp = requests.get(api_url, timeout=60, stream=True)
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"GitHub API returned {resp.status_code}")
    tmp = Path(tempfile.mkdtemp(prefix="udr_scan_"))
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    z.extractall(path=str(tmp))
    # The zip contains a top-level directory like owner-repo-commitSHA
    contents = list(tmp.iterdir())
    if contents and contents[0].is_dir():
        return contents[0]
    return tmp


async def _run_resolution_pipeline(project_dir: Path) -> dict:
    """Run manifest detection + resolution on a project directory."""
    detector = ManifestDetector(str(project_dir))
    aggregator = DataAggregator()
    resolver = ConflictResolver()
    scanner = SystemScanner()
    exporter = ExportGenerator()

    manifests = detector.detect()
    if not manifests:
        return {"status": "no_manifests", "manifests": [], "packages": [], "resolution": None}

    packages = detector.normalize(detector.parse_all(manifests))
    if not packages:
        return {"status": "no_packages", "manifests": manifests, "packages": [], "resolution": None}

    seen = set()
    resolver_inputs = []
    package_details = {}

    for pkg in packages:
        key = (pkg["name"], pkg["ecosystem"])
        if key in seen:
            continue
        seen.add(key)
        try:
            data = await aggregator.get_package_info(
                pkg["name"], ecosystem=pkg["ecosystem"],
                include_dependencies=True, include_versions=True,
            )
            if data:
                package_details[pkg["name"]] = data
                rinput = _aggregator_to_resolver_input(data, pkg["ecosystem"])
                resolver_inputs.append(rinput)
        except Exception as e:
            logger.warning(f"Failed to fetch {pkg['name']}: {e}")

    system_info = await scanner.scan_all()

    try:
        resolved = await _resolve_transitive(aggregator, resolver, resolver_inputs, system_info)
    except Exception:
        resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)

    resolved = _apply_cuda_variants(resolved, package_details, system_info)

    resolved_pkgs = resolved.get("resolved_packages", {})

    return {
        "status": "success",
        "manifests": [{"filename": m["filename"], "ecosystem": m["ecosystem"]} for m in manifests],
        "packages": [
            {
                "name": p["name"],
                "ecosystem": p["ecosystem"],
                "constraint": p["constraint"],
                "resolved_version": resolved_pkgs.get(p["name"], {}).get("version"),
                "cuda_variant": resolved_pkgs.get(p["name"], {}).get("cuda_variant", False),
                "cuda_version": resolved_pkgs.get(p["name"], {}).get("cuda_version"),
            }
            for p in packages
        ],
        "resolution": resolved,
        "system": {
            "os": f"{system_info['platform']['system']} {system_info['platform']['release']}",
            "python": system_info["runtime_versions"]["python"]["version"],
            "cpu": system_info["cpu"]["brand"],
            "gpu": system_info["gpu"]["devices"][0]["name"] if system_info["gpu"]["available"] else None,
            "cuda": system_info["gpu"].get("cuda") if system_info["gpu"]["available"] else None,
        },
    }


@router.post("/scan/github")
async def scan_github(req: GitHubScanRequest):
    """Clone a GitHub repo, detect manifests, resolve all dependencies."""
    loop = asyncio.get_event_loop()
    project_dir = await loop.run_in_executor(None, _download_github_repo, req.repo_url, req.branch)
    try:
        result = await _run_resolution_pipeline(project_dir)
        result["source"] = "github"
        result["repo_url"] = req.repo_url
        return result
    finally:
        import shutil
        shutil.rmtree(project_dir.parent, ignore_errors=True)


@router.post("/scan/upload")
async def scan_upload(file: UploadFile = File(...)):
    """Upload a project archive (zip), detect manifests, resolve all dependencies."""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are supported")
    tmp = Path(tempfile.mkdtemp(prefix="udr_scan_"))
    try:
        content = await file.read()
        z = zipfile.ZipFile(io.BytesIO(content))
        z.extractall(path=str(tmp))
        # Try to find project root (handle single top-level dir)
        project_dir = tmp
        contents = sorted(tmp.iterdir())
        if len(contents) == 1 and contents[0].is_dir():
            project_dir = contents[0]
        result = await _run_resolution_pipeline(project_dir)
        result["source"] = "upload"
        result["filename"] = file.filename
        return result
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


@router.post("/scan/local")
async def scan_local(req: LocalScanRequest):
    """Scan a local directory path (only works when backend runs on same machine)."""
    project_dir = Path(req.directory_path).resolve()
    if not project_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"Directory not found: {req.directory_path}")
    result = await _run_resolution_pipeline(project_dir)
    result["source"] = "local"
    result["directory_path"] = str(project_dir)
    return result
