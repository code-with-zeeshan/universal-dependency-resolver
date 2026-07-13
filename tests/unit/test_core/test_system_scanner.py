from unittest.mock import MagicMock, patch

import pytest

from backend.core.system_scanner import (
    ContainerType,
    OSType,
    SystemScanner,
)


class TestSystemScanner:
    @pytest.fixture
    def scanner(self):
        return SystemScanner()

    def test_initialization(self, scanner):
        assert scanner.cache_ttl == 300
        assert scanner.enable_cache is True
        assert scanner.parallel_scan is True
        assert scanner.scan_network is True
        assert scanner.scan_packages is True
        assert scanner.deep_scan is False
        assert scanner.system_info == {}

    # -- _safe_read_file ----------------------------------------------------

    def test_safe_read_file_success(self, scanner, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world\nline2")
        assert scanner._safe_read_file(str(f)) == "hello world\nline2"

    def test_safe_read_file_not_found(self, scanner, tmp_path):
        assert scanner._safe_read_file(tmp_path / "nope.txt") is None

    def test_safe_read_file_permission_error(self, scanner, tmp_path):
        f = tmp_path / "noaccess.txt"
        f.write_text("secret")
        f.chmod(0o000)
        try:
            result = scanner._safe_read_file(str(f))
            assert result is None
        finally:
            f.chmod(0o644)

    # -- _get_cache_key -----------------------------------------------------

    @patch("platform.system", return_value="Linux")
    @patch("platform.node", return_value="host1")
    @patch("platform.release", return_value="6.2.0")
    @patch("platform.machine", return_value="x86_64")
    def test_get_cache_key_consistent(
        self, mock_machine, mock_release, mock_node, mock_system, scanner
    ):
        k1 = scanner._get_cache_key("cpu")
        k2 = scanner._get_cache_key("cpu")
        assert k1 == k2

    @patch("platform.system", return_value="Linux")
    @patch("platform.node", return_value="host1")
    @patch("platform.release", return_value="6.2.0")
    @patch("platform.machine", return_value="x86_64")
    def test_get_cache_key_diff_category(
        self, mock_machine, mock_release, mock_node, mock_system, scanner
    ):
        k_cpu = scanner._get_cache_key("cpu")
        k_mem = scanner._get_cache_key("memory")
        assert k_cpu != k_mem

    # -- _set_cache / _get_cached ------------------------------------------

    def test_cache_hit(self, scanner):
        scanner._set_cache("k1", {"data": 42})
        assert scanner._get_cached("k1") == {"data": 42}

    def test_cache_disabled(self, scanner):
        scanner.enable_cache = False
        scanner._set_cache("k1", 1)
        assert scanner._get_cached("k1") is None

    def test_cache_expiry(self, scanner):
        scanner.cache_ttl = -1  # expired immediately
        scanner._set_cache("k1", "val")
        assert scanner._get_cached("k1") is None

    def test_cache_miss(self, scanner):
        assert scanner._get_cached("nonexistent") is None

    # -- _check_output ------------------------------------------------------

    @patch.object(SystemScanner, "_run_subprocess")
    def test_check_output_success(self, mock_run, scanner):
        from subprocess import CompletedProcess

        mock_run.return_value = CompletedProcess(["echo", "ok"], 0, stdout="ok\n")
        assert scanner._check_output(["echo", "ok"]) == "ok"

    @patch.object(SystemScanner, "_run_subprocess")
    def test_check_output_failure(self, mock_run, scanner):
        from subprocess import CompletedProcess

        mock_run.return_value = CompletedProcess(["false"], 1, stdout="")
        assert scanner._check_output(["false"]) is None

    @patch.object(SystemScanner, "_run_subprocess")
    def test_check_output_none(self, mock_run, scanner):
        mock_run.return_value = None
        assert scanner._check_output(["missing"]) is None

    @patch.object(SystemScanner, "_run_subprocess")
    def test_check_output_merge_stderr(self, mock_run, scanner):
        from subprocess import CompletedProcess

        mock_run.return_value = CompletedProcess(["cmd"], 0, stdout="", stderr="warn\n")
        assert scanner._check_output(["cmd"], merge_stderr=True) == "warn"

    # -- _run_subprocess ----------------------------------------------------

    @patch("subprocess.run")
    def test_run_subprocess_file_not_found(self, mock_run, scanner):
        mock_run.side_effect = FileNotFoundError()
        assert scanner._run_subprocess(["nonexistent"]) is None

    @patch("subprocess.run")
    def test_run_subprocess_timeout(self, mock_run, scanner):
        from subprocess import TimeoutExpired

        mock_run.side_effect = TimeoutExpired("cmd", 10)
        assert scanner._run_subprocess(["sleep", "100"]) is None

    @patch("subprocess.run")
    def test_run_subprocess_permission_error(self, mock_run, scanner):
        mock_run.side_effect = PermissionError()
        assert scanner._run_subprocess(["restricted"]) is None

    # -- _parse_dotnet_sdks / _parse_dotnet_runtimes ------------------------

    DOTNET_INFO_SAMPLE = r"""
.NET SDK:
 Version: 8.0.100

.NET SDKs installed:
  6.0.420 [/usr/share/dotnet/sdk]
  7.0.410 [/usr/share/dotnet/sdk]
  8.0.100 [/usr/share/dotnet/sdk]

.NET runtimes installed:
  Microsoft.AspNetCore.App 6.0.28 [/usr/share/dotnet/shared]
  Microsoft.AspNetCore.App 7.0.18 [/usr/share/dotnet/shared]
  Microsoft.NETCore.App 8.0.0 [/usr/share/dotnet/shared]

Other:
  random line
"""

    def test_parse_dotnet_sdks(self, scanner):
        versions = scanner._parse_dotnet_sdks(self.DOTNET_INFO_SAMPLE)
        assert versions == ["6.0.420", "7.0.410", "8.0.100"]

    def test_parse_dotnet_runtimes(self, scanner):
        versions = scanner._parse_dotnet_runtimes(self.DOTNET_INFO_SAMPLE)
        assert versions == ["6.0.28", "7.0.18", "8.0.0"]

    def test_parse_dotnet_sdks_empty(self, scanner):
        assert scanner._parse_dotnet_sdks("no .NET SDKs installed:") == []

    def test_parse_dotnet_runtimes_empty(self, scanner):
        assert scanner._parse_dotnet_runtimes("not found") == []

    @patch("platform.system")
    def test_detect_os_type_linux(self, mock_system, scanner):
        mock_system.return_value = "Linux"
        os_type = scanner._detect_os_type()
        assert os_type == OSType.LINUX

    @patch("platform.system")
    def test_detect_os_type_windows(self, mock_system, scanner):
        mock_system.return_value = "Windows"
        os_type = scanner._detect_os_type()
        assert os_type == OSType.WINDOWS

    @patch("platform.system")
    def test_detect_os_type_macos(self, mock_system, scanner):
        mock_system.return_value = "Darwin"
        os_type = scanner._detect_os_type()
        assert os_type == OSType.MACOS

    @patch("platform.system")
    def test_detect_os_type_unknown(self, mock_system, scanner):
        mock_system.return_value = "UnknownOS"
        os_type = scanner._detect_os_type()
        assert os_type == OSType.UNKNOWN

    @patch("platform.system", return_value="Windows")
    @patch("os.path.exists")
    def test_detect_container_docker(self, mock_exists, mock_system, scanner):
        mock_exists.return_value = True
        container_info = scanner.detect_container_info()
        assert container_info["type"] == ContainerType.DOCKER.value
        assert container_info["detected"] is True

    @patch("backend.core.system_scanner.SystemScanner._detect_vm", return_value=None)
    @patch("platform.system", return_value="Windows")
    @patch("os.path.exists")
    def test_detect_container_bare_metal(self, mock_exists, mock_system, mock_detect_vm, scanner):
        mock_exists.return_value = False
        container_info = scanner.detect_container_info()
        assert container_info["type"] == ContainerType.BARE_METAL.value
        assert container_info["detected"] is False

    def test_detect_platform_info(self, scanner):
        os_info = scanner.detect_platform_info()
        assert "system" in os_info
        assert "release" in os_info
        assert "version" in os_info
        assert "machine" in os_info
        assert "architecture" in os_info
        assert "os_type" in os_info

    @patch("backend.core.system_scanner.HAS_PSUTIL", True)
    @patch("backend.core.system_scanner.psutil.cpu_count")
    @patch("backend.core.system_scanner.psutil.cpu_freq")
    def test_detect_cpu_info_with_cpuinfo(self, mock_cpu_freq, mock_cpu_count, scanner):
        mock_cpu_count.side_effect = [8, 8]
        mock_freq = MagicMock()
        mock_freq.max = 3.5
        mock_freq.min = 0.8
        mock_freq.current = 2.1
        mock_cpu_freq.return_value = mock_freq

        mock_cpuinfo = MagicMock()
        mock_cpuinfo.get_cpu_info.return_value = {
            "brand_raw": "Intel Core i7",
            "arch": "x86_64",
            "bits": 64,
            "count": 8,
        }
        with patch.dict("sys.modules", {"cpuinfo": mock_cpuinfo}):
            cpu_info = scanner.detect_cpu_info()
        assert cpu_info["brand"] == "Intel Core i7"
        assert cpu_info["arch"] == "x86_64"
        assert cpu_info["bits"] == 64

    @patch("backend.core.system_scanner.HAS_PSUTIL", True)
    @patch("backend.core.system_scanner.psutil.cpu_count")
    @patch("backend.core.system_scanner.psutil.cpu_freq")
    def test_detect_cpu_info_with_psutil(self, mock_cpu_freq, mock_cpu_count, scanner):
        mock_cpu_count.side_effect = [4, 8]
        mock_freq = MagicMock()
        mock_freq.max = 3.5
        mock_freq.min = 0.8
        mock_freq.current = 2.1
        mock_cpu_freq.return_value = mock_freq

        cpu_info = scanner.detect_cpu_info()

        assert cpu_info["max_frequency"] == 3.5
        assert cpu_info["current_frequency"] == 2.1

    @patch("backend.core.system_scanner.HAS_PSUTIL", True)
    @patch("psutil.virtual_memory")
    def test_detect_memory_info(self, mock_virtual_memory, scanner):
        mock_mem = MagicMock()
        mock_mem.total = 16 * 1024**3
        mock_mem.available = 8 * 1024**3
        mock_mem.used = 8 * 1024**3
        mock_mem.free = 8 * 1024**3
        mock_mem.percent = 50.0
        mock_virtual_memory.return_value = mock_mem

        memory_info = scanner.detect_memory_info()

        assert isinstance(memory_info, dict)
        assert memory_info["total"] == 16 * 1024**3
        assert memory_info["available"] == 8 * 1024**3
        assert memory_info["used"] == 8 * 1024**3

    @patch("backend.core.detectors.gpu.GPUtil", create=True)
    @patch("backend.core.detectors.gpu.HAS_GPUTIL", True)
    def test_detect_gpu_info_with_gputil(self, mock_gputil_module, scanner):
        mock_gpu = MagicMock()
        mock_gpu.id = 0
        mock_gpu.name = "NVIDIA GeForce RTX 3080"
        mock_gpu.memoryTotal = 10240
        mock_gpu.memoryFree = 8192
        mock_gpu.memoryUsed = 2048
        mock_gpu.memoryUtil = 20.0
        mock_gpu.load = 0.2
        mock_gpu.temperature = 65
        mock_gpu.driver = "470.42.01"
        mock_gputil_module.getGPUs.return_value = [mock_gpu]

        gpu_info = scanner.detect_gpu_info()

        assert gpu_info["available"] is True
        assert len(gpu_info["devices"]) == 1
        gpu = gpu_info["devices"][0]
        assert gpu["name"] == "NVIDIA GeForce RTX 3080"
        assert gpu["memory_total"] == 10240
        assert gpu["temperature"] == 65

    @patch("backend.core.system_scanner.HAS_PSUTIL", True)
    @patch("psutil.disk_partitions")
    @patch("psutil.disk_usage")
    def test_detect_disk_info(self, mock_disk_usage, mock_disk_partitions, scanner):
        mock_partition = MagicMock()
        mock_partition.device = "/dev/sda1"
        mock_partition.mountpoint = "/"
        mock_partition.fstype = "ext4"
        mock_disk_partitions.return_value = [mock_partition]

        mock_usage = MagicMock()
        mock_usage.total = 500 * 1024**3
        mock_usage.free = 200 * 1024**3
        mock_usage.used = 300 * 1024**3
        mock_usage.percent = 60.0
        mock_disk_usage.return_value = mock_usage

        disk_info = scanner.detect_disk_info()

        assert len(disk_info["partitions"]) == 1
        disk = disk_info["partitions"][0]
        assert disk["mountpoint"] == "/"
        assert disk["total"] == 500 * 1024**3
        assert disk["free"] == 200 * 1024**3

    def test_detect_runtime_versions_python(self, scanner):
        runtime_info = scanner.detect_runtime_versions()
        assert "python" in runtime_info
        assert runtime_info["python"]["version"] is not None

    @patch("platform.architecture")
    @patch.object(SystemScanner, "_run_subprocess")
    def test_detect_runtime_versions_node(self, mock_run_subprocess, mock_arch, scanner):
        from subprocess import CompletedProcess

        mock_arch.return_value = ("64bit", "ELF")

        def side_effect(cmd, *args, **kwargs):
            if cmd == ["node", "--version"]:
                return CompletedProcess(cmd, 0, stdout="v18.17.0\n")
            if cmd == ["npm", "--version"]:
                return CompletedProcess(cmd, 0, stdout="9.6.7\n")

        mock_run_subprocess.side_effect = side_effect

        runtime_info = scanner.detect_runtime_versions()
        assert runtime_info["nodejs"]["version"] == "18.17.0"

    @patch("platform.architecture")
    @patch.object(SystemScanner, "_run_subprocess")
    def test_detect_runtime_versions_java(self, mock_run_subprocess, mock_arch, scanner):
        from subprocess import CompletedProcess

        mock_arch.return_value = ("64bit", "ELF")
        mock_run_subprocess.return_value = CompletedProcess(
            ["java", "-version"], 0, stdout="", stderr='openjdk version "17.0.8" 2023-07-18\n'
        )
        runtime_info = scanner.detect_runtime_versions()
        assert "java" in runtime_info
        assert "17.0.8" in runtime_info["java"]["version"]

    def test_scan_all(self, scanner):
        import asyncio

        with (
            patch.object(scanner, "detect_platform_info", return_value={}),
            patch.object(scanner, "detect_cpu_info", return_value={}),
            patch.object(scanner, "detect_memory_info", return_value={}),
            patch.object(scanner, "detect_gpu_info", return_value={}),
            patch.object(scanner, "detect_disk_info", return_value={}),
            patch.object(scanner, "detect_network_info", return_value={}),
            patch.object(scanner, "detect_container_info", return_value={}),
            patch.object(scanner, "detect_runtime_versions", return_value={}),
            patch.object(scanner, "detect_installed_packages", return_value={}),
            patch.object(scanner, "get_performance_metrics", return_value={}),
            patch.object(scanner, "detect_system_capabilities", return_value={}),
        ):
            result = asyncio.run(scanner.scan_all())

        assert "platform" in result
        assert "cpu" in result
        assert "memory" in result
        assert "disk" in result
        assert "gpu" in result
        assert "runtime_versions" in result
        assert "container" in result
        assert "scan_metadata" in result

    def test_export_scan_results(self, scanner):
        scanner.system_info = {"platform": {}, "cpu": {}, "memory": {}}
        result = scanner.export_scan_results(format="dict")
        assert isinstance(result, dict)
        assert "platform" in result
        assert "cpu" in result
        assert "memory" in result

    @patch("platform.architecture")
    @patch("subprocess.check_output")
    def test_subprocess_error_handling(self, mock_check_output, mock_arch, scanner):
        mock_arch.return_value = ("64bit", "ELF")
        mock_check_output.side_effect = Exception("Command failed")
        runtime_info = scanner.detect_runtime_versions()
        assert isinstance(runtime_info, dict)
        assert "python" in runtime_info

    def test_fallback_values(self, scanner):
        with (
            patch("backend.core.system_scanner.HAS_PSUTIL", False),
            patch("backend.core.detectors.gpu.HAS_GPUTIL", False),
            patch.dict("sys.modules", {"cpuinfo": None}),
            patch("platform.system", return_value="UnknownOS"),
        ):
            cpu_info = scanner.detect_cpu_info()
            memory_info = scanner.detect_memory_info()
            gpu_info = scanner.detect_gpu_info()

            assert cpu_info.get("brand", "Unknown") == "Unknown"
            assert memory_info == {}
            assert gpu_info["available"] is False
            assert len(gpu_info["devices"]) == 0
