# tests/unit/test_core/test_system_scanner.py
import pytest
import platform
from unittest.mock import patch, MagicMock
from backend.core.system_scanner import (
    SystemScanner,
    OSType,
    ContainerType,
    GPUInfo,
    CPUInfo,
    MemoryInfo,
    DiskInfo,
    RuntimeInfo
)


class TestSystemScanner:
    @pytest.fixture
    def scanner(self):
        """Create SystemScanner instance for testing"""
        return SystemScanner()

    def test_initialization(self, scanner):
        """Test SystemScanner initialization"""
        assert scanner.os_info is not None
        assert scanner.cpu_info is not None
        assert scanner.memory_info is not None

    @patch('platform.system')
    def test_get_os_type_linux(self, mock_system, scanner):
        """Test OS type detection for Linux"""
        mock_system.return_value = 'Linux'
        os_type = scanner._get_os_type()
        assert os_type == OSType.LINUX

    @patch('platform.system')
    def test_get_os_type_windows(self, mock_system, scanner):
        """Test OS type detection for Windows"""
        mock_system.return_value = 'Windows'
        os_type = scanner._get_os_type()
        assert os_type == OSType.WINDOWS

    @patch('platform.system')
    def test_get_os_type_macos(self, mock_system, scanner):
        """Test OS type detection for macOS"""
        mock_system.return_value = 'Darwin'
        os_type = scanner._get_os_type()
        assert os_type == OSType.MACOS

    @patch('platform.system')
    def test_get_os_type_unknown(self, mock_system, scanner):
        """Test OS type detection for unknown OS"""
        mock_system.return_value = 'UnknownOS'
        os_type = scanner._get_os_type()
        assert os_type == OSType.UNKNOWN

    @patch('subprocess.run')
    def test_detect_container_docker(self, mock_subprocess, scanner):
        """Test Docker container detection"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b'/.dockerenv exists'
        mock_subprocess.return_value = mock_result

        container_type = scanner._detect_container()
        assert container_type == ContainerType.DOCKER

    @patch('os.path.exists')
    @patch('subprocess.run')
    def test_detect_container_none(self, mock_subprocess, mock_exists, scanner):
        """Test no container detection"""
        mock_exists.return_value = False
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_subprocess.return_value = mock_result

        container_type = scanner._detect_container()
        assert container_type == ContainerType.BARE_METAL

    def test_get_basic_os_info(self, scanner):
        """Test basic OS information retrieval"""
        os_info = scanner.get_os_info()

        assert 'system' in os_info
        assert 'release' in os_info
        assert 'version' in os_info
        assert 'machine' in os_info
        assert 'architecture' in os_info

    @patch('backend.core.system_scanner.HAS_CPUINFO')
    @patch('cpuinfo.get_cpu_info')
    def test_get_cpu_info_with_cpuinfo(self, mock_get_cpu_info, mock_has_cpuinfo, scanner):
        """Test CPU info retrieval with cpuinfo library"""
        mock_has_cpuinfo = True
        mock_get_cpu_info.return_value = {
            'brand_raw': 'Intel Core i7',
            'arch': 'x86_64',
            'bits': 64,
            'count': 8
        }

        cpu_info = scanner.get_cpu_info()

        assert isinstance(cpu_info, CPUInfo)
        assert cpu_info.brand == 'Intel Core i7'
        assert cpu_info.arch == 'x86_64'
        assert cpu_info.bits == 64

    @patch('backend.core.system_scanner.HAS_PSUTIL')
    @patch('psutil.cpu_count')
    @patch('psutil.cpu_freq')
    def test_get_cpu_info_with_psutil(self, mock_cpu_freq, mock_cpu_count, mock_has_psutil, scanner):
        """Test CPU info retrieval with psutil library"""
        mock_has_psutil = True
        mock_cpu_count.side_effect = [4, 8]  # physical, logical
        mock_freq = MagicMock()
        mock_freq.max = 3.5
        mock_freq.min = 0.8
        mock_freq.current = 2.1
        mock_cpu_freq.return_value = mock_freq

        # Mock cpuinfo not available
        with patch('backend.core.system_scanner.HAS_CPUINFO', False):
            cpu_info = scanner.get_cpu_info()

            assert cpu_info.count_physical == 4
            assert cpu_info.count_logical == 8
            assert cpu_info.max_frequency == 3.5
            assert cpu_info.current_frequency == 2.1

    @patch('backend.core.system_scanner.HAS_PSUTIL')
    @patch('psutil.virtual_memory')
    def test_get_memory_info(self, mock_virtual_memory, mock_has_psutil, scanner):
        """Test memory information retrieval"""
        mock_has_psutil = True
        mock_mem = MagicMock()
        mock_mem.total = 16 * 1024**3  # 16 GB
        mock_mem.available = 8 * 1024**3  # 8 GB
        mock_mem.used = 8 * 1024**3
        mock_mem.percent = 50.0
        mock_virtual_memory.return_value = mock_mem

        memory_info = scanner.get_memory_info()

        assert isinstance(memory_info, MemoryInfo)
        assert memory_info.total == 16 * 1024**3
        assert memory_info.available == 8 * 1024**3
        assert memory_info.used == 8 * 1024**3

    @patch('backend.core.system_scanner.HAS_GPUTIL')
    @patch('GPUtil.getGPUs')
    def test_get_gpu_info_with_gputil(self, mock_get_gpus, mock_has_gputil, scanner):
        """Test GPU information retrieval with GPUtil"""
        mock_has_gputil = True
        mock_gpu = MagicMock()
        mock_gpu.id = 0
        mock_gpu.name = 'NVIDIA GeForce RTX 3080'
        mock_gpu.memoryTotal = 10240  # MB
        mock_gpu.memoryFree = 8192
        mock_gpu.memoryUsed = 2048
        mock_gpu.memoryUtil = 20.0
        mock_gpu.temperature = 65
        mock_gpu.driver = '470.42.01'
        mock_get_gpus.return_value = [mock_gpu]

        gpu_info_list = scanner.get_gpu_info()

        assert len(gpu_info_list) == 1
        gpu = gpu_info_list[0]
        assert isinstance(gpu, GPUInfo)
        assert gpu.name == 'NVIDIA GeForce RTX 3080'
        assert gpu.memory_total == 10240
        assert gpu.temperature == 65

    @patch('backend.core.system_scanner.HAS_PSUTIL')
    @patch('psutil.disk_partitions')
    @patch('psutil.disk_usage')
    def test_get_disk_info(self, mock_disk_usage, mock_disk_partitions, mock_has_psutil, scanner):
        """Test disk information retrieval"""
        mock_has_psutil = True

        mock_partition = MagicMock()
        mock_partition.device = '/dev/sda1'
        mock_partition.mountpoint = '/'
        mock_partition.fstype = 'ext4'
        mock_disk_partitions.return_value = [mock_partition]

        mock_usage = MagicMock()
        mock_usage.total = 500 * 1024**3  # 500 GB
        mock_usage.free = 200 * 1024**3    # 200 GB
        mock_usage.used = 300 * 1024**3
        mock_usage.percent = 60.0
        mock_disk_usage.return_value = mock_usage

        disk_info_list = scanner.get_disk_info()

        assert len(disk_info_list) == 1
        disk = disk_info_list[0]
        assert isinstance(disk, DiskInfo)
        assert disk.mountpoint == '/'
        assert disk.total == 500 * 1024**3
        assert disk.free == 200 * 1024**3

    def test_detect_python_runtime(self, scanner):
        """Test Python runtime detection"""
        runtime_info = scanner.detect_python_runtime()

        assert isinstance(runtime_info, RuntimeInfo)
        assert 'python' in runtime_info.versions
        assert runtime_info.versions['python']['version'] is not None

    @patch('subprocess.run')
    def test_detect_node_runtime(self, mock_subprocess, scanner):
        """Test Node.js runtime detection"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b'v18.17.0\n'
        mock_subprocess.return_value = mock_result

        runtime_info = scanner.detect_node_runtime()

        assert runtime_info.versions['node']['version'] == '18.17.0'

    @patch('subprocess.run')
    def test_detect_java_runtime(self, mock_subprocess, scanner):
        """Test Java runtime detection"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b'openjdk version "17.0.8" 2023-07-18\n'
        mock_subprocess.return_value = mock_result

        runtime_info = scanner.detect_java_runtime()

        assert '17.0.8' in runtime_info.versions['java']['version']

    def test_scan_all(self, scanner):
        """Test full system scan"""
        result = scanner.scan_all()

        assert 'os' in result
        assert 'cpu' in result
        assert 'memory' in result
        assert 'disk' in result
        assert 'gpu' in result
        assert 'runtime' in result
        assert 'container' in result

    def test_to_dict(self, scanner):
        """Test conversion to dictionary"""
        result = scanner.to_dict()

        assert isinstance(result, dict)
        assert 'os' in result
        assert 'cpu' in result
        assert 'memory' in result

    @patch('subprocess.run')
    def test_subprocess_error_handling(self, mock_subprocess, scanner):
        """Test graceful handling of subprocess errors"""
        mock_subprocess.side_effect = Exception("Command failed")

        # Should not raise exception
        runtime_info = scanner.detect_node_runtime()
        assert runtime_info is not None

    def test_fallback_values(self, scanner):
        """Test fallback values when libraries are not available"""
        # Mock all libraries as unavailable
        with patch('backend.core.system_scanner.HAS_PSUTIL', False), \
             patch('backend.core.system_scanner.HAS_GPUTIL', False), \
             patch('backend.core.system_scanner.HAS_CPUINFO', False):

            cpu_info = scanner.get_cpu_info()
            memory_info = scanner.get_memory_info()
            gpu_info = scanner.get_gpu_info()

            assert cpu_info.brand == 'Unknown'
            assert memory_info.total == 0
            assert len(gpu_info) == 0