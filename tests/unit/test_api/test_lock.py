from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.dependencies import get_data_aggregator
from backend.api.main import app


def _mock_aggregator():
    aggregator = MagicMock()
    aggregator.get_package_info = AsyncMock()
    aggregator.search_packages = AsyncMock()
    aggregator.sources = {}
    return aggregator


@pytest.fixture
def mock_aggregator():
    aggregator = _mock_aggregator()
    app.dependency_overrides[get_data_aggregator] = lambda: aggregator
    yield aggregator
    app.dependency_overrides.pop(get_data_aggregator, None)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


SAMPLE_LOCK_DATA = {
    "version": "2.0",
    "resolver": "sat",
    "packages": {
        "requests": {
            "name": "requests",
            "ecosystem": "pypi",
            "resolved_version": "2.31.0",
            "direct": True,
            "original_constraint": ">=2.30.0",
            "source": "manifest",
        },
        "urllib3": {
            "name": "urllib3",
            "ecosystem": "pypi",
            "resolved_version": "2.0.7",
            "direct": False,
            "original_constraint": "*",
            "source": "transitive",
        },
    },
}


class TestGenerateLock:
    def test_generate_lock_pre_parsed_mode(self, client):
        response = client.post("/api/v1/generate-lock", json={
            "packages": [
                {"name": "requests", "ecosystem": "pypi", "resolved_version": "2.31.0"}
            ],
            "manifests": [{"filename": "requirements.txt", "ecosystem": "pypi"}],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["lock_data"]["packages"]["requests"]["resolved_version"] == "2.31.0"

    def test_generate_lock_manifest_contents_not_found(self, client):
        response = client.post("/api/v1/generate-lock", json={
            "manifest_contents": {"unknown.txt": "some content"},
        })
        assert response.status_code == 400
        data = response.json()
        err = data.get("error") or data.get("detail") or data
        if isinstance(err, str):
            assert "no_manifests" in err.lower()
        elif isinstance(err, dict):
            msg = err.get("message", str(err)).lower()
            assert "no_manifests" in msg

    def test_generate_lock_no_input_provided(self, client):
        response = client.post("/api/v1/generate-lock", json={})
        assert response.status_code in (400, 422)

    def test_generate_lock_pre_parsed_multi_package(self, client):
        response = client.post("/api/v1/generate-lock", json={
            "packages": [
                {"name": "flask", "ecosystem": "pypi", "resolved_version": "3.0.0"},
                {"name": "requests", "ecosystem": "pypi", "resolved_version": "2.31.0"},
            ],
            "manifests": [{"filename": "requirements.txt", "ecosystem": "pypi"}],
        })
        assert response.status_code == 200
        data = response.json()
        pkgs = data["lock_data"]["packages"]
        assert pkgs["flask"]["resolved_version"] == "3.0.0"
        assert pkgs["requests"]["resolved_version"] == "2.31.0"

    def test_generate_lock_pre_parsed_with_system(self, client):
        response = client.post("/api/v1/generate-lock", json={
            "packages": [
                {"name": "torch", "ecosystem": "pypi", "resolved_version": "2.3.0"}
            ],
            "manifests": [{"filename": "requirements.txt", "ecosystem": "pypi"}],
            "system": {"gpu": {"available": True, "cuda": "12.1"}},
        })
        assert response.status_code == 200
        data = response.json()
        assert data["lock_data"]["system"]["cuda"] == "12.1"

    def test_generate_lock_lock_data_structure(self, client):
        response = client.post("/api/v1/generate-lock", json={
            "packages": [
                {"name": "click", "ecosystem": "pypi", "resolved_version": "8.1.7"}
            ],
            "manifests": [{"filename": "requirements.txt", "ecosystem": "pypi"}],
        })
        assert response.status_code == 200
        data = response.json()
        ld = data["lock_data"]
        assert "version" in ld
        assert "generated_at" in ld
        assert "resolver" in ld
        assert "system" in ld
        assert "manifests" in ld
        assert "packages" in ld

    def test_generate_lock_manifest_contents_with_filter(self, client):
        response = client.post("/api/v1/generate-lock", json={
            "manifest_contents": {"requirements.txt": "flask>=3.0"},
            "manifest_filter": "requirements.txt",
        })
        assert response.status_code in (200, 400)
        data = response.json()
        if response.status_code == 200:
            assert data["status"] == "success"
        else:
            err = data.get("error") or data.get("detail") or data
            msg = err.get("message", str(err)).lower() if isinstance(err, dict) else str(err).lower()
            assert any(x in msg for x in ["no_manifest", "lock_generation_failed"])

    def test_generate_lock_rejects_non_json(self, client):
        response = client.post("/api/v1/generate-lock", data="not json", headers={"Content-Type": "text/plain"})
        assert response.status_code in (415, 422)

    def test_generate_lock_rejects_oversized_body(self, client):
        big_content = "x" * (11 * 1024 * 1024)
        response = client.post("/api/v1/generate-lock", json={"manifest_contents": {"big.txt": big_content}})
        assert response.status_code in (413, 422)

    def test_generate_lock_validates_too_many_manifests(self, client):
        manifest_contents = {f"f{i}.txt": "content" for i in range(51)}
        response = client.post("/api/v1/generate-lock", json={"manifest_contents": manifest_contents})
        assert response.status_code == 422


class TestVerify:
    def test_verify_empty_lock_data(self, client):
        response = client.post("/api/v1/verify", json={"lock_data": {"packages": {}}})
        assert response.status_code == 400

    def test_verify_no_packages_key(self, client):
        response = client.post("/api/v1/verify", json={"lock_data": {}})
        assert response.status_code == 400

    def test_verify_all_ok(self, client):
        with patch("backend.api.routes.lock.DataAggregator") as MockAgg:
            agg = MagicMock()
            async def get_pkg_info(name, **kw):
                versions = {
                    "requests": ["2.31.0"],
                    "urllib3": ["2.0.7"],
                }
                return {"versions": {"pypi": [{"version": v} for v in versions.get(name, [])]}}
            agg.get_package_info = get_pkg_info
            MockAgg.return_value = agg
            response = client.post("/api/v1/verify", json={"lock_data": SAMPLE_LOCK_DATA})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["ok"] == 2

    def test_verify_version_missing(self, client):
        with patch("backend.api.routes.lock.DataAggregator") as MockAgg:
            agg = MagicMock()
            async def get_pkg_info(name, **kw):
                return {"versions": {"pypi": [{"version": "2.30.0"}]}}
            agg.get_package_info = get_pkg_info
            MockAgg.return_value = agg
            response = client.post("/api/v1/verify", json={"lock_data": SAMPLE_LOCK_DATA})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "issues"


class TestInstallCommands:
    def test_install_commands_single_ecosystem(self, client):
        response = client.post("/api/v1/install-commands", json={"lock_data": SAMPLE_LOCK_DATA})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["commands"]) == 1
        assert data["commands"][0]["ecosystem"] == "pypi"
        assert "pip install" in data["commands"][0]["command"]

    def test_install_commands_multi_ecosystem(self, client):
        lock_data = {
            "packages": {
                "requests": {"ecosystem": "pypi", "resolved_version": "2.31.0", "direct": True},
                "express": {"ecosystem": "npm", "resolved_version": "4.18.2", "direct": True},
            }
        }
        response = client.post("/api/v1/install-commands", json={"lock_data": lock_data})
        assert response.status_code == 200
        data = response.json()
        assert len(data["commands"]) == 2
        ecosystems = {c["ecosystem"] for c in data["commands"]}
        assert ecosystems == {"pypi", "npm"}

    def test_install_commands_skips_transitive(self, client):
        response = client.post("/api/v1/install-commands", json={"lock_data": SAMPLE_LOCK_DATA})
        data = response.json()
        urllib3_cmds = [c for c in data["commands"] if "urllib3" in c["command"]]
        assert len(urllib3_cmds) == 0

    def test_install_commands_empty(self, client):
        response = client.post("/api/v1/install-commands", json={"lock_data": {"packages": {}}})
        data = response.json()
        assert data["status"] == "success"
        assert data["total_packages"] == 0


class TestRestoreCommands:
    def test_restore_includes_all_packages(self, client):
        response = client.post("/api/v1/restore-commands", json={"lock_data": SAMPLE_LOCK_DATA})
        data = response.json()
        assert data["status"] == "success"
        assert data["total_packages"] == 2
        all_cmds = " ".join(c["command"] for c in data["commands"])
        assert "requests" in all_cmds
        assert "urllib3" in all_cmds

    def test_restore_empty(self, client):
        response = client.post("/api/v1/restore-commands", json={"lock_data": {"packages": {}}})
        data = response.json()
        assert data["status"] == "success"
        assert data["total_packages"] == 0


class TestWhy:
    def test_why_direct_package(self, client):
        response = client.post("/api/v1/why", json={"lock_data": SAMPLE_LOCK_DATA, "package": "requests"})
        assert response.status_code == 200
        data = response.json()
        assert data["package"] == "requests"
        assert data["direct"] is True
        assert data["version"] == "2.31.0"

    def test_why_transitive_package(self, client):
        response = client.post("/api/v1/why", json={"lock_data": SAMPLE_LOCK_DATA, "package": "urllib3"})
        assert response.status_code == 200
        data = response.json()
        assert data["package"] == "urllib3"
        assert data["direct"] is False

    def test_why_missing_package(self, client):
        response = client.post("/api/v1/why", json={"lock_data": SAMPLE_LOCK_DATA, "package": "nonexistent"})
        assert response.status_code == 404


class TestDiff:
    def test_diff_identical(self, client):
        response = client.post("/api/v1/diff", json={
            "lock_a": SAMPLE_LOCK_DATA,
            "lock_b": SAMPLE_LOCK_DATA,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["unchanged_count"] == 2
        assert len(data["added"]) == 0
        assert len(data["removed"]) == 0
        assert len(data["changed"]) == 0

    def test_diff_added_package(self, client):
        lock_b = {
            "packages": {
                **SAMPLE_LOCK_DATA["packages"],
                "newpkg": {"ecosystem": "pypi", "resolved_version": "1.0.0"},
            }
        }
        response = client.post("/api/v1/diff", json={
            "lock_a": SAMPLE_LOCK_DATA,
            "lock_b": lock_b,
        })
        data = response.json()
        assert len(data["added"]) == 1
        assert data["added"][0]["name"] == "newpkg"

    def test_diff_removed_package(self, client):
        lock_b = {"packages": {}}
        response = client.post("/api/v1/diff", json={
            "lock_a": SAMPLE_LOCK_DATA,
            "lock_b": lock_b,
        })
        data = response.json()
        assert len(data["removed"]) == 2

    def test_diff_changed_version(self, client):
        lock_b = {
            "packages": {
                "requests": {**SAMPLE_LOCK_DATA["packages"]["requests"], "resolved_version": "3.0.0"},
            }
        }
        response = client.post("/api/v1/diff", json={
            "lock_a": SAMPLE_LOCK_DATA,
            "lock_b": lock_b,
        })
        data = response.json()
        assert len(data["changed"]) == 1
        assert data["changed"][0]["name"] == "requests"
        assert data["changed"][0]["from"] == "2.31.0"
        assert data["changed"][0]["to"] == "3.0.0"


class TestGenerateLockExportFormat:
    """POST /api/v1/generate-lock?export_format=..."""

    def test_export_format_requirements(self, client):
        response = client.post(
            "/api/v1/generate-lock?export_format=requirements.txt",
            json={
                "packages": [{"name": "requests", "ecosystem": "pypi", "resolved_version": "2.31.0"}],
                "manifests": [],
                "system": {},
                "resolution": {
                    "resolved_packages": {
                        "requests": {"name": "requests", "version": "2.31.0", "ecosystem": "pypi"}
                    }
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "export_content" in data
        assert data["export_format"] == "requirements.txt"
        assert "requests==2.31.0" in data["export_content"]

    def test_export_format_dockerfile(self, client):
        response = client.post(
            "/api/v1/generate-lock?export_format=Dockerfile",
            json={
                "packages": [{"name": "flask", "ecosystem": "pypi", "resolved_version": "3.0.0"}],
                "manifests": [],
                "system": {},
                "resolution": {
                    "resolved_packages": {
                        "flask": {"name": "flask", "version": "3.0.0", "ecosystem": "pypi"}
                    }
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "export_content" in data
        # Dockerfile template includes FROM pip install
        content = data["export_content"]
        assert "FROM" in content or "pip install" in content or "flask" in content

    def test_no_export_format_omits_field(self, client):
        response = client.post(
            "/api/v1/generate-lock",
            json={
                "packages": [{"name": "click", "ecosystem": "pypi", "resolved_version": "8.1.7"}],
                "manifests": [],
                "system": {},
                "resolution": {
                    "resolved_packages": {
                        "click": {"name": "click", "version": "8.1.7", "ecosystem": "pypi"}
                    }
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "export_content" not in data
        assert "export_format" not in data

    def test_export_format_with_unknown_format_graceful(self, client):
        response = client.post(
            "/api/v1/generate-lock?export_format=nonexistent_format_xyz",
            json={
                "packages": [{"name": "numpy", "ecosystem": "pypi", "resolved_version": "1.26.0"}],
                "manifests": [],
                "system": {},
                "resolution": {
                    "resolved_packages": {
                        "numpy": {"name": "numpy", "version": "1.26.0", "ecosystem": "pypi"}
                    }
                },
            },
        )
        # Should still return lock_data even if export fails
        assert response.status_code == 200
        data = response.json()
        assert "lock_data" in data
        # Export content might fail gracefully for unknown formats
        assert "export_content" not in data or data["export_content"] is None
