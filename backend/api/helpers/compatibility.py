import logging
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from packaging import version


class SystemSpec(BaseModel):
    os: Optional[str] = Field(
        None, description="Operating system (linux, windows, macos)"
    )
    os_version: Optional[str] = Field(None, description="OS version")
    architecture: Optional[str] = Field(
        None, description="CPU architecture (x86_64, arm64)"
    )
    python_version: Optional[str] = Field(None, description="Python version")
    cuda_version: Optional[str] = Field(None, description="CUDA version if available")
    gpu_available: Optional[bool] = Field(False, description="GPU availability")

    @classmethod
    def from_string(cls, spec_string: str) -> "SystemSpec":
        spec = cls(os=None, os_version=None, architecture=None, python_version=None, cuda_version=None, gpu_available=None)
        parts = spec_string.split(",")
        for part in parts:
            if "=" in part:
                key, value = part.split("=", 1)
                key = key.strip().lower()
                value = value.strip()
                if key in ["os", "operating_system"]:
                    spec.os = value.lower()
                elif key == "os_version":
                    spec.os_version = value
                elif key in ["arch", "architecture"]:
                    spec.architecture = value.lower()
                elif key in ["python", "python_version", "py"]:
                    spec.python_version = value
                elif key in ["cuda", "cuda_version"]:
                    spec.cuda_version = value
                elif key in ["gpu", "gpu_available"]:
                    spec.gpu_available = value.lower() in ["true", "yes", "1"]
        return spec


logger = logging.getLogger(__name__)


def _check_version_compatibility(version_info: Dict, system_spec: str) -> bool:
    try:
        spec = SystemSpec.from_string(system_spec)
        is_compatible, _ = _check_version_compatibility_detailed(version_info, spec)
        return is_compatible
    except Exception:
        return True


def _check_version_compatibility_detailed(
    version_info: Dict, system_spec: SystemSpec
) -> Tuple[bool, List[str]]:
    compatibility_notes = []
    is_compatible = True

    if system_spec.python_version and version_info.get("python_requires"):
        python_requires = version_info["python_requires"]
        if not _check_python_compatibility(system_spec.python_version, python_requires):
            is_compatible = False
            compatibility_notes.append(
                f"Requires Python {python_requires}, but system has {system_spec.python_version}"
            )

    if system_spec.os and version_info.get("platforms"):
        platforms = version_info["platforms"]
        if not _check_os_compatibility(system_spec.os, platforms):
            is_compatible = False
            compatibility_notes.append(
                f"Not available for {system_spec.os} (supports: {', '.join(platforms)})"
            )

    if system_spec.architecture and version_info.get("architectures"):
        architectures = version_info["architectures"]
        if system_spec.architecture not in architectures:
            is_compatible = False
            compatibility_notes.append(
                f"Not available for {system_spec.architecture} architecture"
            )

    if system_spec.cuda_version and version_info.get("cuda_required"):
        cuda_versions = version_info.get("cuda_versions", [])
        if cuda_versions and not _check_cuda_compatibility(
            system_spec.cuda_version, cuda_versions
        ):
            is_compatible = False
            compatibility_notes.append(
                f"Requires CUDA {', '.join(cuda_versions)}, but system has {system_spec.cuda_version}"
            )
    elif not system_spec.gpu_available and version_info.get("gpu_required"):
        is_compatible = False
        compatibility_notes.append("Requires GPU but none available")

    if version_info.get("yanked"):
        compatibility_notes.append("This version has been yanked by maintainers")

    return is_compatible, compatibility_notes


def _check_python_compatibility(system_python: str, requires_python: str) -> bool:
    try:
        from packaging.specifiers import SpecifierSet

        spec = SpecifierSet(requires_python)
        system_version = version.parse(system_python)
        return system_version in spec
    except Exception as e:
        logger.warning(f"Failed to check Python compatibility: {e}")
        return True


def _check_os_compatibility(system_os: str, supported_platforms: List[str]) -> bool:
    if not supported_platforms or "any" in supported_platforms:
        return True
    os_mapping = {
        "linux": ["linux", "manylinux", "unix", "posix"],
        "windows": ["windows", "win", "win32", "win_amd64"],
        "macos": ["macos", "darwin", "osx", "mac"],
        "darwin": ["macos", "darwin", "osx", "mac"],
    }
    system_aliases = os_mapping.get(system_os.lower(), [system_os.lower()])
    for platform in supported_platforms:
        platform_lower = platform.lower()
        if any(alias in platform_lower for alias in system_aliases):
            return True
    return False


def _check_cuda_compatibility(system_cuda: str, required_cuda: List[str]) -> bool:
    try:
        system_version = version.parse(system_cuda)
        for req_cuda in required_cuda:
            if req_cuda.endswith(".x"):
                req_major = int(req_cuda[:-2])
                if system_version.major == req_major:
                    return True
            elif any(op in req_cuda for op in [">=", "<=", ">", "<", "=="]):
                from packaging.specifiers import SpecifierSet

                spec = SpecifierSet(req_cuda.replace("cuda", "").strip())
                if system_version in spec:
                    return True
            else:
                req_version = version.parse(req_cuda)
                if system_version == req_version:
                    return True
        return False
    except Exception as e:
        logger.warning(f"Failed to check CUDA compatibility: {e}")
        return True


def _is_prerelease(version_str: str) -> bool:
    try:
        v = version.parse(version_str)
        return v.is_prerelease
    except Exception:
        prerelease_indicators = ["alpha", "beta", "rc", "dev", "pre", "a", "b"]
        version_lower = version_str.lower()
        return any(indicator in version_lower for indicator in prerelease_indicators)
