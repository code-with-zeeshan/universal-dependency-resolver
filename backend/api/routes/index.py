"""API routes for offline SQLite index management.

Mirrors ``udr index {status,pull,build}``.
"""

import logging
import shutil
import socket
import tempfile
from ipaddress import ip_address, ip_network
from pathlib import Path
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.api.auth import get_current_user
from backend.core.offline_index import (
    INDEX_DIR,
    _db_path,
    create_or_update_index,
    index_status,
    list_indexes,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_PRIVATE_NETWORKS = [
    ip_network("127.0.0.0/8"),
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("169.254.0.0/16"),
    ip_network("::1/128"),
    ip_network("fc00::/7"),
    ip_network("fe80::/10"),
]


def _validate_external_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL must use http:// or https://")
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL must have a valid hostname")
    hostname = parsed.hostname
    try:
        addr = socket.getaddrinfo(hostname, 80, family=socket.AF_INET)[0][4][0]
    except (socket.gaierror, OSError):
        raise HTTPException(status_code=400, detail="Could not resolve hostname")
    ip = ip_address(addr)
    for net in _PRIVATE_NETWORKS:
        if ip in net:
            raise HTTPException(status_code=400, detail="Private/internal URLs are not allowed")
    return url


class IndexPullRequest(BaseModel):
    """Pull a pre-built index from a remote URL."""

    url: str
    ecosystem: str | None = None


class IndexBuildRequest(BaseModel):
    """Build an index from package data."""

    ecosystem: str
    packages: list[dict]


@router.get("/status")
async def get_index_status(
    ecosystem: str | None = Query(None, description="Filter to one ecosystem"),
    current_user=Depends(get_current_user),
):
    """Show local offline index status. Mirrors ``udr index status --json``."""
    if ecosystem:
        st = index_status(ecosystem)
        if st is None:
            raise HTTPException(
                status_code=404,
                detail=f"No index found for ecosystem '{ecosystem}'",
            )
        return {"status": "success", "indexes": [st]}
    results = []
    for eco in list_indexes():
        st = index_status(eco)
        if st:
            results.append(st)
    return {"status": "success", "indexes": results}


@router.post("/pull")
async def pull_index(
    req: IndexPullRequest,
    current_user=Depends(get_current_user),
):
    """Download a pre-built SQLite index from a remote URL.

    Mirrors ``udr index pull <url>``.
    """
    url = _validate_external_url(req.url)

    tmp = Path(tempfile.mkdtemp(prefix="udr_index_pull_"))
    try:
        dest = tmp / "index.db"
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)

        eco = req.ecosystem
        if not eco:
            stem = Path(url).stem
            if stem.endswith(".db"):
                stem = stem[:-3]
            eco = stem.replace("_", "-")

        if not eco:
            raise HTTPException(
                status_code=400,
                detail="Could not determine ecosystem; specify ecosystem",
            )

        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        target = _db_path(eco)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), str(target))

        st = index_status(eco)
        return {"status": "success", "ecosystem": eco, "index": st}
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Download failed: {e.response.status_code} {e.response.text[:200]}",
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Download failed — network error",
        )
    except Exception:
        logger.exception("Unexpected error downloading index")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@router.post("/build")
async def build_index(
    req: IndexBuildRequest,
    current_user=Depends(get_current_user),
):
    """Build an offline index from package data.

    Mirrors ``udr index build --ecosystem <eco> --packages <names>``.
    """
    ecosystem = req.ecosystem
    packages = req.packages
    if not packages:
        raise HTTPException(status_code=400, detail="No packages provided")
    try:
        count = create_or_update_index(ecosystem, packages)
        st = index_status(ecosystem)
        return {
            "status": "success",
            "ecosystem": ecosystem,
            "packages_indexed": count,
            "index": st,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-all")
async def sync_all_indexes(
    current_user=Depends(get_current_user),
):
    """Sync local indexes for all ecosystems from remote registries.

    Mirrors ``udr index sync --all``.
    """
    from backend.core.data_aggregator import DataAggregator
    from backend.settings import ECOSYSTEMS as _ECOSYSTEMS

    ecosystems = [e for e in _ECOSYSTEMS if e not in ("docs", "custom_db")]

    aggregator = DataAggregator()
    try:
        results: list[dict] = []
        for eco in ecosystems:
            try:
                n = await aggregator.sync_local_index(eco)
                results.append(
                    {
                        "ecosystem": eco,
                        "status": "ok",
                        "packages_synced": n or 0,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "ecosystem": eco,
                        "status": "error",
                        "error": str(e),
                    }
                )
        return {
            "status": "success",
            "results": results,
            "total": sum(r.get("packages_synced", 0) for r in results),
        }
    finally:
        await aggregator.close()
