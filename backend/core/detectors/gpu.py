"""GPU detection module."""

import logging
import os
import platform
import re
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backend.core.scanner_models import GPUInfo

from .._json import JSONDecodeError, loads

try:
    import GPUtil

    HAS_GPUTIL = True
except Exception:
    HAS_GPUTIL = False

try:
    from pynvml import (
        NVML_TEMPERATURE_GPU,
        nvmlDeviceGetCount,
        nvmlDeviceGetHandleByIndex,
        nvmlDeviceGetMemoryInfo,
        nvmlDeviceGetName,
        nvmlDeviceGetTemperature,
        nvmlDeviceGetUtilizationRates,
        nvmlInit,
        nvmlShutdown,
        nvmlSystemGetCudaDriverVersion,
        nvmlSystemGetDriverVersion,
    )

    HAS_PYNVML = True
except Exception:
    HAS_PYNVML = False

logger = logging.getLogger(__name__)


def detect_gpu_info(scanner) -> dict[str, Any]:
    """Detect comprehensive GPU information."""
    gpu_data: dict[str, Any] = {
        "available": False,
        "devices": [],
        "cuda": _detect_cuda_info(scanner),
        "rocm": _detect_rocm_info(scanner),
        "intel_gpu": _detect_intel_gpu_info(scanner),
        "opencl": _detect_opencl_info(scanner),
        "vulkan": _detect_vulkan_info(scanner),
        "metal": _detect_metal_info(scanner) if platform.system() == "Darwin" else None,
    }

    nvidia_gpus = _detect_nvidia_gpus(scanner)
    gpu_data["devices"].extend(nvidia_gpus)

    amd_gpus = _detect_amd_gpus(scanner)
    gpu_data["devices"].extend(amd_gpus)

    intel_gpus = _detect_intel_gpus(scanner)
    gpu_data["devices"].extend(intel_gpus)

    if gpu_data["devices"]:
        gpu_data["available"] = True

    return gpu_data


def _detect_nvidia_gpus(scanner) -> list[dict[str, Any]]:
    """Detect NVIDIA GPUs."""
    gpus = []

    if HAS_PYNVML:
        gpus.extend(_detect_gpus_pynvml())

    if not gpus and HAS_GPUTIL:
        try:
            gpu_list = GPUtil.getGPUs()
            for idx, gpu in enumerate(gpu_list):
                gpu_info = GPUInfo(
                    id=gpu.id,
                    name=gpu.name,
                    memory_total=int(gpu.memoryTotal),
                    memory_free=int(gpu.memoryFree),
                    memory_used=int(gpu.memoryUsed),
                    utilization=gpu.load * 100,
                    temperature=gpu.temperature,
                    driver_version=gpu.driver,
                )
                gpus.append({**asdict(gpu_info), "vendor": "NVIDIA"})
        except Exception as e:
            logger.debug("GPUtil error: %s", e)

    if not gpus:
        gpus.extend(_parse_nvidia_smi(scanner))

    return gpus


def _detect_gpus_pynvml() -> list[dict[str, Any]]:
    """Detect NVIDIA GPUs using pynvml."""
    gpus = []
    try:
        nvmlInit()
        device_count = nvmlDeviceGetCount()
        driver_version = nvmlSystemGetDriverVersion()

        for i in range(device_count):
            handle = nvmlDeviceGetHandleByIndex(i)
            name = nvmlDeviceGetName(handle)
            memory = nvmlDeviceGetMemoryInfo(handle)
            utilization = nvmlDeviceGetUtilizationRates(handle)
            temp = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)

            gpu_info = GPUInfo(
                id=i,
                name=name,
                memory_total=int(memory.total / 1024 / 1024),
                memory_free=int(memory.free / 1024 / 1024),
                memory_used=int(memory.used / 1024 / 1024),
                utilization=utilization.gpu,
                temperature=float(temp),
                driver_version=driver_version,
            )
            gpus.append({**asdict(gpu_info), "vendor": "NVIDIA"})

        nvmlShutdown()
    except Exception as e:
        logger.debug("pynvml error: %s", e)

    return gpus


def _parse_nvidia_smi(scanner) -> list[dict[str, Any]]:
    """Parse nvidia-smi output."""
    gpus = []
    try:
        query_cmd = [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,driver_version",
            "--format=csv,noheader,nounits",
        ]
        output = subprocess.check_output(query_cmd, timeout=15).decode()

        for line in output.strip().split("\n"):
            if line:
                parts = line.split(", ")
                if len(parts) >= 8:
                    gpu_info = {
                        "id": int(parts[0]),
                        "name": parts[1],
                        "memory_total": int(parts[2]),
                        "memory_used": int(parts[3]),
                        "memory_free": int(parts[4]),
                        "utilization": float(parts[5]),
                        "temperature": float(parts[6]) if parts[6] != "N/A" else None,
                        "driver_version": parts[7],
                        "vendor": "NVIDIA",
                    }

                    cuda_info = _detect_cuda_info(scanner)
                    if cuda_info:
                        gpu_info["cuda_version"] = cuda_info.get("version")

                    gpus.append(gpu_info)

    except subprocess.CalledProcessError:
        pass
    except Exception as e:
        logger.debug("nvidia-smi parsing error: %s", e)

    return gpus


