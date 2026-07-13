"""Module docstring."""

# backend/api/routes/system.py
import asyncio
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.auth import get_current_user
from backend.api.dependencies import get_system_scanner, limiter
from backend.core.system_scanner import SystemScanner
from backend.orchestrator.db_service import User

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize system scanner
system_scanner = SystemScanner()


# Keep all your existing models
class SystemRequirement(BaseModel):
    """System Requirement functionality."""

    type: str  # 'gpu', 'cpu', 'os', 'memory', 'disk', 'python', 'compiler'
    minimum: dict[str, Any] | None = Field(default_factory=dict)
    recommended: dict[str, Any] | None = Field(default_factory=dict)
    required: bool = True


class SystemCheckRequest(BaseModel):
    """System Check Request functionality."""

    requirements: list[SystemRequirement]
    packages: list[str] | None = None


# MOVED FROM main.py - System info endpoint (renamed from /api/system-info)
@router.get("/info")
@limiter.limit("30/minute")
async def get_system_info(
    request: Request,
    scanner: SystemScanner = Depends(get_system_scanner),
    detailed: bool = False,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get current system information."""
    try:
        info = await scanner.scan_all()

        if not detailed:
            cpu_info = info.get("cpu", {})
            gpu_info = info.get("gpu", {})
            return {
                "status": "success",
                "system": {
                    "os": f"{info.get('platform', {}).get('system', 'unknown')} {info.get('platform', {}).get('release', '')}",
                    "cpu": cpu_info.get("brand", "Unknown"),
                    "gpu": gpu_info.get("devices", [{}])[0].get("name")
                    if gpu_info.get("available")
                    else None,
                    "cuda": gpu_info.get("cuda"),
                    "python": info.get("runtime_versions", {})
                    .get("python", {})
                    .get("version", "unknown"),
                },
            }

        return {"status": "success", "data": info}
    except ValueError as e:
        logger.error(f"Invalid system scan data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"System scan failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Keep all your existing endpoints exactly as they were
@router.post("/check-compatibility")
@limiter.limit("10/minute")
async def check_system_compatibility(
    request: Request,
    check_request: SystemCheckRequest,
    scanner: SystemScanner = Depends(get_system_scanner),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Check if system meets specified requirements."""
    try:
        system_info = await scanner.scan_all()
        results: dict[str, Any] = {
            "compatible": True,
            "checks": [],
            "warnings": [],
            "errors": [],
            "recommendations": [],
        }

        for req in check_request.requirements:
            check_result = await _check_requirement_comprehensive(system_info, req)
            results["checks"].append(check_result)

            if check_result["status"] == "fail":
                results["compatible"] = False
                results["errors"].append(check_result["message"])
            elif check_result["status"] == "warning":
                results["warnings"].append(check_result["message"])

            if "recommendation" in check_result:
                results["recommendations"].append(check_result["recommendation"])

        if check_request.packages:
            package_checks = await _check_package_requirements(check_request.packages, system_info)
            results["package_compatibility"] = package_checks

        return {"status": "success", "results": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _check_requirement_comprehensive(
    system_info: dict[str, Any], requirement: SystemRequirement
) -> dict[str, Any]:
    """Comprehensively check if system meets a specific requirement."""
    result: dict[str, Any] = {
        "type": requirement.type,
        "status": "pass",
        "message": "",
        "details": {},
    }

    if requirement.type == "gpu":
        result.update(_check_gpu_requirement(system_info, requirement))

    elif requirement.type == "cpu":
        result.update(_check_cpu_requirement(system_info, requirement))

    elif requirement.type == "memory":
        result.update(await _check_memory_requirement(system_info, requirement))

    elif requirement.type == "disk":
        result.update(await _check_disk_requirement(system_info, requirement))

    elif requirement.type == "os":
        result.update(_check_os_requirement(system_info, requirement))

    elif requirement.type == "python":
        result.update(_check_python_requirement(system_info, requirement))

    elif requirement.type == "compiler":
        result.update(await _check_compiler_requirement(system_info, requirement))

    return result


def _check_gpu_requirement(
    system_info: dict[str, Any], requirement: SystemRequirement
) -> dict[str, Any]:
    """Check GPU requirements."""
    result: dict[str, Any] = {"details": {}}

    if not system_info["gpu"]["available"]:
        if requirement.required:
            result["status"] = "fail"
            result["message"] = "GPU required but not available"
        else:
            result["status"] = "warning"
            result["message"] = "GPU recommended but not available"
        return result

    # Check CUDA version
    if requirement.minimum and "cuda" in requirement.minimum:
        required_cuda = requirement.minimum["cuda"]
        system_cuda = system_info["gpu"].get("cuda")

        if not system_cuda:
            result["status"] = "fail"
            result["message"] = f"CUDA {required_cuda} required but not installed"
            result["recommendation"] = f"Install CUDA {required_cuda} or later"
        else:
            from packaging import version

            if version.parse(system_cuda) < version.parse(required_cuda):
                result["status"] = "fail"
                result["message"] = f"CUDA {required_cuda} required, but {system_cuda} found"
                result["recommendation"] = f"Update CUDA to version {required_cuda} or later"

    # Check GPU memory
    if requirement.minimum and "memory_gb" in requirement.minimum:
        required_memory = requirement.minimum["memory_gb"]
        # Get GPU memory from devices
        min_gpu_memory = min(
            device.get("memory_mb", 0) / 1024 for device in system_info["gpu"].get("devices", [])
        )

        if min_gpu_memory < required_memory:
            result["status"] = "fail"
            result["message"] = (
                f"GPU with {required_memory}GB memory required, but only {min_gpu_memory:.1f}GB available"
            )

    # Check compute capability
    if requirement.minimum and "compute_capability" in requirement.minimum:
        requirement.minimum["compute_capability"]
        # This would need to be extracted from GPU info
        result["details"]["compute_capability_check"] = "pending"

    return result


def _check_cpu_requirement(
    system_info: dict[str, Any], requirement: SystemRequirement
) -> dict[str, Any]:
    """Check CPU requirements."""
    result: dict[str, Any] = {"details": {}}

    cpu_info = system_info["cpu"]

    # Check core count
    if requirement.minimum and "cores" in requirement.minimum:
        required_cores = requirement.minimum["cores"]
        available_cores = cpu_info.get("physical_cores", 0)

        if available_cores < required_cores:
            result["status"] = "fail"
            result["message"] = (
                f"Requires {required_cores} CPU cores, but only {available_cores} available"
            )

    # Check CPU features
    if requirement.minimum and "features" in requirement.minimum:
        required_features = requirement.minimum["features"]
        cpu_flags = cpu_info.get("flags", [])

        missing_features = [f for f in required_features if f not in cpu_flags]
        if missing_features:
            result["status"] = "fail"
            result["message"] = f"CPU missing required features: {', '.join(missing_features)}"

    # Check architecture
    if requirement.minimum and "architecture" in requirement.minimum:
        required_arch = requirement.minimum["architecture"]
        system_arch = cpu_info.get("architecture")

        if not _is_compatible_architecture(system_arch, required_arch):
            result["status"] = "fail"
            result["message"] = (
                f"Requires {required_arch} architecture, but system is {system_arch}"
            )

    return result


async def _check_memory_requirement(
    system_info: dict[str, Any], requirement: SystemRequirement
) -> dict[str, Any]:
    """Check memory requirements."""
    import psutil

    result: dict[str, Any] = {"details": {}}

    memory = await asyncio.to_thread(psutil.virtual_memory)
    available_gb = memory.total / (1024**3)

    if requirement.minimum and "gb" in requirement.minimum:
        required_gb = requirement.minimum["gb"]

        if available_gb < required_gb:
            result["status"] = "fail"
            result["message"] = (
                f"Requires {required_gb}GB RAM, but only {available_gb:.1f}GB available"
            )
            result["recommendation"] = (
                "Consider closing other applications or upgrading system memory"
            )

    if requirement.recommended and "gb" in requirement.recommended:
        recommended_gb = requirement.recommended["gb"]

        if available_gb < recommended_gb:
            result["status"] = "warning"
            result["message"] = (
                f"Recommended {recommended_gb}GB RAM, but only {available_gb:.1f}GB available"
            )

    # Check available memory
    available_free_gb = memory.available / (1024**3)
    if available_free_gb < 2:  # Less than 2GB free
        result["status"] = "warning"
        result["message"] = f"Low available memory: {available_free_gb:.1f}GB free"

    return result


async def _check_disk_requirement(
    system_info: dict[str, Any], requirement: SystemRequirement
) -> dict[str, Any]:
    """Check disk space requirements."""
    import psutil

    result: dict[str, Any] = {"details": {}}

    disk = await asyncio.to_thread(psutil.disk_usage, "/")
    available_gb = disk.free / (1024**3)

    if requirement.minimum and "gb" in requirement.minimum:
        required_gb = requirement.minimum["gb"]

        if available_gb < required_gb:
            result["status"] = "fail"
            result["message"] = (
                f"Requires {required_gb}GB disk space, but only {available_gb:.1f}GB available"
            )

    # Check disk type (SSD vs HDD)
    if requirement.minimum and "type" in requirement.minimum:
        requirement.minimum["type"]
        # This would need platform-specific implementation
        result["details"]["disk_type_check"] = "pending"

    return result


def _check_os_requirement(
    system_info: dict[str, Any], requirement: SystemRequirement
) -> dict[str, Any]:
    """Check OS requirements."""
    result: dict[str, Any] = {"details": {}}

    os_info = system_info["platform"]

    if requirement.minimum and "name" in requirement.minimum:
        required_os = requirement.minimum["name"].lower()
        system_os = os_info["system"].lower()

        if not _is_compatible_os(system_os, required_os):
            result["status"] = "fail"
            result["message"] = f"Requires {required_os}, but system is {system_os}"

    if requirement.minimum and "version" in requirement.minimum:
        required_version = requirement.minimum["version"]
        system_version = os_info.get("release", "")

        if not _is_compatible_os_version(system_os, system_version, required_version):
            result["status"] = "fail"
            result["message"] = (
                f"Requires {system_os} {required_version}, but system is {system_version}"
            )

    return result


def _check_python_requirement(
    system_info: dict[str, Any], requirement: SystemRequirement
) -> dict[str, Any]:
    """Check Python requirements."""
    result: dict[str, Any] = {"details": {}}

    python_info = system_info["runtime_versions"].get("python", {})

    if requirement.minimum and "version" in requirement.minimum:
        required_version = requirement.minimum["version"]
        system_version = python_info.get("version", "")

        from packaging import version

        if not system_version or version.parse(system_version) < version.parse(required_version):
            result["status"] = "fail"
            result["message"] = (
                f"Requires Python {required_version}, but system has {system_version}"
            )

    return result


async def _check_compiler_requirement(
    system_info: dict[str, Any], requirement: SystemRequirement
) -> dict[str, Any]:
    """Check compiler requirements."""
    result: dict[str, Any] = {"details": {}}

    if requirement.minimum:
        for compiler, version in requirement.minimum.items():
            installed_version = await _get_compiler_version(compiler)

            if not installed_version:
                result["status"] = "fail"
                result["message"] = f"{compiler} compiler required but not found"
                result["recommendation"] = f"Install {compiler} {version} or later"
            elif version and not _is_compatible_version(installed_version, version):
                result["status"] = "fail"
                result["message"] = f"{compiler} {version} required, but {installed_version} found"

    return result


async def _check_package_requirements(
    packages: list[str], system_info: dict[str, Any]
) -> dict[str, Any]:
    """Check system requirements for specific packages."""
    results: dict[str, Any] = {}

    # This would ideally query package metadata
    # For now, use known requirements
    package_requirements: dict[str, dict[str, Any]] = {
        "tensorflow": {
            "gpu": {"cuda": "11.2", "cudnn": "8.1"},
            "memory": {"minimum_gb": 8},
        },
        "pytorch": {
            "gpu": {"cuda": "11.7", "optional": True},
            "memory": {"minimum_gb": 4},
        },
        "opencv": {"compiler": {"cpp": True}},
    }

    for package in packages:
        if package in package_requirements:
            reqs = package_requirements[package]
            check_results = []

            for req_type, req_spec in reqs.items():
                requirement = SystemRequirement(
                    type=req_type,
                    minimum=req_spec
                    if not isinstance(req_spec, dict) or "optional" not in req_spec
                    else {k: v for k, v in req_spec.items() if k != "optional"},
                    required=not (isinstance(req_spec, dict) and req_spec.get("optional", False)),
                )

                result = await _check_requirement_comprehensive(system_info, requirement)
                check_results.append(result)

            results[package] = check_results

    return results


def _is_compatible_architecture(system_arch: str, required_arch: str) -> bool:
    """Check if architectures are compatible."""
    arch_aliases = {
        "x86_64": ["x86_64", "amd64", "x64"],
        "i386": ["i386", "i686", "x86"],
        "arm64": ["arm64", "aarch64"],
        "armv7": ["armv7", "armv7l"],
    }

    system_arch_lower = system_arch.lower()
    required_arch_lower = required_arch.lower()

    # Direct match
    if system_arch_lower == required_arch_lower:
        return True

    # Check aliases
    for arch, aliases in arch_aliases.items():
        if system_arch_lower in aliases and required_arch_lower in aliases:
            return True

    return False


def _is_compatible_os(system_os: str, required_os: str) -> bool:
    """Check if OS is compatible."""
    os_aliases = {
        "linux": ["linux", "gnu/linux"],
        "darwin": ["darwin", "macos", "osx"],
        "windows": ["windows", "win32", "win64"],
    }

    system_os_lower = system_os.lower()
    required_os_lower = required_os.lower()

    # Direct match
    if system_os_lower == required_os_lower:
        return True

    # Check aliases
    for os_name, aliases in os_aliases.items():
        if system_os_lower in aliases and required_os_lower in aliases:
            return True

    return False


def _is_compatible_os_version(os_name: str, system_version: str, required_version: str) -> bool:
    """Check if OS version is compatible."""
    try:
        if os_name.lower() == "darwin":  # macOS
            # Convert macOS version format
            sys_parts = system_version.split(".")
            req_parts = required_version.split(".")

            for i in range(min(len(sys_parts), len(req_parts))):
                if int(sys_parts[i]) < int(req_parts[i]):
                    return False
                if int(sys_parts[i]) > int(req_parts[i]):
                    return True

            return True
        # Generic version comparison
        from packaging import version

        return version.parse(system_version) >= version.parse(required_version)
    except Exception:
        logger.debug("Version comparison failed", exc_info=True)
        return True


def _is_compatible_version(installed: str, required: str) -> bool:
    """Check if installed version satisfies requirement."""
    try:
        from packaging import version
        from packaging.specifiers import SpecifierSet

        if any(op in required for op in [">=", "<=", ">", "<", "==", "~="]):
            spec = SpecifierSet(required)
            return version.parse(installed) in spec
        return version.parse(installed) >= version.parse(required)
    except Exception:
        logger.debug("Version comparison failed", exc_info=True)
        return True


async def _get_compiler_version(compiler: str) -> str | None:
    """Get compiler version asynchronously."""
    cmd_map = {
        "gcc": ["gcc", "--version"],
        "g++": ["g++", "--version"],
        "clang": ["clang", "--version"],
        "msvc": ["cl"],
    }
    cmd = cmd_map.get(compiler)
    if cmd is None:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0:
            first_line = stdout.decode().strip().split("\n")[0]
            match = re.search(r"(\d+\.\d+(?:\.\d+)?)", first_line)
            if match:
                return match.group(1)
    except (TimeoutError, FileNotFoundError):
        return None
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)
    return None
