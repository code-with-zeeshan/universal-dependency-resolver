from unittest.mock import AsyncMock, MagicMock

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
