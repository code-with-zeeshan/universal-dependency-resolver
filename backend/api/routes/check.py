"""REST endpoints for CVE, license, deprecation, and policy checks."""

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.api.dependencies import get_data_aggregator, limiter
from backend.core.data_aggregator import DataAggregator
from backend.core.license_checker import check_license_compatibility
from backend.core.policy_engine import check_policy, load_policy

logger = logging.getLogger(__name__)
router = APIRouter()


class CVECheckRequest(BaseModel):
    """CVE check request — lock file packages to scan."""

    packages: dict[str, dict[str, Any]]


class LicenseCheckRequest(BaseModel):
    """License check request."""

    packages: dict[str, dict[str, Any]]


class DeprecatedCheckRequest(BaseModel):
    """Deprecation check request."""

    packages: dict[str, dict[str, Any]]


class PolicyCheckRequest(BaseModel):
    """Policy check request."""

    packages: dict[str, dict[str, Any]]
    policy_yaml: str | None = None


class CombinedCheckRequest(BaseModel):
    """Combined check request — runs CVE, license, deprecated, and policy in one call."""

    packages: dict[str, dict[str, Any]]
    policy_yaml: str | None = None


@router.post("/check/all")
@limiter.limit("5/minute")
async def check_all(
    request: Request,
    body: CombinedCheckRequest,
    aggregator: DataAggregator = Depends(get_data_aggregator),
) -> dict:
    """Run all checks (CVE, license, deprecated, policy) in a single call."""
    cve_results: list[dict] = []
    vuln_lock = asyncio.Lock()

    async def _check_cve_one(name: str, info: dict) -> None:
        eco = info.get("ecosystem", "")
        ver = info.get("resolved_version", "")
        if not eco or not ver:
            return
        try:
            vulns = await aggregator.check_vulnerabilities(name, eco, ver)
            async with vuln_lock:
                for v in vulns:
                    cve_results.append(
                        {
                            "package": name,
                            "version": ver,
                            "cve_id": v.get("id", "?"),
                            "severity": v.get("severity", "UNKNOWN"),
                            "summary": v.get("summary", ""),
                        }
                    )
        except Exception:
            logger.warning("CVE check failed for %s", name, exc_info=True)

    await asyncio.gather(*[_check_cve_one(n, i) for n, i in body.packages.items()])

    package_licenses: dict[str, str | list[str]] = {}
    missing_licenses: list[tuple[str, str]] = []

    for pname, pinfo in body.packages.items():
        raw_license = pinfo.get("license")
        if raw_license:
            package_licenses[pname] = raw_license
        else:
            eco = pinfo.get("ecosystem", "pypi")
            missing_licenses.append((pname, eco))

    if missing_licenses:
        for pname, eco in missing_licenses:
            try:
                data = await aggregator.get_package_info(
                    pname, ecosystem=eco, include_dependencies=False, include_versions=False
                )
                if data:
                    lic = data.get("license") or data.get("info", {}).get("license", "")
                    if lic:
                        package_licenses[pname] = lic
            except Exception:
                logger.warning("Failed to fetch license for %s", pname, exc_info=True)

    license_results: dict[str, dict] = {}
    if package_licenses:
        license_results = check_license_compatibility(package_licenses)

    deprecated_results: list[dict] = []
    for pname, pinfo in body.packages.items():
        ver = pinfo.get("resolved_version", "")
        if pinfo.get("yanked"):
            deprecated_results.append({"package": pname, "version": ver, "status": "yanked"})
        elif pinfo.get("deprecated"):
            deprecated_results.append({"package": pname, "version": ver, "status": "deprecated"})

    policy_violations: list[dict] = []
    if body.policy_yaml:
        import tempfile
        from pathlib import Path as _Path

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write(body.policy_yaml)
        try:
            policy = load_policy(tmp.name)
        finally:
            _Path(tmp.name).unlink(missing_ok=True)

        lock_data = {"packages": body.packages}
        policy_violations = check_policy(lock_data, policy)

    return {
        "status": "success",
        "cve": {
            "total_vulnerabilities": len(cve_results),
            "results": cve_results,
        },
        "license": {
            "total_checked": len(license_results),
            "denied": sorted({n for n, r in license_results.items() if r["status"] == "denied"}),
            "results": license_results,
        },
        "deprecated": {
            "total_deprecated": len(deprecated_results),
            "results": deprecated_results,
        },
        "policy": {
            "total_violations": len(policy_violations),
            "results": policy_violations,
        },
    }


