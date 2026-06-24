from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from backend.api.main import app
from backend.api.dependencies import get_system_scanner


@pytest.fixture
def mock_scanner():
    scanner = MagicMock()
    scanner.scan_all = AsyncMock(return_value={
        "platform": {"system": "Linux", "release": "5.15.0", "machine": "x86_64"},
        "cpu": {
            "brand": "Intel Core i7",
            "physical_cores": 4,
            "logical_cores": 8,
        },
        "memory": {
            "total": 16777216000,
            "available": 8388608000,
        },
        "gpu": {
            "available": True,
            "devices": [{"name": "NVIDIA GTX 1060", "memory_mb": 6144}],
            "cuda": "11.8",
        },
        "runtime_versions": {
            "python": {"version": "3.9.16", "location": "/usr/bin/python3"}
        },
    })
    scanner.detect_runtime_versions.return_value = {
        "python": {"version": "3.9.16", "location": "/usr/bin/python3"},
        "nodejs": None,
        "java": None,
    }
    scanner.detect_gpu_info.return_value = {
        "available": True,
        "devices": [{"name": "NVIDIA GTX 1060", "memory_mb": 6144}],
        "cuda": "11.8",
    }
    app.dependency_overrides[get_system_scanner] = lambda: scanner
    yield scanner
    app.dependency_overrides.pop(get_system_scanner, None)


