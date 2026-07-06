"""Module docstring."""

# backend/api/routes/system.py
import asyncio
import logging
import re
import subprocess
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.auth import get_current_user
from backend.api.dependencies import get_system_scanner, limiter
from backend.core._json import loads
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


class EnvironmentAnalysis(BaseModel):
    """Environment Analysis functionality."""

    filename: str
    type: str
    packages: list[dict[str, Any]]
    system_requirements: dict[str, Any]
    potential_conflicts: list[dict[str, Any]]
    estimated_size: int | None = None
    python_version_required: str | None = None


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
            check_result = _check_requirement_comprehensive(system_info, req)
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


def _check_requirement_comprehensive(
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
        result.update(_check_memory_requirement(system_info, requirement))

    elif requirement.type == "disk":
        result.update(_check_disk_requirement(system_info, requirement))

    elif requirement.type == "os":
        result.update(_check_os_requirement(system_info, requirement))

    elif requirement.type == "python":
        result.update(_check_python_requirement(system_info, requirement))

    elif requirement.type == "compiler":
        result.update(_check_compiler_requirement(system_info, requirement))

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


def _check_memory_requirement(
    system_info: dict[str, Any], requirement: SystemRequirement
) -> dict[str, Any]:
    """Check memory requirements."""
    import psutil

    result: dict[str, Any] = {"details": {}}

    memory = psutil.virtual_memory()
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


def _check_disk_requirement(
    system_info: dict[str, Any], requirement: SystemRequirement
) -> dict[str, Any]:
    """Check disk space requirements."""
    import psutil

    result: dict[str, Any] = {"details": {}}

    disk = psutil.disk_usage("/")
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


def _check_compiler_requirement(
    system_info: dict[str, Any], requirement: SystemRequirement
) -> dict[str, Any]:
    """Check compiler requirements."""
    result: dict[str, Any] = {"details": {}}

    if requirement.minimum:
        for compiler, version in requirement.minimum.items():
            installed_version = _get_compiler_version(compiler)

            if not installed_version:
                result["status"] = "fail"
                result["message"] = f"{compiler} compiler required but not found"
                result["recommendation"] = f"Install {compiler} {version} or later"
            elif version and not _is_compatible_version(installed_version, version):
                result["status"] = "fail"
                result["message"] = f"{compiler} {version} required, but {installed_version} found"

    return result


def _extract_python_version_requirement(content: str) -> str | None:
    """Extract Python version requirement from requirements.txt."""
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("#") and "python" in line.lower():
            # Look for patterns like "# Requires Python >= 3.8"
            match = re.search(r"python\s*([><=]+)\s*([\d.]+)", line, re.I)
            if match:
                return f"{match.group(1)}{match.group(2)}"

    return None


async def _analyze_package_requirements(
    analysis: EnvironmentAnalysis,
) -> EnvironmentAnalysis:
    """Analyze packages for system requirements and conflicts."""
    # Known packages with special requirements
    gpu_packages = {
        "tensorflow-gpu",
        "torch",
        "pytorch",
        "jax",
        "cupy",
        "mxnet",
        "paddle",
        "tensorrt",
        "onnxruntime-gpu",
    }

    large_memory_packages = {
        "tensorflow",
        "pytorch",
        "scipy",
        "pandas",
        "dask",
        "ray",
        "spark",
        "h2o",
    }

    compiler_packages = {
        "numpy",
        "scipy",
        "scikit-learn",
        "matplotlib",
        "pillow",
        "opencv-python",
    }

    # Analyze packages
    for package in analysis.packages:
        pkg_name = package.get("name", "").lower()

        # Check for GPU requirements
        if any(gpu_pkg in pkg_name for gpu_pkg in gpu_packages):
            analysis.system_requirements["gpu"] = {
                "required": True,
                "cuda": "recommended",
            }

        # Check for memory requirements
        if pkg_name in large_memory_packages:
            current_mem = analysis.system_requirements.get("memory", {}).get("minimum_gb", 4)
            analysis.system_requirements["memory"] = {
                "minimum_gb": max(current_mem, 8),
                "recommended_gb": max(current_mem * 1.5, 16),
            }

        # Check for compiler requirements
        if pkg_name in compiler_packages:
            analysis.system_requirements["compiler"] = {"c": True, "cpp": True}

    # Check for known conflicts
    analysis.potential_conflicts = _detect_package_conflicts(analysis.packages)

    return analysis


def _detect_package_conflicts(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect potential package conflicts."""
    conflicts = []

    # Known conflicting packages
    conflict_groups = [
        ["tensorflow", "tensorflow-gpu"],
        ["pillow", "pil"],
        ["opencv-python", "opencv-contrib-python"],
    ]

    package_names = {pkg["name"].lower() for pkg in packages}

    for group in conflict_groups:
        found = [pkg for pkg in group if pkg in package_names]
        if len(found) > 1:
            conflicts.append(
                {
                    "packages": found,
                    "reason": "These packages may conflict with each other",
                }
            )

    return conflicts


async def _estimate_installation_size(packages: list[dict[str, Any]]) -> int:
    """Estimate total installation size in MB."""
    # This would ideally fetch actual package sizes
    # For now, use rough estimates

    size_estimates = {
        "tensorflow": 500,
        "pytorch": 750,
        "torch": 750,
        "scipy": 150,
        "numpy": 50,
        "pandas": 100,
        "matplotlib": 200,
        "opencv": 300,
        "scikit-learn": 100,
    }

    total_size = 0

    for package in packages:
        pkg_name = package.get("name", "").lower()

        # Check for known packages
        for known_pkg, size in size_estimates.items():
            if known_pkg in pkg_name:
                total_size += size
                break
        else:
            # Default estimate
            total_size += 10

    return total_size


async def _get_detailed_gpu_info() -> list[dict[str, Any]]:
    """Get detailed GPU information using nvidia-smi."""
    gpu_details = []

    try:
        # Query multiple GPU properties
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,driver_version,vbios_version,memory.total,"
                "memory.free,memory.used,temperature.gpu,utilization.gpu,"
                "utilization.memory,power.draw,power.limit,compute_mode,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 14:
                    gpu_details.append(
                        {
                            "index": int(parts[0]),
                            "name": parts[1],
                            "driver_version": parts[2],
                            "vbios_version": parts[3],
                            "memory": {
                                "total_mb": int(float(parts[4])),
                                "free_mb": int(float(parts[5])),
                                "used_mb": int(float(parts[6])),
                            },
                            "temperature_celsius": int(parts[7]) if parts[7] != "N/A" else None,
                            "utilization": {
                                "gpu_percent": int(parts[8]) if parts[8] != "N/A" else 0,
                                "memory_percent": int(parts[9]) if parts[9] != "N/A" else 0,
                            },
                            "power": {
                                "draw_watts": float(parts[10]) if parts[10] != "N/A" else None,
                                "limit_watts": float(parts[11]) if parts[11] != "N/A" else None,
                            },
                            "compute_mode": parts[12],
                            "compute_capability": parts[13],
                        }
                    )
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return gpu_details


def _check_gpu_compute_capabilities() -> dict[str, Any]:
    """Check GPU compute capabilities for various frameworks."""
    capabilities: dict[str, Any] = {}

    try:
        import torch

        if torch.cuda.is_available():
            capabilities["pytorch"] = {
                "available": True,
                "cuda_version": torch.version.cuda,
                "cudnn_version": torch.backends.cudnn.version(),
                "device_count": torch.cuda.device_count(),
            }
    except ImportError:
        capabilities["pytorch"] = {"available": False}

    try:
        import tensorflow as tf

        gpus = tf.config.list_physical_devices("GPU")
        capabilities["tensorflow"] = {
            "available": len(gpus) > 0,
            "device_count": len(gpus),
        }
    except ImportError:
        capabilities["tensorflow"] = {"available": False}

    return capabilities


def _check_gpu_framework_support() -> dict[str, Any]:
    """Check which deep learning frameworks can use the GPU."""
    support: dict[str, Any] = {}

    frameworks = {
        "pytorch": "torch",
        "tensorflow": "tensorflow",
        "jax": "jax",
        "mxnet": "mxnet",
        "paddlepaddle": "paddle",
    }

    for name, module in frameworks.items():
        try:
            __import__(module)
            support[name] = True
        except ImportError:
            support[name] = False

    return support


async def _check_docker() -> dict[str, Any]:
    """Check Docker installation and version."""
    try:
        docker_info: dict[str, Any]
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            version_output = result.stdout.strip()

            # Get more Docker info
            info_result = subprocess.run(
                ["docker", "info", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            docker_info = {"version": version_output, "available": True}  # type: ignore[assignment]

            if info_result.returncode == 0:
                info_data = loads(info_result.stdout)
                docker_info.update(
                    {
                        "server_version": info_data.get("ServerVersion"),
                        "storage_driver": info_data.get("Driver"),
                        "containers": info_data.get("Containers", 0),
                        "images": info_data.get("Images", 0),
                    }
                )

            return docker_info
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return {"available": False}


async def _check_rust() -> dict[str, Any]:
    """Check Rust installation."""
    rust_info: dict[str, Any] = {"available": False}

    try:
        # Check rustc
        rustc_result = subprocess.run(
            ["rustc", "--version"], capture_output=True, text=True, timeout=5
        )

        if rustc_result.returncode == 0:
            rust_info["rustc"] = rustc_result.stdout.strip()
            rust_info["available"] = True

        # Check cargo
        cargo_result = subprocess.run(
            ["cargo", "--version"], capture_output=True, text=True, timeout=5
        )

        if cargo_result.returncode == 0:
            rust_info["cargo"] = cargo_result.stdout.strip()

        # Check installed toolchains
        toolchain_result = subprocess.run(
            ["rustup", "toolchain", "list"], capture_output=True, text=True, timeout=5
        )

        if toolchain_result.returncode == 0:
            rust_info["toolchains"] = toolchain_result.stdout.strip().split("\n")

    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return rust_info


async def _check_go() -> dict[str, Any]:
    """Check Go installation."""
    try:
        result = subprocess.run(["go", "version"], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            version_output = result.stdout.strip()

            go_info: dict[str, Any] = {"version": version_output, "available": True}

            # Get GOPATH and GOROOT
            env_result = subprocess.run(
                ["go", "env", "GOPATH", "GOROOT"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if env_result.returncode == 0:
                lines = env_result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    go_info["GOPATH"] = lines[0]
                    go_info["GOROOT"] = lines[1]

            return go_info
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return {"available": False}


async def _check_julia() -> dict[str, Any]:
    """Check Julia installation."""
    try:
        result = subprocess.run(["julia", "--version"], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            return {"version": result.stdout.strip(), "available": True}
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return {"available": False}


async def _check_r() -> dict[str, Any]:
    """Check R installation."""
    try:
        result = subprocess.run(["R", "--version"], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            # Extract version from output
            lines = result.stdout.strip().split("\n")
            version_line = lines[0] if lines else ""

            return {"version": version_line, "available": True}
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return {"available": False}


async def _check_dotnet() -> dict[str, Any]:
    """Check .NET installation."""
    try:
        result = subprocess.run(["dotnet", "--info"], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            info: dict[str, Any] = {"available": True}

            # Parse .NET info
            lines = result.stdout.strip().split("\n")
            for line in lines:
                if "Version:" in line:
                    info["version"] = line.split("Version:")[1].strip()
                    break

            # List SDKs
            sdk_result = subprocess.run(
                ["dotnet", "--list-sdks"], capture_output=True, text=True, timeout=5
            )

            if sdk_result.returncode == 0:
                info["sdks"] = sdk_result.stdout.strip().split("\n")

            return info
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return {"available": False}


async def _check_ruby() -> dict[str, Any]:
    """Check Ruby installation."""
    try:
        result = subprocess.run(["ruby", "--version"], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            ruby_info = {"version": result.stdout.strip(), "available": True}

            # Check gem
            gem_result = subprocess.run(
                ["gem", "--version"], capture_output=True, text=True, timeout=5
            )

            if gem_result.returncode == 0:
                ruby_info["gem_version"] = gem_result.stdout.strip()

            return ruby_info
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return {"available": False}


async def _check_php() -> dict[str, Any]:
    """Check PHP installation."""
    try:
        result = subprocess.run(["php", "--version"], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            php_info = {
                "version": result.stdout.strip().split("\n")[0],
                "available": True,
            }

            # Check composer
            composer_result = subprocess.run(
                ["composer", "--version"], capture_output=True, text=True, timeout=5
            )

            if composer_result.returncode == 0:
                php_info["composer_version"] = composer_result.stdout.strip()

            return php_info
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return {"available": False}


async def _check_kotlin() -> dict[str, Any]:
    """Check Kotlin installation."""
    try:
        result = subprocess.run(["kotlin", "-version"], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            return {"version": result.stdout.strip(), "available": True}
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return {"available": False}


async def _check_scala() -> dict[str, Any]:
    """Check Scala installation."""
    try:
        result = subprocess.run(["scala", "-version"], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            return {
                "version": result.stderr.strip(),  # Scala outputs version to stderr
                "available": True,
            }
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return {"available": False}


def _get_npm_version() -> str | None:
    """Get npm version."""
    try:
        result = subprocess.run(["npm", "--version"], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return None


async def _get_python_packages() -> list[dict[str, Any]]:
    """Get list of installed Python packages."""
    try:
        result = subprocess.run(
            ["pip", "list", "--format=json"], capture_output=True, text=True, timeout=10
        )

        if result.returncode == 0:
            return loads(result.stdout)
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return []


async def _get_npm_global_packages() -> list[str]:
    """Get list of globally installed npm packages."""
    try:
        result = subprocess.run(
            ["npm", "list", "-g", "--depth=0"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")[1:]  # Skip first line
            return [line.strip() for line in lines if line.strip()]
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return []


def _detect_virtual_env() -> dict[str, Any]:
    """Detect if running in a virtual environment."""
    import os
    import sys

    venv_info: dict[str, Any] = {"active": False, "type": None, "path": None}

    # Check for virtualenv/venv
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        venv_info["active"] = True
        venv_info["type"] = "venv"
        venv_info["path"] = sys.prefix

    # Check for conda
    if "CONDA_DEFAULT_ENV" in os.environ:
        venv_info["active"] = True
        venv_info["type"] = "conda"
        venv_info["name"] = os.environ.get("CONDA_DEFAULT_ENV")
        venv_info["path"] = os.environ.get("CONDA_PREFIX")

    # Check for poetry
    if "POETRY_ACTIVE" in os.environ:
        venv_info["active"] = True
        venv_info["type"] = "poetry"

    return venv_info  # type: ignore[return-value]


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

                result = _check_requirement_comprehensive(system_info, requirement)
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


def _get_compiler_version(compiler: str) -> str | None:
    """Get compiler version."""
    try:
        if compiler == "gcc":
            result = subprocess.run(["gcc", "--version"], capture_output=True, text=True)
        elif compiler == "g++":
            result = subprocess.run(["g++", "--version"], capture_output=True, text=True)
        elif compiler == "clang":
            result = subprocess.run(["clang", "--version"], capture_output=True, text=True)
        elif compiler == "msvc":
            result = subprocess.run(["cl"], capture_output=True, text=True)
        else:
            return None

        if result.returncode == 0:
            # Extract version from first line
            first_line = result.stdout.strip().split("\n")[0]
            # Use regex to find version number
            match = re.search(r"(\d+\.\d+(?:\.\d+)?)", first_line)
            if match:
                return match.group(1)
    except Exception:
        logger.debug("Runtime detection failed", exc_info=True)

    return None


async def _benchmark_cpu() -> dict[str, Any]:
    """Run CPU benchmark in thread pool."""
    return await asyncio.to_thread(_benchmark_cpu_sync)


def _benchmark_cpu_sync() -> dict[str, Any]:
    """Synchronous CPU benchmark (runs in thread pool)."""
    import time

    results: dict[str, Any] = {}

    try:
        import numpy as np

        # Single-threaded benchmark
        start = time.time()
        size = 2000
        a = np.random.rand(size, size)
        b = np.random.rand(size, size)
        np.dot(a, b)
        single_thread_time = time.time() - start

        results["matrix_multiply_single"] = {
            "time_seconds": round(single_thread_time, 3),
            "size": f"{size}x{size}",
            "gflops": round((2 * size**3) / (single_thread_time * 1e9), 2),
        }
    except ImportError:
        results["matrix_multiply_single"] = {
            "error": "numpy not installed",
            "skipped": True,
        }

    # Integer operations benchmark
    start = time.time()
    count = 10000000
    sum(i for i in range(count))
    int_time = time.time() - start

    results["integer_operations"] = {
        "time_seconds": round(int_time, 3),
        "operations": count,
        "ops_per_second": round(count / int_time),
    }

    return results


def _benchmark_memory() -> dict[str, Any]:
    """Run memory benchmark."""
    import psutil

    memory = psutil.virtual_memory()

    return {
        "total_gb": round(memory.total / (1024**3), 2),
        "available_gb": round(memory.available / (1024**3), 2),
        "used_gb": round(memory.used / (1024**3), 2),
        "percent_used": memory.percent,
        "swap": {
            "total_gb": round(psutil.swap_memory().total / (1024**3), 2),
            "used_gb": round(psutil.swap_memory().used / (1024**3), 2),
            "percent_used": psutil.swap_memory().percent,
        },
    }


async def _benchmark_disk() -> dict[str, Any]:
    """Run disk benchmark."""
    import os
    import tempfile
    import time

    import psutil

    results: dict[str, Any] = {}

    # Disk usage
    disk = psutil.disk_usage("/")
    results["usage"] = {
        "total_gb": round(disk.total / (1024**3), 2),
        "free_gb": round(disk.free / (1024**3), 2),
        "percent_used": disk.percent,
    }

    # Simple write/read benchmark
    try:
        test_size = 100 * 1024 * 1024  # 100MB
        test_data = os.urandom(test_size)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            # Write test
            start = time.time()
            tmp.write(test_data)
            tmp.flush()
            os.fsync(tmp.fileno())
            write_time = time.time() - start

            results["write_speed_mbps"] = round((test_size / (1024**2)) / write_time, 2)

            # Read test
            tmp.seek(0)
            start = time.time()
            tmp.read()
            read_time = time.time() - start

            results["read_speed_mbps"] = round((test_size / (1024**2)) / read_time, 2)

            os.unlink(tmp.name)
    except Exception as e:
        results["benchmark_error"] = str(e)

    return results


async def _benchmark_gpu() -> dict[str, Any]:
    """Run GPU benchmark."""
    results: dict[str, Any] = {}

    try:
        import torch

        if torch.cuda.is_available():
            device = torch.device("cuda:0")

            # Warm up
            a = torch.randn(1000, 1000).to(device)
            b = torch.randn(1000, 1000).to(device)
            torch.matmul(a, b)
            torch.cuda.synchronize()

            # Matrix multiplication benchmark
            sizes = [2000, 4000, 8000]
            for size in sizes:
                a = torch.randn(size, size).to(device)
                b = torch.randn(size, size).to(device)

                torch.cuda.synchronize()
                start = time.time()

                torch.matmul(a, b)

                torch.cuda.synchronize()
                elapsed = time.time() - start

                results[f"matrix_multiply_{size}"] = {
                    "time_seconds": round(elapsed, 3),
                    "size": f"{size}x{size}",
                    "tflops": round((2 * size**3) / (elapsed * 1e12), 2),
                }

            # Memory transfer benchmark
            size_mb = 1000
            data = torch.randn(size_mb * 1024 * 1024 // 4).cpu()  # float32

            # Host to device
            start = time.time()
            data_gpu = data.to(device)
            torch.cuda.synchronize()
            h2d_time = time.time() - start

            results["memory_transfer"] = {
                "host_to_device_gbps": round(size_mb / 1024 / h2d_time, 2)
            }

            # Device to host
            start = time.time()
            data_gpu.cpu()
            torch.cuda.synchronize()
            d2h_time = time.time() - start

            results["memory_transfer"]["device_to_host_gbps"] = round(size_mb / 1024 / d2h_time, 2)

        else:
            results["error"] = "CUDA not available"

    except ImportError:
        results["error"] = "PyTorch not installed"
    except Exception as e:
        results["error"] = str(e)

    return results


async def _benchmark_cpu_multicore() -> dict[str, Any]:
    """Run multi-core CPU benchmark."""
    import concurrent.futures
    import multiprocessing
    import time

    try:
        import numpy as np
    except ImportError:
        return {"error": "numpy not installed", "skipped": True}

    def cpu_task(size=1000):
        """Cpu task."""
        a = np.random.rand(size, size)
        b = np.random.rand(size, size)
        c = np.dot(a, b)
        return c.sum()

    results: dict[str, Any] = {}
    num_cores = multiprocessing.cpu_count()

    # Test scaling with different thread counts
    for num_threads in [1, num_cores // 2, num_cores]:
        start = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(cpu_task) for _ in range(num_threads)]
            [f.result() for f in futures]

        elapsed = time.time() - start

        results[f"threads_{num_threads}"] = {
            "time_seconds": round(elapsed, 3),
            "speedup": round(
                1 / elapsed if num_threads == 1 else results["threads_1"]["time_seconds"] / elapsed,
                2,
            ),
        }

    return results


async def _benchmark_network() -> dict[str, Any]:
    """Run network benchmark."""
    import time

    import aiohttp

    results: dict[str, Any] = {}

    # DNS lookup benchmark
    start = time.time()
    try:
        import socket

        socket.gethostbyname("www.google.com")
        dns_time = time.time() - start
        results["dns_lookup_ms"] = round(dns_time * 1000, 2)
    except Exception as e:
        results["dns_error"] = str(e)

    # HTTP request benchmark
    test_urls = [
        ("google", "https://www.google.com"),
        ("cloudflare", "https://1.1.1.1"),
    ]

    async with aiohttp.ClientSession() as session:
        for name, url in test_urls:
            try:
                start = time.time()
                async with session.get(url) as response:  # type: ignore[arg-type]
                    await response.read()
                    latency = time.time() - start

                    results[f"{name}_latency_ms"] = round(latency * 1000, 2)
            except Exception as e:
                results[f"{name}_error"] = str(e)

    return results


async def _benchmark_python() -> dict[str, Any]:
    """Run Python-specific benchmarks."""
    import time

    results: dict[str, Any] = {}

    # Import time benchmark
    packages = ["numpy", "pandas", "matplotlib"]
    for package in packages:
        try:
            start = time.time()
            __import__(package)
            import_time = time.time() - start
            results[f"import_{package}_ms"] = round(import_time * 1000, 2)
        except ImportError:
            results[f"import_{package}_ms"] = "not installed"

    # List comprehension benchmark
    start = time.time()
    [i**2 for i in range(1000000)]
    list_comp_time = time.time() - start
    results["list_comprehension_ms"] = round(list_comp_time * 1000, 2)

    # Dictionary operations
    start = time.time()
    d = {}
    for i in range(100000):
        d[i] = i**2
    for i in range(100000):
        _ = d[i]
    dict_time = time.time() - start
    results["dict_operations_ms"] = round(dict_time * 1000, 2)

    return results


def _compare_benchmark_results(benchmarks: dict[str, Any]) -> dict[str, Any]:
    """Compare benchmark results with typical values."""
    typical_values: dict[str, Any] = {
        "cpu": {
            "matrix_multiply_single": {
                "gflops": {"poor": 1, "average": 5, "good": 10, "excellent": 20}
            }
        },
        "gpu": {
            "matrix_multiply_4000": {
                "tflops": {"poor": 0.5, "average": 2, "good": 5, "excellent": 10}
            }
        },
        "disk": {
            "write_speed_mbps": {
                "poor": 50,
                "average": 200,
                "good": 500,
                "excellent": 1000,
            },
            "read_speed_mbps": {
                "poor": 100,
                "average": 300,
                "good": 800,
                "excellent": 2000,
            },
        },
    }

    comparison: dict[str, Any] = {}

    for category, tests in typical_values.items():
        if category in benchmarks:
            comparison[category] = {}

            for test, metrics in tests.items():
                if test in benchmarks[category]:
                    actual = benchmarks[category][test]
                    if not isinstance(actual, dict):
                        continue

                    for metric, ranges in metrics.items():
                        if metric in actual:
                            value = actual[metric]

                            rating = "poor"
                            for level in ["poor", "average", "good", "excellent"]:
                                if value >= ranges[level]:
                                    rating = level

                            comparison[category][f"{test}_{metric}_rating"] = rating

    return comparison
