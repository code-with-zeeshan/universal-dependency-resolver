"""Module docstring."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


class OSType(Enum):
    """Os Type functionality."""

    WINDOWS = "Windows"
    LINUX = "Linux"
    MACOS = "Darwin"
    BSD = "BSD"
    UNKNOWN = "Unknown"


class ContainerType(Enum):
    """Container Type functionality."""

    DOCKER = "docker"
    PODMAN = "podman"
    LXC = "lxc"
    WSL = "wsl"
    VM = "vm"
    BARE_METAL = "bare_metal"


@dataclass
class GPUInfo:
    """Gpu Info functionality."""

    id: int
    name: str
    memory_total: int
    memory_free: int
    memory_used: int
    utilization: float
    temperature: Optional[float] = None
    driver_version: Optional[str] = None
    cuda_version: Optional[str] = None
    compute_capability: Optional[str] = None


@dataclass
class CPUInfo:
    """Cpu Info functionality."""

    brand: str
    arch: str
    bits: int
    count_physical: int
    count_logical: int
    max_frequency: Optional[float] = None
    min_frequency: Optional[float] = None
    current_frequency: Optional[float] = None
    cache_sizes: Dict[str, int] = field(default_factory=dict)
    features: List[str] = field(default_factory=list)
    temperature: Optional[float] = None


@dataclass
class MemoryInfo:
    """Memory Info functionality."""

    total: int
    available: int
    used: int
    free: int
    percent: float
    swap_total: int
    swap_used: int
    swap_free: int
    swap_percent: float


@dataclass
class DiskInfo:
    """Disk Info functionality."""

    device: str
    mountpoint: str
    fstype: str
    total: int
    used: int
    free: int
    percent: float


@dataclass
class NetworkInterface:
    """Network Interface functionality."""

    name: str
    addresses: List[Dict[str, str]]
    is_up: bool
    speed: Optional[int] = None
    mtu: Optional[int] = None
    stats: Dict[str, int] = field(default_factory=dict)


@dataclass
class RuntimeInfo:
    """Runtime Info functionality."""

    name: str
    version: str
    path: Optional[str] = None
    architecture: Optional[str] = None
    implementation: Optional[str] = None
    additional_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PackageInfo:
    """Package Info functionality."""

    name: str
    version: str
    manager: str
    location: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