class TestSystemInfo:
    def test_get_system_info_success(self, client, mock_scanner):
        response = client.get("/api/v1/system/info")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "system" in data
        assert data["system"]["os"] == "Linux 5.15.0"
        assert data["system"]["python"] == "3.9.16"
        mock_scanner.scan_all.assert_called_once()

    def test_get_system_info_detailed(self, client, mock_scanner):
        response = client.get("/api/v1/system/info?detailed=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert data["data"]["platform"]["system"] == "Linux"

    def test_get_system_info_handles_scanner_error(self, client, mock_scanner):
        mock_scanner.scan_all.side_effect = Exception("Scan failed")
        response = client.get("/api/v1/system/info")
        assert response.status_code == 500
        data = response.json()
        assert "Internal server error" in data["error"]["message"]

    def test_get_system_info_handles_value_error(self, client, mock_scanner):
        mock_scanner.scan_all.side_effect = ValueError("Invalid scan data")
        response = client.get("/api/v1/system/info")
        assert response.status_code == 400

    def test_get_system_info_no_gpu(self, client, mock_scanner):
        mock_scanner.scan_all = AsyncMock(return_value={
            "platform": {"system": "Linux", "release": "5.15.0", "machine": "x86_64"},
            "cpu": {"brand": "Intel Core i7", "physical_cores": 4, "logical_cores": 8},
            "memory": {"total": 16777216000, "available": 8388608000},
            "gpu": {"available": False, "devices": []},
            "runtime_versions": {
                "python": {"version": "3.9.16", "location": "/usr/bin/python3"}
            },
        })
        response = client.get("/api/v1/system/info")
        assert response.status_code == 200
        data = response.json()
        assert data["system"]["gpu"] is None


class TestHealthCheck:
    def test_health_check_success(self, client):
        with patch("backend.database.models.check_db_health") as mock_db_health:
            mock_db_health.return_value = {"status": "healthy"}
            response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "checks" in data
        assert "database" in data["checks"]

    def test_health_check_db_unhealthy(self, client):
        with patch("backend.database.models.check_db_health") as mock_db_health:
            mock_db_health.return_value = {
                "status": "unhealthy",
                "error": "Connection failed",
            }
            response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"]["status"] == "unhealthy"

    def test_health_check_db_exception(self, client):
        with patch(
            "backend.database.models.check_db_health", side_effect=Exception("DB error")
        ):
            response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"

    def test_health_check_with_redis(self, client):
        with patch("backend.database.models.check_db_health") as mock_db_health, patch.dict(
            "os.environ", {"REDIS_URL": "redis://localhost:6379"}
        ), patch("redis.from_url") as mock_redis:
            mock_db_health.return_value = {"status": "healthy"}
            mock_redis_instance = MagicMock()
            mock_redis.return_value = mock_redis_instance
            response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "redis" in data["checks"]


class TestSystemCheckCompatibility:
    def test_check_compatibility_success(self, client, mock_scanner):
        response = client.post(
            "/api/v1/system/check-compatibility",
            json={
                "requirements": [
                    {"type": "os", "minimum": {"name": "linux"}},
                    {"type": "memory", "minimum": {"gb": 4}},
                ],
                "packages": None,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "results" in data

    def test_check_compatibility_gpu_required(self, client, mock_scanner):
        response = client.post(
            "/api/v1/system/check-compatibility",
            json={
                "requirements": [
                    {"type": "gpu", "minimum": {"cuda": "11.0"}, "required": True}
                ]
            },
        )
        assert response.status_code == 200

    def test_check_compatibility_empty_requirements(self, client, mock_scanner):
        response = client.post(
            "/api/v1/system/check-compatibility",
            json={"requirements": [], "packages": None},
        )
        assert response.status_code == 200

    def test_check_compatibility_invalid_payload(self, client):
        response = client.post(
            "/api/v1/system/check-compatibility",
            json={"requirements": "invalid"},
        )
        assert response.status_code == 422


class TestGPUInfo:
    def test_get_gpu_info_success(self, client, mock_scanner):
        response = client.get("/api/v1/system/gpu/info")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "gpu" in data


class TestRuntimeInfo:
    def test_get_runtime_info_python(self, client, mock_scanner):
        response = client.get("/api/v1/system/runtime/python")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["runtime"] == "python"

    def test_get_runtime_info_not_found(self, client, mock_scanner):
        response = client.get("/api/v1/system/runtime/nonexistent_runtime")
        assert response.status_code == 404


class TestBenchmarks:
    def test_benchmarks_success(self, client, mock_scanner):
        with patch("backend.api.routes.system._benchmark_cpu") as mock_cpu, \
             patch("backend.api.routes.system._benchmark_memory") as mock_mem, \
             patch("backend.api.routes.system._benchmark_disk") as mock_disk, \
             patch("backend.api.routes.system._benchmark_gpu") as mock_gpu, \
             patch("backend.api.routes.system._compare_benchmark_results") as mock_compare:
            mock_cpu.return_value = {"matrix_multiply_single": {"time_seconds": 0.5}}
            mock_mem.return_value = {"total_gb": 16.0}
            mock_disk.return_value = {"read_speed_mbps": 500.0}
            mock_gpu.return_value = {"matrix_multiply_2000": {"time_seconds": 0.1}}
            mock_compare.return_value = {"summary": "above_average"}
            response = client.get("/api/v1/system/benchmarks")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "benchmarks" in data

    def test_benchmarks_comprehensive(self, client, mock_scanner):
        with patch("backend.api.routes.system._benchmark_cpu") as mock_cpu, \
             patch("backend.api.routes.system._benchmark_memory") as mock_mem, \
             patch("backend.api.routes.system._benchmark_disk") as mock_disk, \
             patch("backend.api.routes.system._benchmark_gpu") as mock_gpu, \
             patch("backend.api.routes.system._benchmark_network") as mock_net, \
             patch("backend.api.routes.system._benchmark_python") as mock_py, \
             patch("backend.api.routes.system._benchmark_cpu_multicore") as mock_multi, \
             patch("backend.api.routes.system._compare_benchmark_results") as mock_compare:
            mock_cpu.return_value = {"matrix_multiply_single": {"time_seconds": 0.5}}
            mock_mem.return_value = {"total_gb": 16.0}
            mock_disk.return_value = {"read_speed_mbps": 500.0}
            mock_gpu.return_value = {"matrix_multiply_2000": {"time_seconds": 0.1}}
            mock_net.return_value = {"dns_lookup_ms": 10.0}
            mock_py.return_value = {"list_comprehension_ms": 50.0}
            mock_multi.return_value = {"threads_1": {"time_seconds": 0.5}}
            mock_compare.return_value = {"summary": "above_average"}
            response = client.get("/api/v1/system/benchmarks?comprehensive=true")
        assert response.status_code == 200


class TestAnalyzeEnvironment:
    def test_analyze_requirements_txt(self, client):
        content = "requests>=2.25.0\nflask==2.3.3\n"
        response = client.post(
            "/api/v1/system/analyze-environment",
            files={"file": ("requirements.txt", content, "text/plain")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_analyze_package_json(self, client):
        content = '{"dependencies": {"express": "^4.18.0"}}'
        response = client.post(
            "/api/v1/system/analyze-environment",
            files={"file": ("package.json", content, "application/json")},
        )
        assert response.status_code == 200

    def test_analyze_environment_no_file(self, client):
        response = client.post("/api/v1/system/analyze-environment")
        assert response.status_code == 422
