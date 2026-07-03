# tests/unit/test_core/test_scanner_models.py
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


class TestOSType:
    def test_values(self):
        assert OSType.WINDOWS.value == "Windows"
        assert OSType.LINUX.value == "Linux"
        assert OSType.MACOS.value == "Darwin"
        assert OSType.BSD.value == "BSD"
        assert OSType.UNKNOWN.value == "Unknown"

    def test_members(self):
        assert len(OSType) == 5


class TestContainerType:
    def test_values(self):
        assert ContainerType.DOCKER.value == "docker"
        assert ContainerType.PODMAN.value == "podman"
        assert ContainerType.LXC.value == "lxc"
        assert ContainerType.WSL.value == "wsl"
        assert ContainerType.VM.value == "vm"
        assert ContainerType.BARE_METAL.value == "bare_metal"

    def test_members(self):
        assert len(ContainerType) == 6


class TestGPUInfo:
    def test_minimal_construction(self):
        gpu = GPUInfo(id=0, name="Test GPU", memory_total=8192, memory_free=4096,
                      memory_used=4096, utilization=50.0)
        assert gpu.id == 0
        assert gpu.name == "Test GPU"
        assert gpu.memory_total == 8192
        assert gpu.memory_free == 4096
        assert gpu.memory_used == 4096
        assert gpu.utilization == 50.0
        assert gpu.temperature is None
        assert gpu.driver_version is None
        assert gpu.cuda_version is None
        assert gpu.compute_capability is None

    def test_full_construction(self):
        gpu = GPUInfo(
            id=1, name="RTX 4090", memory_total=24576, memory_free=16384,
            memory_used=8192, utilization=35.5, temperature=65.0,
            driver_version="535.129", cuda_version="12.1", compute_capability="8.9",
        )
        assert gpu.temperature == 65.0
        assert gpu.driver_version == "535.129"
        assert gpu.cuda_version == "12.1"
        assert gpu.compute_capability == "8.9"

    def test_default_factory(self):
        gpu = GPUInfo(id=0, name="GPU", memory_total=1024, memory_free=512,
                      memory_used=512, utilization=0.0)
        assert gpu.temperature is None


class TestCPUInfo:
    def test_minimal_construction(self):
        cpu = CPUInfo(brand="Intel", arch="x86_64", bits=64,
                      count_physical=8, count_logical=16)
        assert cpu.brand == "Intel"
        assert cpu.arch == "x86_64"
        assert cpu.bits == 64
        assert cpu.count_physical == 8
        assert cpu.count_logical == 16
        assert cpu.max_frequency is None
        assert cpu.cache_sizes == {}
        assert cpu.features == []
        assert cpu.temperature is None

    def test_full_construction(self):
        cpu = CPUInfo(
            brand="AMD", arch="x86_64", bits=64, count_physical=16, count_logical=32,
            max_frequency=5000.0, min_frequency=2200.0, current_frequency=3500.0,
            cache_sizes={"l1": 512, "l2": 4096, "l3": 32768},
            features=["avx2", "sse4.2"], temperature=55.0,
        )
        assert cpu.max_frequency == 5000.0
        assert cpu.cache_sizes["l1"] == 512
        assert "avx2" in cpu.features

    def test_default_factory(self):
        cpu = CPUInfo(brand="Test", arch="arm", bits=64, count_physical=4, count_logical=4)
        assert cpu.cache_sizes == {}
        assert cpu.features == []


class TestMemoryInfo:
    def test_construction(self):
        mem = MemoryInfo(
            total=16384, available=8192, used=8192, free=4096,
            percent=50.0, swap_total=8192, swap_used=1024, swap_free=7168,
            swap_percent=12.5,
        )
        assert mem.total == 16384
        assert mem.available == 8192
        assert mem.used == 8192
        assert mem.free == 4096
        assert mem.percent == 50.0
        assert mem.swap_total == 8192
        assert mem.swap_used == 1024
        assert mem.swap_free == 7168
        assert mem.swap_percent == 12.5


class TestDiskInfo:
    def test_construction(self):
        disk = DiskInfo(
            device="/dev/sda1", mountpoint="/", fstype="ext4",
            total=500000, used=200000, free=300000, percent=40.0,
        )
        assert disk.device == "/dev/sda1"
        assert disk.mountpoint == "/"
        assert disk.fstype == "ext4"
        assert disk.total == 500000
        assert disk.used == 200000
        assert disk.free == 300000
        assert disk.percent == 40.0


class TestNetworkInterface:
    def test_minimal_construction(self):
        net = NetworkInterface(
            name="eth0",
            addresses=[{"addr": "192.168.1.1"}],
            is_up=True,
        )
        assert net.name == "eth0"
        assert len(net.addresses) == 1
        assert net.is_up is True
        assert net.speed is None
        assert net.mtu is None
        assert net.stats == {}

    def test_full_construction(self):
        net = NetworkInterface(
            name="eth0", addresses=[{"addr": "10.0.0.1"}], is_up=True,
            speed=1000, mtu=1500,
            stats={"rx_bytes": 1000, "tx_bytes": 500},
        )
        assert net.speed == 1000
        assert net.mtu == 1500
        assert net.stats["rx_bytes"] == 1000


class TestRuntimeInfo:
    def test_minimal_construction(self):
        rt = RuntimeInfo(name="python", version="3.11.0")
        assert rt.name == "python"
        assert rt.version == "3.11.0"
        assert rt.path is None
        assert rt.architecture is None
        assert rt.implementation is None
        assert rt.additional_info == {}

    def test_full_construction(self):
        rt = RuntimeInfo(
            name="node", version="20.0.0", path="/usr/bin/node",
            architecture="x64", implementation="V8",
            additional_info={"features": ["esm"]},
        )
        assert rt.path == "/usr/bin/node"
        assert rt.additional_info["features"] == ["esm"]


class TestPackageInfo:
    def test_minimal_construction(self):
        pkg = PackageInfo(name="requests", version="2.31.0", manager="pip")
        assert pkg.name == "requests"
        assert pkg.version == "2.31.0"
        assert pkg.manager == "pip"
        assert pkg.location is None
        assert pkg.dependencies == []
        assert pkg.metadata == {}

    def test_full_construction(self):
        pkg = PackageInfo(
            name="flask", version="2.3.0", manager="pip",
            location="/usr/lib/python3.11",
            dependencies=["werkzeug>=2.3", "markupsafe"],
            metadata={"homepage": "https://flask.palletsprojects.com/"},
        )
        assert pkg.location == "/usr/lib/python3.11"
        assert len(pkg.dependencies) == 2
        assert pkg.metadata["homepage"] is not None