@router.post("/check/cve")
@limiter.limit("10/minute")
async def check_cve(
    request: Request,
    body: CVECheckRequest,
    aggregator: DataAggregator = Depends(get_data_aggregator),
) -> dict:
    """Scan lock file packages against OSV vulnerability database."""
    vuln_results: list[dict] = []

    async def _check_one(name: str, info: dict) -> None:
        eco = info.get("ecosystem", "")
        ver = info.get("resolved_version", "")
        if not eco or not ver:
            return
        try:
            vulns = await aggregator.check_vulnerabilities(name, eco, ver)
            for v in vulns:
                vuln_results.append(
                    {
                        "package": name,
                        "version": ver,
                        "cve_id": v.get("id", "?"),
                        "severity": v.get("severity", "UNKNOWN"),
                        "summary": v.get("summary", ""),
                    }
                )
        except Exception:
            logger.warning("CVE check failed for %s", name, exc_info=True)

    await asyncio.gather(*[_check_one(n, i) for n, i in body.packages.items()])
    return {
        "status": "success",
        "total_vulnerabilities": len(vuln_results),
        "results": vuln_results,
    }


@router.post("/check/license")
@limiter.limit("10/minute")
async def check_license(
    request: Request,
    body: LicenseCheckRequest,
    aggregator: DataAggregator = Depends(get_data_aggregator),
) -> dict:
    """Check lock file packages for license compliance."""
    package_licenses: dict[str, str | list[str]] = {}
    missing_licenses: list[tuple[str, str]] = []

    for pname, pinfo in body.packages.items():
        raw_license = pinfo.get("license")
        if raw_license:
            package_licenses[pname] = raw_license
        else:
            eco = pinfo.get("ecosystem", "pypi")
            missing_licenses.append((pname, eco))

    if missing_licenses:
        for pname, eco in missing_licenses:
            try:
                data = await aggregator.get_package_info(
                    pname, ecosystem=eco, include_dependencies=False, include_versions=False
                )
                if data:
                    lic = data.get("license") or data.get("info", {}).get("license", "")
                    if lic:
                        package_licenses[pname] = lic
            except Exception:
                logger.warning("Failed to fetch license for %s", pname, exc_info=True)

    if not package_licenses:
        return {"status": "success", "message": "No license information found.", "results": {}}

    results = check_license_compatibility(package_licenses)
    denied = {n for n, r in results.items() if r["status"] == "denied"}
    warnings = {n for n, r in results.items() if r["status"] == "warning"}

    return {
        "status": "violation" if denied else ("warning" if warnings else "success"),
        "total_checked": len(results),
        "denied": sorted(denied),
        "warnings": sorted(warnings),
        "results": results,
    }


@router.post("/check/deprecated")
@limiter.limit("10/minute")
async def check_deprecated(
    request: Request,
    body: DeprecatedCheckRequest,
) -> dict:
    """Check lock file packages for deprecated/yanked versions."""
    deprecated: list[dict] = []
    for pname, pinfo in body.packages.items():
        ver = pinfo.get("resolved_version", "")
        if pinfo.get("yanked"):
            deprecated.append({"package": pname, "version": ver, "status": "yanked"})
        elif pinfo.get("deprecated"):
            deprecated.append({"package": pname, "version": ver, "status": "deprecated"})

    return {
        "status": "success" if not deprecated else "issues_found",
        "total_deprecated": len(deprecated),
        "has_yanked": any(d["status"] == "yanked" for d in deprecated),
        "results": deprecated,
    }


@router.post("/check/policy")
@limiter.limit("10/minute")
async def check_policy_endpoint(
    request: Request,
    body: PolicyCheckRequest,
) -> dict:
    """Check lock file packages against project policy."""
    policy: dict[str, Any]
    if body.policy_yaml:
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write(body.policy_yaml)
        try:
            policy = load_policy(tmp.name)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    else:
        candidate = Path("udr-policy.yaml")
        if not candidate.is_file():
            raise HTTPException(
                status_code=404,
                detail="No policy file found. Provide policy_yaml in request body or create udr-policy.yaml.",
            )
        policy = load_policy(str(candidate))

    lock_data = {"packages": body.packages}
    violations = check_policy(lock_data, policy)
    has_error = any(v.get("severity") == "error" for v in violations)

    return {
        "status": "violation" if has_error else ("warning" if violations else "ok"),
        "total_violations": len(violations),
        "results": violations,
    }
