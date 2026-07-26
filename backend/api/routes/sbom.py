"""REST endpoints for SBOM generation."""

import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.api.dependencies import limiter
from backend.core.sbom import _build_cyclonedx, _build_spdx

logger = logging.getLogger(__name__)
router = APIRouter()


class SBOMRequest(BaseModel):
    """Request model for SBOM generation from lock data."""

    lock_data: dict[str, Any]
    format: str = "spdx"


@router.post("/sbom")
@limiter.limit("10/minute")
async def generate_sbom(
    request: Request,
    body: SBOMRequest,
) -> dict[str, Any]:
    """Generate SPDX 2.3 or CycloneDX 1.5 SBOM from lock data."""
    fmt = body.format.lower()
    if fmt == "spdx":
        sbom = _build_spdx(body.lock_data)
    elif fmt in ("cyclonedx", "cdx"):
        sbom = _build_cyclonedx(body.lock_data)
    else:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400, detail=f"Unsupported format: {fmt}. Use 'spdx' or 'cyclonedx'."
        )
    return {"status": "success", "format": fmt, "sbom": sbom}
