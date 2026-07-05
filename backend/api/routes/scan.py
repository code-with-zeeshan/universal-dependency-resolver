"""Module docstring."""

# backend/api/routes/scan.py
import asyncio
import io
import logging
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from backend.api.auth import get_current_user
from backend.core.conflict_resolver import ConflictResolver
from backend.core.data_aggregator import DataAggregator
from backend.core.export_generator import ExportGenerator
from backend.core.system_scanner import SystemScanner
from backend.manifest_detector import ManifestDetector
from backend.orchestrator import (
    _aggregator_to_resolver_input,
    _apply_cuda_variants,
    _resolve_transitive,
)

SOLVER_API_TIMEOUT = int(os.environ.get("SOLVER_API_TIMEOUT", "60"))

logger = logging.getLogger(__name__)
router = APIRouter()


class GitHubScanRequest(BaseModel):
    """Git Hub Scan Request functionality."""

    repo_url: str
    branch: str | None = "main"


class LocalScanRequest(BaseModel):
    """Local Scan Request functionality."""

    directory_path: str


from backend.orchestrator import _download_github_repo


async def _run_resolution_pipeline(project_dir: Path, export_format: str | None = None) -> dict:
    """Run manifest detection + resolution on a project directory."""
    detector = ManifestDetector(str(project_dir))
    aggregator = DataAggregator()
    resolver = ConflictResolver()
    scanner = SystemScanner()
    exporter = ExportGenerator() if export_format else None

    manifests = detector.detect()
    if not manifests:
        return {
            "status": "no_manifests",
            "manifests": [],
            "packages": [],
            "resolution": None,
        }

    packages = detector.normalize(detector.parse_all(manifests))
    if not packages:
        return {
            "status": "no_packages",
            "manifests": manifests,
            "packages": [],
            "resolution": None,
        }

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
                pkg["name"],
                ecosystem=pkg["ecosystem"],
                include_dependencies=True,
                include_versions=True,
            )
            if data:
                package_details[pkg["name"]] = data
                rinput = _aggregator_to_resolver_input(data, pkg["ecosystem"])
                resolver_inputs.append(rinput)
        except Exception as e:
            logger.warning(f"Failed to fetch {pkg['name']}: {e}")

    system_info = await scanner.scan_all()

    try:
        resolved = await asyncio.wait_for(
            _resolve_transitive(aggregator, resolver, resolver_inputs, system_info),
            timeout=SOLVER_API_TIMEOUT,
        )
    except (TimeoutError, Exception):
        resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)

    resolved = _apply_cuda_variants(resolved, package_details, system_info)

    resolved_pkgs = resolved.get("resolved_packages", {})

    export_content = None
    if export_format and exporter:
        try:
            export_content = exporter.generate(
                {
                    p["name"]: {
                        "version": resolved_pkgs.get(p["name"], {}).get("version"),
                        "ecosystem": p["ecosystem"],
                    }
                    for p in packages
                },
                format=export_format,
                system_info=system_info,
            )
        except Exception as e:
            logger.warning("Export failed: %s", e)

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
            "os": f"{system_info.get('platform', {}).get('system', 'Unknown')} {system_info.get('platform', {}).get('release', 'Unknown')}",
            "python": system_info.get("runtime_versions", {})
            .get("python", {})
            .get("version", "Unknown"),
            "cpu": system_info.get("cpu", {}).get("brand", "Unknown"),
            "gpu": system_info.get("gpu", {}).get("devices", [{}])[0].get("name", "Unknown")
            if system_info.get("gpu", {}).get("available", False)
            else None,
            "cuda": system_info.get("gpu", {}).get("cuda")
            if system_info.get("gpu", {}).get("available", False)
            else None,
        },
        "export": export_content,
    }


@router.post("/scan/github")
async def scan_github(
    req: GitHubScanRequest,
    export: str | None = Query(
        None, description="Export format (e.g. requirements.txt, Dockerfile)"
    ),
    current_user=Depends(get_current_user),
):
    """Clone a GitHub repo, detect manifests, resolve all dependencies."""
    try:
        project_dir = await _download_github_repo(req.repo_url, req.branch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        result = await _run_resolution_pipeline(project_dir, export_format=export)
        result["source"] = "github"
        result["repo_url"] = req.repo_url
        return result
    finally:
        import shutil

        shutil.rmtree(project_dir.parent, ignore_errors=True)


@router.post("/scan/upload")
async def scan_upload(
    file: UploadFile = File(...),
    export: str | None = Query(
        None, description="Export format (e.g. requirements.txt, Dockerfile)"
    ),
    current_user=Depends(get_current_user),
):
    """Upload a project archive (zip), detect manifests, resolve all dependencies."""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are supported")
    tmp = Path(tempfile.mkdtemp(prefix="udr_scan_"))
    try:
        content = await file.read()
        z = zipfile.ZipFile(io.BytesIO(content))
        for entry in z.infolist():
            dest = (tmp / entry.filename).resolve()
            if not str(dest).startswith(str(tmp.resolve())):
                raise HTTPException(status_code=400, detail="Illegal path in zip archive")
        z.extractall(path=str(tmp))
        # Try to find project root (handle single top-level dir)
        project_dir = tmp
        contents = sorted(tmp.iterdir())
        if len(contents) == 1 and contents[0].is_dir():
            project_dir = contents[0]
        result = await _run_resolution_pipeline(project_dir, export_format=export)
        result["source"] = "upload"
        result["filename"] = file.filename
        return result
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


@router.post("/scan/local")
async def scan_local(
    req: LocalScanRequest,
    export: str | None = Query(
        None, description="Export format (e.g. requirements.txt, Dockerfile)"
    ),
    current_user=Depends(get_current_user),
):
    """Scan a local directory path (only works when backend runs on same machine)."""
    project_dir = Path(req.directory_path).resolve()
    if not project_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"Directory not found: {req.directory_path}")
    result = await _run_resolution_pipeline(project_dir, export_format=export)
    result["source"] = "local"
    result["directory_path"] = str(project_dir)
    return result
