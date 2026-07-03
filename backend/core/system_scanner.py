"""Module docstring."""

# system_scanner.py
import asyncio
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.core.scanner_models import (
    ContainerType,
    CPUInfo,
    DiskInfo,
    GPUInfo,
    MemoryInfo,
    NetworkInterface,
    OSType,
    PackageInfo,
    RuntimeInfo,
)
from backend.core.utils import hash_system_info

# Third-party imports with fallback
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

try:
    import psutil

    HAS_PSUTIL = True
except Exception:
    HAS_PSUTIL = False

try:
    import pkg_resources

    HAS_PKG_RESOURCES = True
except Exception:
    HAS_PKG_RESOURCES = False

try:
    import distro

    HAS_DISTRO = True
except Exception:
    HAS_DISTRO = False

logger = logging.getLogger(__name__)


class SystemScanner:
    """System Scanner functionality."""

    def __init__(
        self,
        cache_ttl: int = 300,
        enable_cache: bool = True,
        parallel_scan: bool = True,
        scan_network: bool = True,
        scan_packages: bool = True,
        deep_scan: bool = False,
    ):
        """Initialize."""
        self.cache_ttl = cache_ttl
        self.enable_cache = enable_cache
        self.parallel_scan = parallel_scan
        self.scan_network = scan_network
        self.scan_packages = scan_packages
        self.deep_scan = deep_scan
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._executor = ThreadPoolExecutor(max_workers=10)
        self.system_info: dict[str, Any] = {}

    async def __aenter__(self):
        """Aenter."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Aexit."""
        self._executor.shutdown(wait=True)

    def _get_cache_key(self, category: str) -> str:
        """Generate cache key based on system configuration."""
        # Get basic system identifiers for cache key
        system_identifiers = {
            "system": platform.system(),
            "node": platform.node(),
            "release": platform.release(),
            "machine": platform.machine(),
            "category": category,
        }

        # Use hash_system_info to create a consistent cache key
        return f"system_scan_{hash_system_info(system_identifiers)}"

    def _get_cached(self, key: str) -> Any | None:
        """Get cached data if available."""
        if not self.enable_cache:
            return None

        if key in self._cache:
            data, timestamp = self._cache[key]
            if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                return data
            del self._cache[key]
        return None

    def _set_cache(self, key: str, data: Any):
        """Set cache data."""
        if self.enable_cache:
            self._cache[key] = (data, datetime.now())

    async def scan_all(self, categories: list[str] | None = None) -> dict[str, Any]:
        """Perform complete or selective system scan."""
        start_time = datetime.now()

        # Define scan categories
        all_categories = {
            "platform": self.detect_platform_info,
            "cpu": self.detect_cpu_info,
            "memory": self.detect_memory_info,
            "gpu": self.detect_gpu_info,
            "disk": self.detect_disk_info,
            "network": self.detect_network_info if self.scan_network else None,
            "container": self.detect_container_info,
            "runtime_versions": self.detect_runtime_versions,
            "installed_packages": self.detect_installed_packages if self.scan_packages else None,
            "security": self.detect_security_info if self.deep_scan else None,
            "performance": self.get_performance_metrics,
            "capabilities": self.detect_system_capabilities,
        }

        # Filter categories if specified
        if categories:
            scan_categories = {
                k: v for k, v in all_categories.items() if k in categories and v is not None
            }
        else:
            scan_categories = {k: v for k, v in all_categories.items() if v is not None}

        # Perform scans
        if self.parallel_scan:
            # Parallel scanning
            tasks = []
            for category, scanner_func in scan_categories.items():
                tasks.append(self._scan_category_async(category, scanner_func))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for category, result in zip(scan_categories.keys(), results):
                if isinstance(result, Exception):
                    logger.error(f"Error scanning {category}: {result}")
                    self.system_info[category] = {"error": str(result)}
                else:
                    self.system_info[category] = result
        else:
            # Sequential scanning
            for category, scanner_func in scan_categories.items():
                try:
                    result = await self._scan_category_async(category, scanner_func)
                    self.system_info[category] = result
                except Exception as e:
                    logger.error(f"Error scanning {category}: {e}")
                    self.system_info[category] = {"error": str(e)}

        # Add metadata
        self.system_info["scan_metadata"] = {
            "timestamp": datetime.now().isoformat(),
            "duration": (datetime.now() - start_time).total_seconds(),
            "categories_scanned": list(scan_categories.keys()),
            "scanner_version": "2.0.0",
            "system_hash": hash_system_info(self.system_info),
        }

        return self.system_info

    async def _scan_category_async(self, category: str, scanner_func) -> Any:
        """Run scanner function asynchronously."""
        # Check cache first
        cache_key = self._get_cache_key(category)
        cached_data = self._get_cached(cache_key)
        if cached_data is not None:
            return cached_data

        # Run scanner
        if asyncio.iscoroutinefunction(scanner_func):
            result = await scanner_func()
        else:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(self._executor, scanner_func)

        # Cache result
        self._set_cache(cache_key, result)

        return result

    def detect_platform_info(self) -> dict[str, Any]:
        """Detect comprehensive platform information."""
        info: dict[str, Any] = {
            "system": platform.system(),
            "node": platform.node(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "platform": platform.platform(),
            "python_build": platform.python_build(),
            "python_compiler": platform.python_compiler(),
            "architecture": platform.architecture(),
            "os_type": self._detect_os_type().value,
            "hostname": socket.gethostname(),
            "fqdn": socket.getfqdn(),
            "boot_time": None,
        }

        # Boot time
        if HAS_PSUTIL:
            info["boot_time"] = datetime.fromtimestamp(psutil.boot_time()).isoformat()

        # Linux-specific info
        if info["system"] == "Linux":
            info["distribution"] = self._get_linux_distribution()
            info["kernel_version"] = self._get_kernel_version()
            info["libc_version"] = self._get_libc_version()

        # Windows-specific info
        elif info["system"] == "Windows":
            info["windows_edition"] = self._get_windows_edition()
            info["windows_version"] = self._get_windows_version()

        # macOS-specific info
        elif info["system"] == "Darwin":
            info["macos_version"] = self._get_macos_version()

        return info

    def _detect_os_type(self) -> OSType:
        """Detect OS type."""
        system = platform.system()
        if system == "Windows":
            return OSType.WINDOWS
        if system == "Linux":
            return OSType.LINUX
        if system == "Darwin":
            return OSType.MACOS
        if "BSD" in system:
            return OSType.BSD
        return OSType.UNKNOWN

    def _get_linux_distribution(self) -> dict[str, str]:
        """Get detailed Linux distribution info."""
        dist_info = {}

        # Try distro library first
        if HAS_DISTRO:
            dist_info = {
                "name": distro.name(),
                "version": distro.version(),
                "codename": distro.codename(),
                "like": distro.like(),
                "id": distro.id(),
            }

        # Fallback to os-release
        elif os.path.exists("/etc/os-release"):
            try:
                with open("/etc/os-release") as f:
                    for line in f:
                        if "=" in line:
                            key, value = line.strip().split("=", 1)
                            dist_info[key.lower()] = value.strip('"')
            except Exception:
                pass

        # Additional detection for specific distros
        if os.path.exists("/etc/redhat-release"):
            try:
                with open("/etc/redhat-release") as f:
                    dist_info["redhat_release"] = f.read().strip()
            except Exception:
                pass

        return dist_info

    def _get_kernel_version(self) -> str | None:
        """Get Linux kernel version."""
        try:
            return subprocess.check_output(["uname", "-r"]).decode().strip()
        except Exception:
            return None

    def _get_libc_version(self) -> dict[str, str] | None:
        """Get libc version."""
        try:
            ldd_output = subprocess.check_output(["ldd", "--version"]).decode()
            version_match = re.search(r"(\d+\.\d+)", ldd_output)
            if version_match:
                return {
                    "version": version_match.group(1),
                    "type": "glibc" if "GNU" in ldd_output else "unknown",
                }
            return None
        except Exception:
            return None

    def _get_windows_edition(self) -> str | None:
        """Get Windows edition."""
        try:
            import winreg  # type: ignore[import-not-found]

            key = winreg.OpenKey(  # type: ignore[attr-defined]
                winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            )
            edition, _ = winreg.QueryValueEx(key, "EditionID")  # type: ignore[attr-defined]
            winreg.CloseKey(key)  # type: ignore[attr-defined]
            return edition
        except Exception:
            return None

    def _get_windows_version(self) -> dict[str, str] | None:
        """Get detailed Windows version."""
        try:
            output = subprocess.check_output(
                ["wmic", "os", "get", "Caption,Version,BuildNumber", "/value"]
            ).decode()
            info = {}
            for line in output.strip().split("\n"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    if key and value:
                        info[key.lower()] = value.strip()
            return info
        except Exception:
            return None

    def _get_macos_version(self) -> dict[str, str] | None:
        """Get macOS version details."""
        try:
            output = subprocess.check_output(["sw_vers"]).decode()
            info = {}
            for line in output.strip().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    info[key.strip().lower().replace(" ", "_")] = value.strip()
            return info
        except Exception:
            return None

    def detect_cpu_info(self) -> dict[str, Any]:
        """Detect comprehensive CPU information."""
        cpu_data: dict[str, Any] = {}

        # Basic info from platform
        cpu_data["processor"] = platform.processor()
        cpu_data["architecture"] = platform.machine()

        # Detailed info from cpuinfo
        try:
            from cpuinfo import get_cpu_info as _get_cpu_info

            info = _get_cpu_info()
            cpu_info = CPUInfo(
                brand=info.get("brand_raw", "Unknown"),
                arch=info.get("arch", platform.machine()),
                bits=info.get("bits", 64),
                count_physical=info.get(
                    "count", psutil.cpu_count(logical=False) if HAS_PSUTIL else 1
                ),
                count_logical=psutil.cpu_count(logical=True)
                if HAS_PSUTIL
                else info.get("count", 1),
                features=info.get("flags", []),
            )

            if "l1_instruction_cache_size" in info:
                cpu_info.cache_sizes["l1i"] = info["l1_instruction_cache_size"]
            if "l1_data_cache_size" in info:
                cpu_info.cache_sizes["l1d"] = info["l1_data_cache_size"]
            if "l2_cache_size" in info:
                cpu_info.cache_sizes["l2"] = info["l2_cache_size"]
            if "l3_cache_size" in info:
                cpu_info.cache_sizes["l3"] = info["l3_cache_size"]

            cpu_data.update(asdict(cpu_info))
        except Exception as e:
            logger.error(f"cpuinfo error: {e}")
            cpu_data.setdefault("brand", "Unknown")
            cpu_data.setdefault("arch", platform.machine())
            cpu_data.setdefault("bits", "64")
            cpu_data.setdefault(
                "count_logical",
                str(psutil.cpu_count(logical=True) if HAS_PSUTIL else 1),
            )
            cpu_data.setdefault(
                "count_physical",
                str(psutil.cpu_count(logical=False) if HAS_PSUTIL else 1),
            )

        # Additional info from psutil
        if HAS_PSUTIL:
            try:
                # CPU frequency
                freq = psutil.cpu_freq()
                if freq:
                    cpu_data["max_frequency"] = freq.max
                    cpu_data["min_frequency"] = freq.min
                    cpu_data["current_frequency"] = freq.current

                # CPU stats
                cpu_data["stats"] = {
                    "ctx_switches": psutil.cpu_stats().ctx_switches,
                    "interrupts": psutil.cpu_stats().interrupts,
                    "soft_interrupts": psutil.cpu_stats().soft_interrupts,
                    "syscalls": getattr(psutil.cpu_stats(), "syscalls", None),
                }

                # CPU times
                cpu_times = psutil.cpu_times()
                cpu_data["times"] = {
                    "user": cpu_times.user,
                    "system": cpu_times.system,
                    "idle": cpu_times.idle,
                    "iowait": getattr(cpu_times, "iowait", None),
                }

                # Per-CPU usage
                cpu_data["usage_per_cpu"] = psutil.cpu_percent(percpu=True, interval=0.1)
                cpu_data["usage_total"] = psutil.cpu_percent(interval=0.1)

            except Exception as e:
                logger.error(f"psutil CPU error: {e}")

        # Temperature (if available)
        cpu_data["temperature"] = self._get_cpu_temperature()

        # Virtualization capabilities
        features = cpu_data.get("features", [])
        assert isinstance(features, list)
        cpu_data["virtualization"] = self._detect_virtualization_support(features)

        return cpu_data

    def _get_cpu_temperature(self) -> float | None:
        """Get CPU temperature."""
        if not HAS_PSUTIL:
            return None

        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # Try different sensor names
                for name in ["coretemp", "cpu_thermal", "k10temp", "zenpower"]:
                    if name in temps:
                        return temps[name][0].current
        except Exception:
            pass

        # Platform-specific methods
        if platform.system() == "Darwin":
            # macOS temperature reading (requires osx-cpu-temp)
            try:
                output = subprocess.check_output(["osx-cpu-temp"]).decode()
                temp_match = re.search(r"(\d+\.\d+)", output)
                if temp_match:
                    return float(temp_match.group(1))
            except Exception:
                pass

        return None

    def _detect_virtualization_support(self, cpu_features: list[str]) -> dict[str, bool]:
        """Detect CPU virtualization support."""
        virt_support = {
            "vmx": False,  # Intel VT-x
            "svm": False,  # AMD-V
            "hypervisor": False,
        }

        feature_set = set(cpu_features)
        virt_support["vmx"] = "vmx" in feature_set
        virt_support["svm"] = "svm" in feature_set
        virt_support["hypervisor"] = "hypervisor" in feature_set

        return virt_support

    def detect_memory_info(self) -> dict[str, Any]:
        """Detect memory information."""
        mem_data = {}

        if HAS_PSUTIL:
            # Virtual memory
            vmem = psutil.virtual_memory()
            mem_info = MemoryInfo(
                total=vmem.total,
                available=vmem.available,
                used=vmem.used,
                free=vmem.free,
                percent=vmem.percent,
                swap_total=0,
                swap_used=0,
                swap_free=0,
                swap_percent=0.0,
            )

            # Swap memory
            try:
                swap = psutil.swap_memory()
                mem_info.swap_total = swap.total
                mem_info.swap_used = swap.used
                mem_info.swap_free = swap.free
                mem_info.swap_percent = swap.percent
            except Exception:
                pass

            mem_data = asdict(mem_info)

            # Additional memory stats
            mem_data["buffers"] = getattr(vmem, "buffers", 0)
            mem_data["cached"] = getattr(vmem, "cached", 0)
            mem_data["shared"] = getattr(vmem, "shared", 0)

        else:
            # Fallback for basic memory info
            try:
                if platform.system() == "Linux":
                    with open("/proc/meminfo") as f:
                        for line in f:
                            if line.startswith("MemTotal:"):
                                mem_data["total"] = int(line.split()[1]) * 1024
                            elif line.startswith("MemAvailable:"):
                                mem_data["available"] = int(line.split()[1]) * 1024
            except Exception:
                pass

        return mem_data

    def detect_gpu_info(self) -> dict[str, Any]:
        """Detect comprehensive GPU information."""
        gpu_data: dict[str, Any] = {
            "available": False,
            "devices": [],
            "cuda": self._detect_cuda_info(),
            "opencl": self._detect_opencl_info(),
            "vulkan": self._detect_vulkan_info(),
            "metal": self._detect_metal_info() if platform.system() == "Darwin" else None,
        }

        # NVIDIA GPUs
        nvidia_gpus = self._detect_nvidia_gpus()
        gpu_data["devices"].extend(nvidia_gpus)

        # AMD GPUs
        amd_gpus = self._detect_amd_gpus()
        gpu_data["devices"].extend(amd_gpus)

        # Intel GPUs
        intel_gpus = self._detect_intel_gpus()
        gpu_data["devices"].extend(intel_gpus)

        if gpu_data["devices"]:
            gpu_data["available"] = True

        return gpu_data

    def _detect_gpus_pynvml(self) -> list[dict[str, Any]]:
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
            logger.debug(f"pynvml error: {e}")

        return gpus

    def _detect_nvidia_gpus(self) -> list[dict[str, Any]]:
        """Detect NVIDIA GPUs."""
        gpus = []

        # Try pynvml first
        if HAS_PYNVML:
            gpus.extend(self._detect_gpus_pynvml())

        # Then GPUtil
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
                logger.debug(f"GPUtil error: {e}")

        # Fallback to nvidia-smi
        if not gpus:
            gpus.extend(self._parse_nvidia_smi())

        return gpus

    def _parse_nvidia_smi(self) -> list[dict[str, Any]]:
        """Parse nvidia-smi output."""
        gpus = []
        try:
            # Query specific fields
            query_cmd = [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,driver_version",
                "--format=csv,noheader,nounits",
            ]
            output = subprocess.check_output(query_cmd).decode()

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

                        # Get CUDA version
                        cuda_info = self._detect_cuda_info()
                        if cuda_info:
                            gpu_info["cuda_version"] = cuda_info.get("version")

                        gpus.append(gpu_info)

        except subprocess.CalledProcessError:
            pass
        except Exception as e:
            logger.debug(f"nvidia-smi parsing error: {e}")

        return gpus

    def _detect_amd_gpus(self) -> list[dict[str, Any]]:
        """Detect AMD GPUs."""
        gpus = []

        # Try rocm-smi
        try:
            output = subprocess.check_output(["rocm-smi", "--showallinfo"]).decode()
            # Parse rocm-smi output (simplified)
            # In production, implement proper parsing
            if "GPU" in output:
                gpus.append({"vendor": "AMD", "name": "AMD GPU", "driver": "ROCm"})
        except Exception:
            pass

        # Try clinfo for OpenCL devices
        opencl_devices = self._get_opencl_devices()
        for device in opencl_devices:
            if "AMD" in device.get("vendor", ""):
                gpus.append(device)

        return gpus

    def _detect_intel_gpus(self) -> list[dict[str, Any]]:
        """Detect Intel GPUs."""
        gpus = []

        # Check for Intel integrated graphics
        if platform.system() == "Linux":
            try:
                # Check if i915 driver is loaded
                lsmod = subprocess.check_output(["lsmod"]).decode()
                if "i915" in lsmod:
                    gpus.append(
                        {
                            "vendor": "Intel",
                            "name": "Intel Integrated Graphics",
                            "driver": "i915",
                        }
                    )
            except Exception:
                pass

        return gpus

    def _detect_cuda_info(self) -> dict[str, Any] | None:
        """Detect CUDA installation and version."""
        cuda_info: dict[str, Any] = {}

        # Try pynvml first for CUDA driver version
        if HAS_PYNVML:
            try:
                nvmlInit()
                cuda_driver = nvmlSystemGetCudaDriverVersion()
                nvmlShutdown()
                if cuda_driver:
                    cuda_info["version"] = f"{cuda_driver // 100}.{cuda_driver % 100}"
                    cuda_info["runtime_version"] = cuda_info["version"]
            except Exception:
                pass

        # Fallback to nvcc
        if not cuda_info.get("version"):
            try:
                nvcc_output = subprocess.check_output(["nvcc", "--version"]).decode()
                version_match = re.search(r"release (\d+\.\d+)", nvcc_output)
                if version_match:
                    cuda_info["version"] = version_match.group(1)
                    cuda_info["nvcc_path"] = shutil.which("nvcc")
            except Exception:
                pass

        # Fallback to nvidia-smi for CUDA version
        if not cuda_info.get("version"):
            try:
                smi_output = subprocess.check_output(["nvidia-smi"]).decode()
                cuda_match = re.search(r"CUDA Version:\s*(\d+\.\d+)", smi_output)
                if cuda_match:
                    cuda_info["version"] = cuda_match.group(1)
                    cuda_info["runtime_version"] = cuda_match.group(1)
            except Exception:
                pass

        # Check for cuDNN
        cudnn_info = self._detect_cudnn_version()
        if cudnn_info:
            cuda_info["cudnn"] = cudnn_info

        # Check CUDA paths
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

    def _detect_cudnn_version(self) -> dict[str, str] | None:
        """Detect cuDNN version."""
        cudnn_info = {}

        # Check header file
        header_paths = [
            "/usr/local/cuda/include/cudnn_version.h",
            "/usr/include/cudnn_version.h",
            "/usr/local/include/cudnn_version.h",
        ]

        for header_path in header_paths:
            if os.path.exists(header_path):
                try:
                    with open(header_path) as f:
                        content = f.read()
                        major = re.search(r"#define CUDNN_MAJOR (\d+)", content)
                        minor = re.search(r"#define CUDNN_MINOR (\d+)", content)
                        patch = re.search(r"#define CUDNN_PATCHLEVEL (\d+)", content)

                        if major and minor and patch:
                            cudnn_info["version"] = (
                                f"{major.group(1)}.{minor.group(1)}.{patch.group(1)}"
                            )
                            cudnn_info["header_path"] = header_path
                            return cudnn_info
                except Exception:
                    pass

        # Try ldconfig
        if platform.system() == "Linux":
            try:
                output = subprocess.check_output(["ldconfig", "-p"]).decode()
                cudnn_match = re.search(r"libcudnn\.so\.(\d+)", output)
                if cudnn_match:
                    cudnn_info["version"] = cudnn_match.group(1)
                    return cudnn_info
            except Exception:
                pass

        return None

    def _detect_opencl_info(self) -> dict[str, Any] | None:
        """Detect OpenCL support."""
        opencl_info: dict[str, Any] = {
            "available": False,
            "version": None,
            "devices": [],
        }

        try:
            # Try clinfo
            output = subprocess.check_output(["clinfo"]).decode()
            if "Number of platforms" in output:
                opencl_info["available"] = True

                # Extract version
                version_match = re.search(r"OpenCL (\d+\.\d+)", output)
                if version_match:
                    opencl_info["version"] = version_match.group(1)

                # Get device count
                device_match = re.search(r"Number of devices\s+(\d+)", output)
                if device_match:
                    opencl_info["device_count"] = int(device_match.group(1))

        except Exception:
            pass

        return opencl_info if opencl_info["available"] else None

    def _get_opencl_devices(self) -> list[dict[str, Any]]:
        """Get OpenCL device list by parsing clinfo output."""
        devices = []
        try:
            import subprocess

            result = subprocess.run(
                ["clinfo", "--raw"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "=" in line:
                        key, val = line.split("=", 1)
                        devices.append({"key": key.strip(), "value": val.strip()})
        except Exception:
            pass
        return devices

    def _detect_vulkan_info(self) -> dict[str, Any] | None:
        """Detect Vulkan support."""
        vulkan_info: dict[str, Any] = {"available": False, "version": None}

        try:
            # Try vulkaninfo
            output = subprocess.check_output(["vulkaninfo", "--summary"]).decode()
            if "Vulkan Instance Version" in output:
                vulkan_info["available"] = True

                # Extract version
                version_match = re.search(r"Vulkan Instance Version:\s*(\d+\.\d+\.\d+)", output)
                if version_match:
                    vulkan_info["version"] = version_match.group(1)

        except Exception:
            pass

        return vulkan_info if vulkan_info["available"] else None

    def _detect_metal_info(self) -> dict[str, Any] | None:
        """Detect Metal support (macOS)."""
        metal_info = {"available": False}

        try:
            # Check if Metal framework exists
            framework_path = "/System/Library/Frameworks/Metal.framework"
            if os.path.exists(framework_path):
                metal_info["available"] = True

                # Get GPU info via system_profiler
                output = subprocess.check_output(
                    ["system_profiler", "SPDisplaysDataType", "-json"]
                ).decode()

                json.loads(output)
                # Parse GPU info from system_profiler
                # Implementation depends on output structure

        except Exception:
            pass

        return metal_info if metal_info["available"] else None

    def detect_disk_info(self) -> dict[str, Any]:
        """Detect disk information."""
        disk_data: dict[str, Any] = {"disks": [], "partitions": [], "io_counters": {}}

        if HAS_PSUTIL:
            # Get disk partitions
            partitions = psutil.disk_partitions(all=False)
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_info = DiskInfo(
                        device=partition.device,
                        mountpoint=partition.mountpoint,
                        fstype=partition.fstype,
                        total=usage.total,
                        used=usage.used,
                        free=usage.free,
                        percent=usage.percent,
                    )
                    disk_data["partitions"].append(asdict(disk_info))
                except Exception:
                    pass

            # Get disk I/O counters
            try:
                io_counters = psutil.disk_io_counters(perdisk=True)
                for disk, counters in io_counters.items():
                    disk_data["io_counters"][disk] = {
                        "read_count": counters.read_count,
                        "write_count": counters.write_count,
                        "read_bytes": counters.read_bytes,
                        "write_bytes": counters.write_bytes,
                        "read_time": counters.read_time,
                        "write_time": counters.write_time,
                    }
            except Exception:
                pass

        # Get physical disk info
        disk_data["physical_disks"] = self._detect_physical_disks()

        return disk_data

    def _detect_physical_disks(self) -> list[dict[str, Any]]:
        """Detect physical disk information."""
        disks = []

        if platform.system() == "Linux":
            # Parse lsblk output
            try:
                output = subprocess.check_output(
                    ["lsblk", "-J", "-b", "-o", "NAME,TYPE,SIZE,MODEL,SERIAL,ROTA"]
                ).decode()

                data = json.loads(output)
                for device in data.get("blockdevices", []):
                    if device.get("type") == "disk":
                        disk_info = {
                            "name": device.get("name"),
                            "size": device.get("size"),
                            "model": device.get("model"),
                            "serial": device.get("serial"),
                            "rotational": device.get("rota") == "1",
                        }
                        disks.append(disk_info)
            except Exception:
                pass

        elif platform.system() == "Windows":
            # Use wmic
            try:
                output = subprocess.check_output(
                    [
                        "wmic",
                        "diskdrive",
                        "get",
                        "Name,Size,Model,SerialNumber",
                        "/format:csv",
                    ]
                ).decode()

                lines = output.strip().split("\n")[2:]  # Skip headers
                for line in lines:
                    if line:
                        parts = line.split(",")
                        if len(parts) >= 5:
                            disks.append(
                                {
                                    "name": parts[2],
                                    "size": int(parts[4]) if parts[4] else 0,
                                    "model": parts[1],
                                    "serial": parts[3],
                                }
                            )
            except Exception:
                pass

        elif platform.system() == "Darwin":
            # Use diskutil
            try:
                output = subprocess.check_output(["diskutil", "list"]).decode()
                # Parse diskutil output
                # Implementation depends on output format
            except Exception:
                pass

        return disks

    def detect_network_info(self) -> dict[str, Any]:
        """Detect network information."""
        network_data: dict[str, Any] = {
            "interfaces": [],
            "connections": [],
            "stats": {},
        }

        if HAS_PSUTIL:
            # Network interfaces
            interfaces = psutil.net_if_addrs()
            for iface_name, addrs in interfaces.items():
                iface_info = NetworkInterface(name=iface_name, addresses=[], is_up=True)

                for addr in addrs:
                    addr_info = {
                        "family": str(addr.family),
                        "address": addr.address,
                        "netmask": addr.netmask,
                        "broadcast": addr.broadcast,
                    }
                    iface_info.addresses.append(addr_info)

                # Get interface stats
                if_stats = psutil.net_if_stats()
                if iface_name in if_stats:
                    stats = if_stats[iface_name]
                    iface_info.is_up = stats.isup
                    iface_info.speed = stats.speed
                    iface_info.mtu = stats.mtu

                network_data["interfaces"].append(asdict(iface_info))

            # Network connections
            try:
                connections = psutil.net_connections(kind="inet")
                for conn in connections[:100]:  # Limit to first 100
                    conn_info = {
                        "fd": conn.fd,
                        "family": str(conn.family),
                        "type": str(conn.type),
                        "laddr": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else None,
                        "raddr": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else None,
                        "status": conn.status,
                        "pid": conn.pid,
                    }
                    network_data["connections"].append(conn_info)
            except Exception:
                pass

            # Network I/O stats
            try:
                io_counters = psutil.net_io_counters(pernic=False)
                network_data["stats"] = {
                    "bytes_sent": io_counters.bytes_sent,
                    "bytes_recv": io_counters.bytes_recv,
                    "packets_sent": io_counters.packets_sent,
                    "packets_recv": io_counters.packets_recv,
                    "errin": io_counters.errin,
                    "errout": io_counters.errout,
                    "dropin": io_counters.dropin,
                    "dropout": io_counters.dropout,
                }
            except Exception:
                pass

        # Additional network info
        network_data["hostname"] = socket.gethostname()
        network_data["fqdn"] = socket.getfqdn()

        # DNS servers
        network_data["dns_servers"] = self._get_dns_servers()

        # Default gateway
        network_data["default_gateway"] = self._get_default_gateway()

        return network_data

    def _get_dns_servers(self) -> list[str]:
        """Get DNS server addresses."""
        dns_servers = []

        if platform.system() == "Linux":
            try:
                with open("/etc/resolv.conf") as f:
                    for line in f:
                        if line.startswith("nameserver"):
                            dns_servers.append(line.split()[1])
            except Exception:
                pass

        elif platform.system() == "Windows":
            try:
                output = subprocess.check_output(
                    ["netsh", "interface", "ip", "show", "dns"]
                ).decode()
                # Parse netsh output
                for line in output.split("\n"):
                    if "DNS" in line and ":" in line:
                        parts = line.split(":")
                        if len(parts) > 1:
                            dns = parts[1].strip()
                            if dns and dns != "None":
                                dns_servers.append(dns)
            except Exception:
                pass

        elif platform.system() == "Darwin":
            try:
                output = subprocess.check_output(["scutil", "--dns"]).decode()
                # Parse scutil output
                for line in output.split("\n"):
                    if "nameserver" in line:
                        parts = line.split(":")
                        if len(parts) > 1:
                            dns_servers.append(parts[1].strip())
            except Exception:
                pass

        return list(set(dns_servers))  # Remove duplicates

    def _get_default_gateway(self) -> str | None:
        """Get default gateway."""
        if platform.system() == "Linux":
            try:
                output = subprocess.check_output(["ip", "route", "show", "default"]).decode()
                match = re.search(r"default via (\S+)", output)
                if match:
                    return match.group(1)
            except Exception:
                pass

        elif platform.system() == "Windows":
            try:
                output = subprocess.check_output(["route", "print", "0.0.0.0"]).decode()
                # Parse route output
                lines = output.split("\n")
                for line in lines:
                    if "0.0.0.0" in line and "Network" not in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            return parts[2]
            except Exception:
                pass

        elif platform.system() == "Darwin":
            try:
                output = subprocess.check_output(["route", "-n", "get", "default"]).decode()
                match = re.search(r"gateway: (\S+)", output)
                if match:
                    return match.group(1)
            except Exception:
                pass

        return None

    def detect_container_info(self) -> dict[str, Any]:
        """Detect container/virtualization environment."""
        container_data: dict[str, Any] = {
            "type": ContainerType.BARE_METAL.value,
            "detected": False,
            "details": {},
        }

        # Docker detection
        if self._is_docker():
            container_data["type"] = ContainerType.DOCKER.value
            container_data["detected"] = True
            container_data["details"] = self._get_docker_info()

        # Podman detection
        elif os.path.exists("/run/.containerenv"):
            container_data["type"] = ContainerType.PODMAN.value
            container_data["detected"] = True

        # LXC detection
        elif os.path.exists("/proc/1/environ"):
            try:
                with open("/proc/1/environ", "rb") as f:
                    if b"container=lxc" in f.read():
                        container_data["type"] = ContainerType.LXC.value
                        container_data["detected"] = True
            except Exception:
                pass

        # WSL detection
        if platform.system() == "Linux":
            try:
                with open("/proc/version") as f:
                    if "Microsoft" in f.read() or "WSL" in f.read():
                        container_data["type"] = ContainerType.WSL.value
                        container_data["detected"] = True
                        container_data["details"]["wsl_version"] = self._get_wsl_version()
            except Exception:
                pass

        # VM detection
        if not container_data["detected"]:
            vm_info = self._detect_vm()
            if vm_info:
                container_data["type"] = ContainerType.VM.value
                container_data["detected"] = True
                container_data["details"] = vm_info

        return container_data

    def _is_docker(self) -> bool:
        """Check if running in Docker."""
        # Check for .dockerenv file
        if os.path.exists("/.dockerenv"):
            return True

        # Check cgroup
        try:
            with open("/proc/self/cgroup") as f:
                return "docker" in f.read()
        except Exception:
            pass

        return False

    def _get_docker_info(self) -> dict[str, Any]:
        """Get Docker container information."""
        info = {}

        # Get container ID
        try:
            with open("/proc/self/cgroup") as f:
                for line in f:
                    if "docker" in line:
                        parts = line.strip().split("/")
                        if len(parts) > 1:
                            info["container_id"] = parts[-1][:12]
                            break
        except Exception:
            pass

        # Get Docker version (if docker command available)
        try:
            output = subprocess.check_output(
                ["docker", "version", "--format", "{{.Server.Version}}"]
            ).decode()
            info["docker_version"] = output.strip()
        except Exception:
            pass

        return info

    def _get_wsl_version(self) -> str | None:
        """Get WSL version."""
        try:
            # Check for WSL 2
            with open("/proc/version") as f:
                content = f.read()
                if "WSL2" in content:
                    return "2"
                if "Microsoft" in content:
                    return "1"
        except Exception:
            pass

        return None

    def _detect_vm(self) -> dict[str, Any] | None:
        """Detect virtual machine environment."""
        vm_info = {}

        # Check DMI info
        if platform.system() == "Linux":
            try:
                # Check systemd-detect-virt
                output = subprocess.check_output(["systemd-detect-virt"]).decode().strip()
                if output and output != "none":
                    vm_info["type"] = output
                    return vm_info
            except Exception:
                pass

            # Check DMI
            try:
                dmi_path = "/sys/devices/virtual/dmi/id/product_name"
                if os.path.exists(dmi_path):
                    with open(dmi_path) as f:
                        product = f.read().strip().lower()
                        if "virtualbox" in product:
                            vm_info["type"] = "virtualbox"
                        elif "vmware" in product:
                            vm_info["type"] = "vmware"
                        elif "kvm" in product:
                            vm_info["type"] = "kvm"
                        elif "xen" in product:
                            vm_info["type"] = "xen"
                        elif "microsoft corporation" in product:
                            vm_info["type"] = "hyper-v"

                        if vm_info:
                            return vm_info
            except Exception:
                pass

        # Check CPU features
        try:
            from cpuinfo import get_cpu_info as _get_cpu_info

            info = _get_cpu_info()
            flags = info.get("flags", [])
            if "hypervisor" in flags:
                vm_info["detected_by"] = "cpu_flags"
                return vm_info
        except Exception:
            pass

        return vm_info if vm_info else None

    def detect_runtime_versions(self) -> dict[str, Any]:
        """Detect runtime environment versions."""
        runtimes = {}

        # Python
        runtimes["python"] = RuntimeInfo(
            name="Python",
            version=platform.python_version(),
            path=sys.executable,
            implementation=platform.python_implementation(),
            architecture=platform.architecture()[0],
            additional_info={
                "compiler": platform.python_compiler(),
                "build": platform.python_build(),
            },
        )

        # Node.js
        node_info = self._detect_nodejs()
        if node_info:
            runtimes["nodejs"] = node_info

        # Java
        java_info = self._detect_java()
        if java_info:
            runtimes["java"] = java_info

        # .NET
        dotnet_info = self._detect_dotnet()
        if dotnet_info:
            runtimes["dotnet"] = dotnet_info

        # Ruby
        ruby_info = self._detect_ruby()
        if ruby_info:
            runtimes["ruby"] = ruby_info

        # Go
        go_info = self._detect_go()
        if go_info:
            runtimes["go"] = go_info

        # Rust
        rust_info = self._detect_rust()
        if rust_info:
            runtimes["rust"] = rust_info

        # PHP
        php_info = self._detect_php()
        if php_info:
            runtimes["php"] = php_info

        # Swift
        swift_info = self._detect_swift()
        if swift_info:
            runtimes["swift"] = swift_info

        # Kotlin
        kotlin_info = self._detect_kotlin()
        if kotlin_info:
            runtimes["kotlin"] = kotlin_info

        # Dart
        dart_info = self._detect_dart()
        if dart_info:
            runtimes["dart"] = dart_info

        # Elixir
        elixir_info = self._detect_elixir()
        if elixir_info:
            runtimes["elixir"] = elixir_info

        # Haskell
        haskell_info = self._detect_haskell()
        if haskell_info:
            runtimes["haskell"] = haskell_info

        # GCC/Clang
        gcc_info = self._detect_gcc()
        if gcc_info:
            runtimes["gcc"] = gcc_info

        clang_info = self._detect_clang()
        if clang_info:
            runtimes["clang"] = clang_info

        # Convert dataclasses to dicts
        return {k: asdict(v) if hasattr(v, "__dict__") else v for k, v in runtimes.items()}

    def _detect_nodejs(self) -> RuntimeInfo | None:
        """Detect Node.js installation."""
        try:
            node_version = subprocess.check_output(["node", "--version"]).decode().strip()
            npm_version = subprocess.check_output(["npm", "--version"]).decode().strip()

            return RuntimeInfo(
                name="Node.js",
                version=node_version.lstrip("v"),
                path=shutil.which("node"),
                additional_info={
                    "npm_version": npm_version,
                    "npm_path": shutil.which("npm"),
                },
            )
        except Exception:
            return None

    def _detect_java(self) -> RuntimeInfo | None:
        """Detect Java installation."""
        try:
            java_output = subprocess.check_output(
                ["java", "-version"], stderr=subprocess.STDOUT
            ).decode()

            version_match = re.search(r'version "?(\d+(?:\.\d+)*)', java_output)
            if version_match:
                version = version_match.group(1)

                # Detect vendor
                vendor = "Unknown"
                if "OpenJDK" in java_output:
                    vendor = "OpenJDK"
                elif "Oracle" in java_output:
                    vendor = "Oracle"
                elif "IBM" in java_output:
                    vendor = "IBM"

                return RuntimeInfo(
                    name="Java",
                    version=version,
                    path=shutil.which("java"),
                    additional_info={
                        "vendor": vendor,
                        "javac_path": shutil.which("javac"),
                    },
                )
            return None
        except Exception:
            return None

    def _detect_dotnet(self) -> RuntimeInfo | None:
        """Detect .NET installation."""
        try:
            output = subprocess.check_output(["dotnet", "--info"]).decode()

            # Extract version
            version_match = re.search(r"Version:\s*(\d+\.\d+\.\d+)", output)
            if version_match:
                return RuntimeInfo(
                    name=".NET",
                    version=version_match.group(1),
                    path=shutil.which("dotnet"),
                    additional_info={
                        "sdks": self._parse_dotnet_sdks(output),
                        "runtimes": self._parse_dotnet_runtimes(output),
                    },
                )
            return None
        except Exception:
            return None

    def _parse_dotnet_sdks(self, dotnet_output: str) -> list[str]:
        """Parse .NET SDK versions from dotnet --info."""
        sdks = []
        in_sdk_section = False

        for line in dotnet_output.split("\n"):
            if ".NET SDKs installed:" in line:
                in_sdk_section = True
                continue
            if in_sdk_section and line.strip() and not line[0].isspace():
                break
            if in_sdk_section and line.strip():
                version_match = re.search(r"(\d+\.\d+\.\d+)", line)
                if version_match:
                    sdks.append(version_match.group(1))

        return sdks

    def _parse_dotnet_runtimes(self, dotnet_output: str) -> list[str]:
        """Parse .NET runtime versions from dotnet --info."""
        runtimes = []
        in_runtime_section = False

        for line in dotnet_output.split("\n"):
            if ".NET runtimes installed:" in line:
                in_runtime_section = True
                continue
            if in_runtime_section and line.strip() and not line[0].isspace():
                break
            if in_runtime_section and line.strip():
                version_match = re.search(r"(\d+\.\d+\.\d+)", line)
                if version_match:
                    runtimes.append(version_match.group(1))

        return runtimes

    def _detect_ruby(self) -> RuntimeInfo | None:
        """Detect Ruby installation."""
        try:
            ruby_version = subprocess.check_output(["ruby", "--version"]).decode()
            version_match = re.search(r"ruby (\d+\.\d+\.\d+)", ruby_version)

            if version_match:
                return RuntimeInfo(
                    name="Ruby",
                    version=version_match.group(1),
                    path=shutil.which("ruby"),
                    additional_info={
                        "gem_path": shutil.which("gem"),
                        "full_version": ruby_version.strip(),
                    },
                )
            return None
        except Exception:
            return None

    def _detect_go(self) -> RuntimeInfo | None:
        """Detect Go installation."""
        try:
            go_version = subprocess.check_output(["go", "version"]).decode()
            version_match = re.search(r"go(\d+\.\d+(?:\.\d+)?)", go_version)

            if version_match:
                return RuntimeInfo(
                    name="Go",
                    version=version_match.group(1),
                    path=shutil.which("go"),
                    additional_info={
                        "gopath": os.environ.get("GOPATH"),
                        "goroot": os.environ.get("GOROOT"),
                    },
                )
            return None
        except Exception:
            return None

    def _detect_rust(self) -> RuntimeInfo | None:
        """Detect Rust installation."""
        try:
            rustc_version = subprocess.check_output(["rustc", "--version"]).decode()
            version_match = re.search(r"rustc (\d+\.\d+\.\d+)", rustc_version)

            if version_match:
                cargo_version = None
                try:
                    cargo_output = subprocess.check_output(["cargo", "--version"]).decode()
                    cargo_match = re.search(r"cargo (\d+\.\d+\.\d+)", cargo_output)
                    if cargo_match:
                        cargo_version = cargo_match.group(1)
                except Exception:
                    pass

                return RuntimeInfo(
                    name="Rust",
                    version=version_match.group(1),
                    path=shutil.which("rustc"),
                    additional_info={
                        "cargo_version": cargo_version,
                        "cargo_path": shutil.which("cargo"),
                        "rustup_home": os.environ.get("RUSTUP_HOME"),
                        "cargo_home": os.environ.get("CARGO_HOME"),
                    },
                )
            return None
        except Exception:
            return None

    def _detect_php(self) -> RuntimeInfo | None:
        """Detect PHP installation."""
        try:
            output = subprocess.check_output(["php", "--version"]).decode()
            m = re.search(r"PHP (\d+\.\d+\.\d+)", output)
            if m:
                return RuntimeInfo(
                    name="PHP",
                    version=m.group(1),
                    path=shutil.which("php"),
                    additional_info={
                        "composer_path": shutil.which("composer"),
                    },
                )
            return None
        except Exception:
            return None

    def _detect_swift(self) -> RuntimeInfo | None:
        """Detect Swift installation."""
        try:
            output = subprocess.check_output(["swift", "--version"]).decode()
            m = re.search(r"Swift version (\d+\.\d+(?:\.\d+)?)", output)
            if m:
                return RuntimeInfo(
                    name="Swift",
                    version=m.group(1),
                    path=shutil.which("swift"),
                )
            return None
        except Exception:
            return None

    def _detect_kotlin(self) -> RuntimeInfo | None:
        """Detect Kotlin installation."""
        try:
            output = subprocess.check_output(
                ["kotlin", "-version"], stderr=subprocess.STDOUT
            ).decode()
            m = re.search(r"(\d+\.\d+\.\d+)", output)
            if not m:
                output = subprocess.check_output(
                    ["kotlinc", "-version"], stderr=subprocess.STDOUT
                ).decode()
                m = re.search(r"(\d+\.\d+\.\d+)", output)
            if m:
                return RuntimeInfo(
                    name="Kotlin",
                    version=m.group(1),
                    path=shutil.which("kotlin") or shutil.which("kotlinc"),
                )
            return None
        except Exception:
            return None

    def _detect_dart(self) -> RuntimeInfo | None:
        """Detect Dart installation."""
        try:
            output = subprocess.check_output(["dart", "--version"]).decode()
            m = re.search(r"(\d+\.\d+\.\d+)", output)
            if m:
                return RuntimeInfo(
                    name="Dart",
                    version=m.group(1),
                    path=shutil.which("dart"),
                    additional_info={
                        "flutter_path": shutil.which("flutter"),
                    },
                )
            return None
        except Exception:
            return None

    def _detect_elixir(self) -> RuntimeInfo | None:
        """Detect Elixir installation."""
        try:
            output = subprocess.check_output(["elixir", "--version"]).decode()
            m = re.search(r"Elixir (\d+\.\d+(?:\.\d+)?)", output)
            if m:
                otp_m = re.search(r"OTP (\d+\.\d+(?:\.\d+)?)", output)
                return RuntimeInfo(
                    name="Elixir",
                    version=m.group(1),
                    path=shutil.which("elixir"),
                    additional_info={
                        "otp_version": otp_m.group(1) if otp_m else None,
                    },
                )
            return None
        except Exception:
            return None

    def _detect_haskell(self) -> RuntimeInfo | None:
        """Detect Haskell (GHC) installation."""
        try:
            output = subprocess.check_output(["ghc", "--version"]).decode()
            m = re.search(r"(\d+\.\d+(?:\.\d+)?)", output)
            if m:
                return RuntimeInfo(
                    name="Haskell (GHC)",
                    version=m.group(1),
                    path=shutil.which("ghc"),
                    additional_info={
                        "cabal_path": shutil.which("cabal"),
                        "stack_path": shutil.which("stack"),
                    },
                )
            return None
        except Exception:
            return None

    def _detect_gcc(self) -> RuntimeInfo | None:
        """Detect GCC installation."""
        try:
            gcc_output = subprocess.check_output(["gcc", "--version"]).decode()
            version_match = re.search(r"gcc.*?(\d+\.\d+\.\d+)", gcc_output, re.IGNORECASE)

            if version_match:
                return RuntimeInfo(
                    name="GCC",
                    version=version_match.group(1),
                    path=shutil.which("gcc"),
                    additional_info={
                        "gpp_path": shutil.which("g++"),
                        "target": self._get_gcc_target(),
                    },
                )
            return None
        except Exception:
            return None

    def _get_gcc_target(self) -> str | None:
        """Get GCC target architecture."""
        try:
            output = subprocess.check_output(["gcc", "-dumpmachine"]).decode().strip()
            return output
        except Exception:
            return None

    def _detect_clang(self) -> RuntimeInfo | None:
        """Detect Clang installation."""
        try:
            clang_output = subprocess.check_output(["clang", "--version"]).decode()
            version_match = re.search(r"clang version (\d+\.\d+\.\d+)", clang_output)

            if version_match:
                return RuntimeInfo(
                    name="Clang",
                    version=version_match.group(1),
                    path=shutil.which("clang"),
                    additional_info={
                        "clangpp_path": shutil.which("clang++"),
                        "llvm_version": self._get_llvm_version(),
                    },
                )
            return None
        except Exception:
            return None

    def _get_llvm_version(self) -> str | None:
        """Get LLVM version."""
        try:
            output = subprocess.check_output(["llvm-config", "--version"]).decode().strip()
            return output
        except Exception:
            return None

    def detect_installed_packages(self) -> dict[str, list[Any]]:
        """Detect installed packages across different package managers."""
        packages = {}

        # Python packages
        if self.deep_scan:
            packages["python"] = self._get_python_packages_detailed()
        else:
            packages["python"] = self._get_python_packages()

        # Node.js packages
        packages["npm"] = self._get_npm_packages()

        # System packages
        system_type = platform.system()
        if system_type == "Linux":
            packages.update(self._get_linux_packages())
        elif system_type == "Darwin":
            packages["homebrew"] = self._get_homebrew_packages()
        elif system_type == "Windows":
            packages["chocolatey"] = self._get_chocolatey_packages()

        # Ruby gems
        packages["gem"] = self._get_ruby_gems()

        # Rust crates
        packages["cargo"] = self._get_cargo_packages()

        # Convert to dict format
        result: dict[str, list[dict[str, Any]]] = {}
        for manager, pkg_list in packages.items():
            if pkg_list:
                converted: list[Any] = []
                for pkg in pkg_list:
                    converted.append(asdict(pkg) if hasattr(pkg, "__dict__") else pkg)
                result[manager] = converted

        return result

    def _get_python_packages(self) -> list[PackageInfo]:
        """Get installed Python packages (basic)."""
        packages = []

        if HAS_PKG_RESOURCES:
            try:
                for dist in pkg_resources.working_set:
                    packages.append(
                        PackageInfo(
                            name=dist.project_name,
                            version=dist.version,
                            manager="pip",
                            location=dist.location,
                        )
                    )
            except Exception:
                pass

        # Fallback to pip list
        if not packages:
            try:
                output = subprocess.check_output(
                    [sys.executable, "-m", "pip", "list", "--format=json"]
                ).decode()

                pip_packages = json.loads(output)
                for pkg in pip_packages:
                    packages.append(
                        PackageInfo(name=pkg["name"], version=pkg["version"], manager="pip")
                    )
            except Exception:
                pass

        return packages

    def _get_python_packages_detailed(self) -> list[PackageInfo]:
        """Get detailed Python package information."""
        packages = []

        try:
            # Use pip show for detailed info
            output = subprocess.check_output(
                [sys.executable, "-m", "pip", "list", "--format=json"]
            ).decode()

            pip_packages = json.loads(output)

            for pkg in pip_packages[:50]:  # Limit for performance
                try:
                    show_output = subprocess.check_output(
                        [sys.executable, "-m", "pip", "show", pkg["name"]]
                    ).decode()

                    pkg_info = PackageInfo(name=pkg["name"], version=pkg["version"], manager="pip")

                    # Parse pip show output
                    for line in show_output.split("\n"):
                        if line.startswith("Location:"):
                            pkg_info.location = line.split(":", 1)[1].strip()
                        elif line.startswith("Requires:"):
                            deps = line.split(":", 1)[1].strip()
                            if deps:
                                pkg_info.dependencies = [d.strip() for d in deps.split(",")]

                    packages.append(pkg_info)

                except Exception:
                    # Fallback to basic info
                    packages.append(
                        PackageInfo(name=pkg["name"], version=pkg["version"], manager="pip")
                    )

        except Exception:
            # Fallback to basic method
            packages = self._get_python_packages()

        return packages

    def _get_npm_packages(self) -> list[PackageInfo]:
        """Get installed npm packages."""
        packages = []

        try:
            # Global packages
            output = subprocess.check_output(["npm", "list", "-g", "--json", "--depth=0"]).decode()

            data = json.loads(output)
            if "dependencies" in data:
                for name, info in data["dependencies"].items():
                    packages.append(
                        PackageInfo(
                            name=name,
                            version=info.get("version", "unknown"),
                            manager="npm",
                            metadata={"scope": "global"},
                        )
                    )
        except Exception:
            pass

        # Local packages (if in a project directory)
        if os.path.exists("package.json"):
            try:
                output = subprocess.check_output(["npm", "list", "--json", "--depth=0"]).decode()

                data = json.loads(output)
                if "dependencies" in data:
                    for name, info in data["dependencies"].items():
                        packages.append(
                            PackageInfo(
                                name=name,
                                version=info.get("version", "unknown"),
                                manager="npm",
                                metadata={"scope": "local"},
                            )
                        )
            except Exception:
                pass

        return packages

    def _get_linux_packages(self) -> dict[str, list[PackageInfo]]:
        """Get Linux system packages."""
        packages = {}

        # APT (Debian/Ubuntu)
        if shutil.which("dpkg"):
            packages["apt"] = self._get_apt_packages()

        # YUM/DNF (RedHat/Fedora)
        if shutil.which("rpm"):
            packages["rpm"] = self._get_rpm_packages()

        # Pacman (Arch)
        if shutil.which("pacman"):
            packages["pacman"] = self._get_pacman_packages()

        # Snap packages
        if shutil.which("snap"):
            packages["snap"] = self._get_snap_packages()

        # Flatpak
        if shutil.which("flatpak"):
            packages["flatpak"] = self._get_flatpak_packages()

        # APK (Alpine)
        if shutil.which("apk"):
            packages["apk"] = self._get_apk_packages()

        return packages

    def _get_apt_packages(self) -> list[PackageInfo]:
        """Get APT packages."""
        packages = []

        try:
            output = subprocess.check_output(
                ["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\n"]
            ).decode()

            for line in output.split("\n"):
                if line and "\t" in line:
                    parts = line.split("\t")
                    if len(parts) >= 3 and "installed" in parts[2]:
                        packages.append(PackageInfo(name=parts[0], version=parts[1], manager="apt"))
        except Exception:
            pass

        return packages[:100] if not self.deep_scan else packages  # Limit if not deep scan

    def _get_rpm_packages(self) -> list[PackageInfo]:
        """Get RPM packages."""
        packages = []

        try:
            output = subprocess.check_output(
                ["rpm", "-qa", "--queryformat", "%{NAME}\t%{VERSION}-%{RELEASE}\n"]
            ).decode()

            for line in output.split("\n"):
                if line and "\t" in line:
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        packages.append(PackageInfo(name=parts[0], version=parts[1], manager="rpm"))
        except Exception:
            pass

        return packages[:100] if not self.deep_scan else packages

    def _get_pacman_packages(self) -> list[PackageInfo]:
        """Get Pacman packages."""
        packages = []

        try:
            output = subprocess.check_output(["pacman", "-Q"]).decode()

            for line in output.split("\n"):
                if line:
                    parts = line.split()
                    if len(parts) >= 2:
                        packages.append(
                            PackageInfo(name=parts[0], version=parts[1], manager="pacman")
                        )
        except Exception:
            pass

        return packages[:100] if not self.deep_scan else packages

    def _get_snap_packages(self) -> list[PackageInfo]:
        """Get Snap packages."""
        packages = []

        try:
            output = subprocess.check_output(["snap", "list"]).decode()
            lines = output.strip().split("\n")[1:]  # Skip header

            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    packages.append(PackageInfo(name=parts[0], version=parts[1], manager="snap"))
        except Exception:
            pass

        return packages

    def _get_flatpak_packages(self) -> list[PackageInfo]:
        """Get Flatpak packages."""
        packages = []

        try:
            output = subprocess.check_output(
                ["flatpak", "list", "--app", "--columns=application,version"]
            ).decode()

            for line in output.strip().split("\n"):
                if line and "\t" in line:
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        packages.append(
                            PackageInfo(name=parts[0], version=parts[1], manager="flatpak")
                        )
        except Exception:
            pass

        return packages

    def _get_homebrew_packages(self) -> list[PackageInfo]:
        """Get Homebrew packages (macOS)."""
        packages = []

        try:
            output = subprocess.check_output(["brew", "list", "--versions"]).decode()

            for line in output.split("\n"):
                if line:
                    parts = line.split(" ", 1)
                    if len(parts) >= 2:
                        packages.append(
                            PackageInfo(name=parts[0], version=parts[1], manager="homebrew")
                        )
        except Exception:
            pass

        return packages

    def _get_chocolatey_packages(self) -> list[PackageInfo]:
        """Get Chocolatey packages (Windows)."""
        packages = []

        try:
            output = subprocess.check_output(["choco", "list", "--local-only", "-r"]).decode()

            for line in output.split("\n"):
                if line and "|" in line:
                    parts = line.split("|")
                    if len(parts) >= 2:
                        packages.append(
                            PackageInfo(name=parts[0], version=parts[1], manager="chocolatey")
                        )
        except Exception:
            pass

        return packages

    def _get_apk_packages(self) -> list[PackageInfo]:
        """Get APK packages (Alpine Linux)."""
        packages = []
        try:
            output = subprocess.check_output(["apk", "list", "--installed"]).decode()
            for line in output.split("\n"):
                line = line.strip()
                if line:
                    parts = line.split(" ", 1)
                    if len(parts) >= 1:
                        name_ver = parts[0]
                        nv_parts = name_ver.rsplit("-", 2)
                        if len(nv_parts) >= 2:
                            name = nv_parts[0]
                            version = (
                                f"{nv_parts[1]}-{nv_parts[2]}"
                                if len(nv_parts) == 3
                                else nv_parts[1]
                            )
                            packages.append(PackageInfo(name=name, version=version, manager="apk"))
        except Exception:
            pass
        return packages[:100] if not self.deep_scan else packages

    def _get_ruby_gems(self) -> list[PackageInfo]:
        """Get Ruby gems."""
        packages = []

        try:
            output = subprocess.check_output(["gem", "list", "--local"]).decode()

            for line in output.split("\n"):
                if line:
                    match = re.match(r"^([\w-]+)\s+\(([\d.]+)\)", line)
                    if match:
                        packages.append(
                            PackageInfo(
                                name=match.group(1),
                                version=match.group(2),
                                manager="gem",
                            )
                        )
        except Exception:
            pass

        return packages[:50] if not self.deep_scan else packages

    def _get_cargo_packages(self) -> list[PackageInfo]:
        """Get Rust cargo packages."""
        packages = []

        try:
            output = subprocess.check_output(["cargo", "install", "--list"]).decode()

            current_package = None
            for line in output.split("\n"):
                if line and not line.startswith(" "):
                    # Package line
                    match = re.match(r"^([\w-]+)\s+v([\d.]+)", line)
                    if match:
                        current_package = PackageInfo(
                            name=match.group(1), version=match.group(2), manager="cargo"
                        )
                        packages.append(current_package)
        except Exception:
            pass

        return packages

    def detect_security_info(self) -> dict[str, Any]:
        """Detect security-related information."""
        security_data = {
            "firewall": self._detect_firewall(),
            "antivirus": self._detect_antivirus(),
            "selinux": self._detect_selinux(),
            "updates_available": self._check_system_updates(),
        }

        return security_data

    def _detect_firewall(self) -> dict[str, Any]:
        """Detect firewall status."""
        firewall_info: dict[str, Any] = {"enabled": False, "type": None}

        if platform.system() == "Linux":
            # Check iptables
            try:
                subprocess.check_call(
                    ["iptables", "-L", "-n"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                firewall_info["type"] = "iptables"
                firewall_info["enabled"] = True
            except Exception:
                pass

            # Check ufw
            try:
                output = subprocess.check_output(["ufw", "status"]).decode()
                if "Status: active" in output:
                    firewall_info["type"] = "ufw"
                    firewall_info["enabled"] = True
            except Exception:
                pass

            # Check firewalld
            try:
                output = subprocess.check_output(
                    ["firewall-cmd", "--state"], stderr=subprocess.DEVNULL
                ).decode()
                if "running" in output:
                    firewall_info["type"] = "firewalld"
                    firewall_info["enabled"] = True
            except Exception:
                pass

        elif platform.system() == "Windows":
            # Check Windows Firewall
            try:
                output = subprocess.check_output(
                    ["netsh", "advfirewall", "show", "allprofiles", "state"]
                ).decode()
                if "ON" in output:
                    firewall_info["type"] = "windows_firewall"
                    firewall_info["enabled"] = True
            except Exception:
                pass

        elif platform.system() == "Darwin":
            # Check macOS firewall
            try:
                output = subprocess.check_output(
                    [
                        "defaults",
                        "read",
                        "/Library/Preferences/com.apple.alf",
                        "globalstate",
                    ]
                ).decode()
                if "1" in output or "2" in output:
                    firewall_info["type"] = "macos_firewall"
                    firewall_info["enabled"] = True
            except Exception:
                pass

        return firewall_info

    def _detect_antivirus(self) -> list[dict[str, str]]:
        """Detect installed antivirus software."""
        av_list = []

        if platform.system() == "Windows":
            # Check Windows Security Center
            try:
                output = subprocess.check_output(
                    [
                        "wmic",
                        "/namespace:\\\\root\\SecurityCenter2",
                        "path",
                        "AntiVirusProduct",
                        "get",
                        "displayName",
                    ],
                    stderr=subprocess.DEVNULL,
                ).decode()

                for line in output.split("\n"):
                    line = line.strip()
                    if line and line != "displayName":
                        av_list.append({"name": line, "type": "antivirus"})
            except Exception:
                pass

        elif platform.system() == "Linux":
            # Check for common Linux AV
            av_products = ["clamav", "sophos", "eset", "kaspersky"]
            for av in av_products:
                if shutil.which(av) or os.path.exists(f"/etc/{av}"):
                    av_list.append({"name": av, "type": "antivirus"})

        return av_list

    def _detect_selinux(self) -> dict[str, str] | None:
        """Detect SELinux status (Linux only)."""
        if platform.system() != "Linux":
            return None

        try:
            output = subprocess.check_output(["sestatus"]).decode()
            status: dict[str, Any] = {}

            for line in output.split("\n"):
                if "SELinux status:" in line:
                    status["enabled"] = "enabled" in line
                elif "Current mode:" in line:
                    status["mode"] = line.split(":")[1].strip()
                elif "Policy version:" in line:
                    status["policy_version"] = line.split(":")[1].strip()

            return status
        except Exception:
            return None

    def _check_system_updates(self) -> dict[str, Any]:
        """Check for available system updates."""
        updates: dict[str, Any] = {"available": False, "count": 0}

        if platform.system() == "Linux":
            # Check apt
            if shutil.which("apt"):
                try:
                    subprocess.check_call(
                        ["apt", "update"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    output = subprocess.check_output(["apt", "list", "--upgradable"]).decode()
                    count = len([line for line in output.split("\n") if "upgradable" in line])
                    if count > 0:
                        updates["available"] = True
                        updates["count"] = count
                except Exception:
                    pass

        elif platform.system() == "Windows":
            # Windows Update check would require COM interface
            # Simplified check
            updates["update_command"] = "Check Windows Update in Settings"

        elif platform.system() == "Darwin":
            # Check softwareupdate
            try:
                output = subprocess.check_output(["softwareupdate", "-l"]).decode()
                if "Software Update found" in output:
                    updates["available"] = True
                    # Count updates
                    updates["count"] = output.count("*")
            except Exception:
                pass

        return updates

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get current system performance metrics."""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "cpu": {},
            "memory": {},
            "disk": {},
            "network": {},
        }

        if HAS_PSUTIL:
            # CPU metrics
            metrics["cpu"] = {
                "percent": psutil.cpu_percent(interval=1),
                "percent_per_core": psutil.cpu_percent(interval=1, percpu=True),
                "load_average": os.getloadavg() if hasattr(os, "getloadavg") else None,
            }

            # Memory metrics
            vmem = psutil.virtual_memory()
            metrics["memory"] = {
                "percent": vmem.percent,
                "used_gb": vmem.used / (1024**3),
                "available_gb": vmem.available / (1024**3),
            }

            # Disk I/O
            disk_io = psutil.disk_io_counters()
            if disk_io:
                metrics["disk"] = {
                    "read_mb_s": disk_io.read_bytes / (1024**2),
                    "write_mb_s": disk_io.write_bytes / (1024**2),
                }

            # Network I/O
            net_io = psutil.net_io_counters()
            if net_io:
                metrics["network"] = {
                    "sent_mb": net_io.bytes_sent / (1024**2),
                    "recv_mb": net_io.bytes_recv / (1024**2),
                    "packets_sent": net_io.packets_sent,
                    "packets_recv": net_io.packets_recv,
                }

        # Generate metrics hash for comparison/caching
        metrics["metrics_hash"] = hash_system_info(metrics)

        return metrics

    def detect_system_capabilities(self) -> dict[str, Any]:
        """Detect system capabilities and features."""
        capabilities: dict[str, Any] = {
            "virtualization": {},
            "hardware_acceleration": {},
            "development_tools": {},
            "multimedia": {},
        }

        # Virtualization support
        capabilities["virtualization"] = {
            "docker": shutil.which("docker") is not None,
            "podman": shutil.which("podman") is not None,
            "virtualbox": shutil.which("VBoxManage") is not None,
            "vmware": self._check_vmware(),
            "kvm": self._check_kvm_support(),
            "hyper_v": self._check_hyperv(),
        }

        # Hardware acceleration
        capabilities["hardware_acceleration"] = {
            "cuda": self._detect_cuda_info() is not None,
            "opencl": self._detect_opencl_info() is not None,
            "vulkan": self._detect_vulkan_info() is not None,
            "metal": platform.system() == "Darwin",
            "directx": platform.system() == "Windows",
        }

        # Development tools
        dev_tools = [
            "git",
            "make",
            "cmake",
            "gcc",
            "g++",
            "clang",
            "clang++",
            "python",
            "python3",
            "pip",
            "pip3",
            "node",
            "npm",
            "yarn",
            "java",
            "javac",
            "maven",
            "gradle",
            "dotnet",
            "go",
            "rust",
            "cargo",
            "ruby",
            "gem",
            "perl",
            "php",
            "composer",
            "swift",
            "kotlin",
            "dart",
            "flutter",
            "elixir",
            "ghc",
            "cabal",
            "stack",
        ]

        capabilities["development_tools"] = {
            tool: shutil.which(tool) is not None for tool in dev_tools
        }

        # Shell tools
        shell_tools = [
            "bash",
            "zsh",
            "fish",
            "sh",
            "curl",
            "wget",
            "ssh",
            "rsync",
            "tmux",
            "screen",
            "vim",
            "nvim",
            "nano",
            "emacs",
            "less",
            "jq",
            "unzip",
            "tar",
            "gzip",
        ]
        capabilities["shell_tools"] = {tool: shutil.which(tool) is not None for tool in shell_tools}

        # Multimedia libraries
        multimedia = {
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "imagemagick": shutil.which("convert") is not None,
            "gstreamer": shutil.which("gst-launch-1.0") is not None,
        }

        capabilities["multimedia"] = multimedia

        return capabilities

    def _check_vmware(self) -> bool:
        """Check for VMware installation."""
        if platform.system() == "Windows":
            return os.path.exists("C:\\Program Files (x86)\\VMware") or os.path.exists(
                "C:\\Program Files\\VMware"
            )
        return shutil.which("vmware") is not None

    def _check_kvm_support(self) -> bool:
        """Check KVM support (Linux)."""
        if platform.system() != "Linux":
            return False

        # Check CPU support
        try:
            with open("/proc/cpuinfo") as f:
                cpuinfo = f.read()
                has_vmx = " vmx " in cpuinfo  # Intel
                has_svm = " svm " in cpuinfo  # AMD

                # Check if KVM module is loaded
                kvm_loaded = os.path.exists("/dev/kvm")

                return (has_vmx or has_svm) and kvm_loaded
        except Exception:
            return False

    def _check_hyperv(self) -> bool:
        """Check Hyper-V support (Windows)."""
        if platform.system() != "Windows":
            return False

        try:
            output = subprocess.check_output(
                [
                    "powershell",
                    "Get-WindowsOptionalFeature",
                    "-Online",
                    "-FeatureName",
                    "Microsoft-Hyper-V",
                ],
                stderr=subprocess.DEVNULL,
            ).decode()
            return "Enabled" in output
        except Exception:
            return False

    def export_scan_results(
        self, format: str = "json", include_sensitive: bool = False
    ) -> str | dict:
        """Export scan results in various formats."""
        # Filter sensitive information if requested
        data = self.system_info.copy()

        if not include_sensitive:
            # Remove potentially sensitive data
            if "network" in data:
                data["network"].pop("connections", None)
            if "installed_packages" in data:
                # Limit package lists
                for manager in data["installed_packages"]:
                    if len(data["installed_packages"][manager]) > 20:
                        data["installed_packages"][manager] = data["installed_packages"][manager][
                            :20
                        ]

        if format == "json":
            return json.dumps(data, indent=2, default=str)
        if format == "summary":
            return self._generate_summary(data)
        return data

    def _generate_summary(self, data: dict) -> str:
        """Generate human-readable summary."""
        summary = []
        summary.append("=== System Scan Summary ===\n")

        # Platform info
        if "platform" in data:
            platform_info = data["platform"]
            summary.append(f"OS: {platform_info.get('system')} {platform_info.get('release')}")
            summary.append(f"Architecture: {platform_info.get('machine')}")
            summary.append(f"Hostname: {platform_info.get('hostname')}")

            if platform_info.get("distribution"):
                dist = platform_info["distribution"]
                summary.append(
                    f"Distribution: {dist.get('name', 'Unknown')} {dist.get('version', '')}"
                )

        summary.append("")

        # CPU info
        if "cpu" in data:
            cpu = data["cpu"]
            summary.append(f"CPU: {cpu.get('brand', 'Unknown')}")
            summary.append(
                f"Cores: {cpu.get('count_physical', 'Unknown')} physical, {cpu.get('count_logical', 'Unknown')} logical"
            )
            if cpu.get("current_frequency"):
                summary.append(f"Frequency: {cpu['current_frequency']:.2f} MHz")

        summary.append("")

        # Memory info
        if "memory" in data:
            mem = data["memory"]
            if mem.get("total"):
                summary.append(f"Memory: {mem['total'] / (1024**3):.2f} GB total")
                summary.append(
                    f"        {mem.get('available', 0) / (1024**3):.2f} GB available ({mem.get('percent', 0):.1f}% used)"
                )

        summary.append("")

        # GPU info
        if "gpu" in data and data["gpu"].get("available"):
            summary.append("GPUs:")
            for gpu in data["gpu"].get("devices", []):
                summary.append(f"  - {gpu.get('name', 'Unknown GPU')}")
                if gpu.get("memory_total"):
                    summary.append(f"    Memory: {gpu['memory_total']} MB")

        summary.append("")

        # Runtime versions
        if "runtime_versions" in data:
            summary.append("Runtimes:")
            for runtime, info in data["runtime_versions"].items():
                if isinstance(info, dict):
                    summary.append(f"  - {runtime}: {info.get('version', 'Unknown')}")

        summary.append("")

        # Container info
        if "container" in data and data["container"].get("detected"):
            summary.append(f"Container: {data['container']['type']}")

        summary.append("")
        summary.append(
            f"Scan completed at: {data.get('scan_metadata', {}).get('timestamp', 'Unknown')}"
        )

        return "\n".join(summary)


# Example usage
async def example_usage():
    """Example usage."""
    scanner = SystemScanner(enable_cache=True, parallel_scan=True, deep_scan=False)

    async with scanner:
        # Full scan
        await scanner.scan_all()

        # Export as JSON
        scanner.export_scan_results(format="json", include_sensitive=False)

        # Get summary
        summary = scanner.export_scan_results(format="summary")
        print(summary)

        # Specific scans
        await scanner.scan_all(categories=["cpu", "memory", "gpu"])


if __name__ == "__main__":
    import sys

    # Add minimal dependencies
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    asyncio.run(example_usage())
