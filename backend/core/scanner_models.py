"""Module docstring."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
    temperature: float | None = None
    driver_version: str | None = None
    cuda_version: str | None = None
    compute_capability: str | None = None


@dataclass
class CPUInfo:
    """Cpu Info functionality."""

    brand: str
    arch: str
    bits: int
    count_physical: int
    count_logical: int
    max_frequency: float | None = None
    min_frequency: float | None = None
    current_frequency: float | None = None
    cache_sizes: dict[str, int] = field(default_factory=dict)
    features: list[str] = field(default_factory=list)
    temperature: float | None = None


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
    addresses: list[dict[str, str]]
    is_up: bool
    speed: int | None = None
    mtu: int | None = None
    stats: dict[str, int] = field(default_factory=dict)


@dataclass
class RuntimeInfo:
    """Runtime Info functionality."""

    name: str
    version: str
    path: str | None = None
    architecture: str | None = None
    implementation: str | None = None
    additional_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class PackageInfo:
    """Package Info functionality."""

    name: str
    version: str
    manager: str
    location: str | None = None
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
