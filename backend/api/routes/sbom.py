"""REST endpoints for SBOM generation."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.api.dependencies import limiter
from backend.core.utils import make_purl

logger = logging.getLogger(__name__)
router = APIRouter()


class SBOMRequest(BaseModel):
    lock_data: dict[str, Any]
    format: str = "spdx"


def _build_spdx(lock_data: dict) -> dict[str, Any]:
    packages_raw = lock_data.get("packages", {})
    spdx_packages = []
    spdx_relationships = []
    for pkg_name, pkg_info in packages_raw.items():
        ver = pkg_info.get("resolved_version", "")
        lic = pkg_info.get("license") or "NOASSERTION"
        integrity = pkg_info.get("integrity")
        pkg_entry = {
            "SPDXID": f"SPDXRef-{pkg_name}",
            "name": pkg_name,
            "versionInfo": ver,
            "supplier": "NOASSERTION",
            "downloadLocation": "NOASSERTION",
            "licenseConcluded": lic,
            "licenseDeclared": lic,
            "copyrightText": "NOASSERTION",
        }
        if integrity and isinstance(integrity, dict):
            algo = integrity.get("algorithm", "SHA256")
            val = integrity.get("value", "")
            if val:
                pkg_entry["checksums"] = [{"algorithm": algo, "value": val}]
        spdx_packages.append(pkg_entry)
        for dep_name in pkg_info.get("depends_on", {}):
            spdx_relationships.append(
                {
                    "spdxElementId": f"SPDXRef-{pkg_name}",
                    "relatedSpdxElement": f"SPDXRef-{dep_name}",
                    "relationshipType": "DEPENDS_ON",
                }
            )
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "udr-sbom",
        "creationInfo": {
            "created": datetime.now().isoformat(),
            "creators": ["Tool: universal-dependency-resolver"],
        },
        "packages": spdx_packages,
        "relationships": spdx_relationships,
    }


def _build_cyclonedx(lock_data: dict) -> dict[str, Any]:
    packages_raw = lock_data.get("packages", {})
    components = []
    dependencies = []
    purl_cache = {}
    for pkg_name, pkg_info in packages_raw.items():
        eco = pkg_info.get("ecosystem", "pypi")
        ver = pkg_info.get("resolved_version", "")
        lic = pkg_info.get("license")
        purl_str = make_purl(pkg_name, ver, eco)
        purl_cache[pkg_name] = purl_str
        comp = {"type": "library", "name": pkg_name, "version": ver, "purl": purl_str}
        if lic:
            comp["licenses"] = [{"license": {"id": lic}}]
        components.append(comp)
    for pkg_name, pkg_info in packages_raw.items():
        dep_ref = purl_cache.get(pkg_name, "")
        dep_on = [purl_cache.get(d) for d in pkg_info.get("depends_on", {}) if purl_cache.get(d)]
        if dep_on:
            dependencies.append({"ref": dep_ref, "dependsOn": dep_on})
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "tools": [{"name": "universal-dependency-resolver"}],
        },
        "components": components,
        "dependencies": dependencies,
    }


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