def _detect_amd_gpus(scanner) -> list[dict[str, Any]]:
    """Detect AMD GPUs."""
    gpus = []

    output = scanner._check_output(["rocm-smi", "--showallinfo"])
    if output and "GPU" in output:
        gpus.append({"vendor": "AMD", "name": "AMD GPU", "driver": "ROCm"})

    opencl_devices = _get_opencl_devices(scanner)
    for device in opencl_devices:
        if "AMD" in device.get("vendor", ""):
            gpus.append(device)

    return gpus


def _detect_rocm_info(scanner) -> dict[str, Any] | None:
    """Detect ROCm installation and version."""
    rocm_info: dict[str, Any] = {"available": False, "version": None}

    output = scanner._check_output(["rocm-smi", "--showversion"])
    if output:
        version_match = re.search(r"(\d+\.\d+\.\d+)", output)
        if version_match:
            rocm_info["version"] = version_match.group(1)
            rocm_info["available"] = True
            return rocm_info

    version_file = Path("/opt/rocm/.version")
    if version_file.exists():
        content = scanner._safe_read_file(str(version_file))
        if content:
            version_match = re.search(r"(\d+\.\d+\.\d+)", content.strip())
            if version_match:
                rocm_info["version"] = version_match.group(1)
                rocm_info["available"] = True
                return rocm_info

    lib_paths = ["/opt/rocm/lib", "/usr/lib/x86_64-linux-gnu"]
    for lib_dir in lib_paths:
        for match in Path(lib_dir).glob("librocm-core.so*"):
            soname_match = re.search(r"librocm-core\.so\.(\d+\.\d+\.\d+)", str(match))
            if soname_match:
                rocm_info["version"] = soname_match.group(1)
                rocm_info["available"] = True
                return rocm_info

    return rocm_info if rocm_info["available"] else None


def _detect_intel_gpus(scanner) -> list[dict[str, Any]]:
    """Detect Intel GPUs."""
    gpus = []

    if platform.system() == "Linux":
        lsmod = scanner._check_output(["lsmod"])
        if lsmod and "i915" in lsmod:
            gpus.append(
                {
                    "vendor": "Intel",
                    "name": "Intel Integrated Graphics",
                    "driver": "i915",
                }
            )

    return gpus


def _detect_intel_gpu_info(scanner) -> dict[str, Any] | None:
    """Detect Intel GPU driver version."""
    intel_info: dict[str, Any] = {"available": False, "version": None}

    if platform.system() != "Linux":
        return None

    lsmod = scanner._check_output(["lsmod"])
    if not lsmod or "i915" not in lsmod:
        return None

    intel_info["available"] = True

    mod_ver = scanner._safe_read_file("/sys/module/i915/version")
    if mod_ver:
        version_match = re.search(r"(\d+\.\d+\.\d+)", mod_ver.strip())
        if version_match:
            intel_info["version"] = version_match.group(1)
            return intel_info

    lspci = scanner._check_output(["lspci", "-k"])
    if lspci:
        for line in lspci.split("\n"):
            if "VGA" in line or "Display" in line:
                kernel_match = re.search(r"Kernel driver in use: (\S+)", lspci)
                if kernel_match:
                    intel_info["driver"] = kernel_match.group(1)
                continue

    for drm_path in Path("/sys/class/drm").glob("card*"):
        if drm_path.is_dir():
            vendor = scanner._safe_read_file(str(drm_path / "device/vendor"))
            if vendor and "0x8086" in vendor.strip():
                dev_id = scanner._safe_read_file(str(drm_path / "device/device"))
                if dev_id:
                    intel_info["device_id"] = dev_id.strip()

    return intel_info


