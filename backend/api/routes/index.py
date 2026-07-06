"""API routes for offline SQLite index management.

Mirrors ``udr index {status,pull,build}``.
"""

import logging
import shutil
import tempfile
from pathlib import Path

import httpx
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
    url = req.url
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

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
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Download failed — network error: {e}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
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