def _detect_cuda_info(scanner) -> dict[str, Any] | None:
    """Detect CUDA installation and version."""
    cuda_info: dict[str, Any] = {}

    if HAS_PYNVML:
        try:
            nvmlInit()
            cuda_driver = nvmlSystemGetCudaDriverVersion()
            nvmlShutdown()
            if cuda_driver:
                cuda_info["version"] = f"{cuda_driver // 100}.{cuda_driver % 100}"
                cuda_info["runtime_version"] = cuda_info["version"]
        except Exception as e:
            logger.debug("pynvml CUDA detection failed: %s", e)

    if not cuda_info.get("version"):
        nvcc_output = scanner._check_output(["nvcc", "--version"])
        if nvcc_output:
            version_match = re.search(r"release (\d+\.\d+)", nvcc_output)
            if version_match:
                cuda_info["version"] = version_match.group(1)
                cuda_info["nvcc_path"] = shutil.which("nvcc")

    if not cuda_info.get("version"):
        smi_output = scanner._check_output(["nvidia-smi"])
        if smi_output:
            cuda_match = re.search(r"CUDA Version:\s*(\d+\.\d+)", smi_output)
            if cuda_match:
                cuda_info["version"] = cuda_match.group(1)
                cuda_info["runtime_version"] = cuda_match.group(1)

    cudnn_info = _detect_cudnn_version(scanner)
    if cudnn_info:
        cuda_info["cudnn"] = cudnn_info

    cuda_paths = [
        "/usr/local/cuda",
        "/usr/local/cuda-*",
        "C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\*",
    ]

    for pattern in cuda_paths:
        for path in Path("/").glob(pattern.lstrip("/")):
            if path.exists():
                cuda_info["cuda_path"] = str(path)
                break

    return cuda_info if cuda_info else None


def _detect_cudnn_version(scanner) -> dict[str, str] | None:
    """Detect cuDNN version."""
    cudnn_info = {}

    header_paths = [
        "/usr/local/cuda/include/cudnn_version.h",
        "/usr/include/cudnn_version.h",
        "/usr/local/include/cudnn_version.h",
    ]

    for header_path in header_paths:
        if os.path.exists(header_path):
            content = scanner._safe_read_file(header_path)
            if content:
                major = re.search(r"#define CUDNN_MAJOR (\d+)", content)
                minor = re.search(r"#define CUDNN_MINOR (\d+)", content)
                patch = re.search(r"#define CUDNN_PATCHLEVEL (\d+)", content)
                if major and minor and patch:
                    cudnn_info["version"] = f"{major.group(1)}.{minor.group(1)}.{patch.group(1)}"
                    cudnn_info["header_path"] = header_path
                    return cudnn_info

    if platform.system() == "Linux":
        output = scanner._check_output(["ldconfig", "-p"])
        if output:
            cudnn_match = re.search(r"libcudnn\.so\.(\d+)", output)
            if cudnn_match:
                cudnn_info["version"] = cudnn_match.group(1)
                return cudnn_info

    return None


def _detect_opencl_info(scanner) -> dict[str, Any] | None:
    """Detect OpenCL support."""
    opencl_info: dict[str, Any] = {
        "available": False,
        "version": None,
        "devices": [],
    }

    output = scanner._check_output(["clinfo"])
    if output and "Number of platforms" in output:
        opencl_info["available"] = True
        version_match = re.search(r"OpenCL (\d+\.\d+)", output)
        if version_match:
            opencl_info["version"] = version_match.group(1)
        device_match = re.search(r"Number of devices\s+(\d+)", output)
        if device_match:
            opencl_info["device_count"] = int(device_match.group(1))

    return opencl_info if opencl_info["available"] else None


def _get_opencl_devices(scanner) -> list[dict[str, Any]]:
    """Get OpenCL device list by parsing clinfo output."""
    devices = []
    result = scanner._run_subprocess(["clinfo", "--raw"], timeout=5)
    if result and result.returncode == 0:
        for line in result.stdout.split("\n"):
            if "=" in line:
                key, val = line.split("=", 1)
                devices.append({"key": key.strip(), "value": val.strip()})
    return devices


def _detect_vulkan_info(scanner) -> dict[str, Any] | None:
    """Detect Vulkan support."""
    vulkan_info: dict[str, Any] = {"available": False, "version": None}

    output = scanner._check_output(["vulkaninfo", "--summary"])
    if output and "Vulkan Instance Version" in output:
        vulkan_info["available"] = True
        version_match = re.search(r"Vulkan Instance Version:\s*(\d+\.\d+\.\d+)", output)
        if version_match:
            vulkan_info["version"] = version_match.group(1)

    return vulkan_info if vulkan_info["available"] else None


def _detect_metal_info(scanner) -> dict[str, Any] | None:
    """Detect Metal support (macOS)."""
    metal_info: dict[str, Any] = {"available": False, "version": None}

    framework_path = "/System/Library/Frameworks/Metal.framework"
    if os.path.exists(framework_path):
        metal_info["available"] = True
        output = scanner._check_output(["system_profiler", "SPDisplaysDataType", "-json"])
        if output:
            try:
                parsed = loads(output)
                displays = parsed.get("SPDisplaysDataType", [])
                if isinstance(displays, list):
                    for display in displays:
                        if isinstance(display, dict):
                            metal_ver = display.get("spdisplays_metal_version")
                            if metal_ver:
                                version_match = re.search(
                                    r"Metal\s*(\d+(?:\.\d+)?)", str(metal_ver)
                                )
                                if version_match:
                                    metal_info["version"] = version_match.group(1)
                                    break
            except JSONDecodeError as e:
                logger.debug("system_profiler JSON parse failed: %s", e)

    return metal_info if metal_info["available"] else None
