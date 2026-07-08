"""Tests for /api/v1/index/* endpoints (offline index management)."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    app = pytest.importorskip("backend.api.main").app
    with TestClient(app) as c:
        yield c


class TestIndexStatus:
    """GET /api/v1/index/status"""

    def test_status_empty_when_no_indexes(self, client):
        resp = client.get("/api/v1/index/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["indexes"] == []

    def test_status_with_ecosystem_not_found(self, client):
        resp = client.get("/api/v1/index/status?ecosystem=nonexistent")
        assert resp.status_code == 404

    def test_status_filters_by_ecosystem(self, client):
        with patch("backend.api.routes.index.index_status") as mock_status:
            mock_status.return_value = {
                "ecosystem": "pypi",
                "path": "/tmp/test.db",
                "size_bytes": 1024,
                "packages": 100,
                "versions": 500,
                "metadata": {"index_version": "1"},
            }
            resp = client.get("/api/v1/index/status?ecosystem=pypi")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["indexes"]) == 1
            assert data["indexes"][0]["ecosystem"] == "pypi"


class TestIndexPull:
    """POST /api/v1/index/pull"""

    def test_rejects_bad_url(self, client):
        resp = client.post("/api/v1/index/pull", json={"url": "not-a-url"})
        assert resp.status_code == 400
        assert "URL must start with" in resp.text

    def test_rejects_empty_body(self, client):
        resp = client.post("/api/v1/index/pull", json={})
        assert resp.status_code == 422

    def test_rejects_missing_field(self, client):
        resp = client.post("/api/v1/index/pull", json={"ecosystem": "pypi"})
        assert resp.status_code == 422

    def test_network_error_returns_502(self, client):
        resp = client.post(
            "/api/v1/index/pull",
            json={"url": "http://nonexistent-domain-xyz.example/db.db"},
        )
        assert resp.status_code == 502
        assert "Download failed" in resp.text


class TestIndexBuild:
    """POST /api/v1/index/build"""

    def test_rejects_empty_packages(self, client):
        resp = client.post(
            "/api/v1/index/build",
            json={"ecosystem": "pypi", "packages": []},
        )
        assert resp.status_code == 400
        assert "No packages" in resp.text

    def test_rejects_missing_ecosystem(self, client):
        resp = client.post("/api/v1/index/build", json={"packages": [{"name": "test"}]})
        assert resp.status_code == 422

    def test_successful_build(self, client):
        with patch("backend.api.routes.index.create_or_update_index") as mock_create:
            mock_create.return_value = 1
            with patch("backend.api.routes.index.index_status") as mock_status:
                mock_status.return_value = {
                    "ecosystem": "pypi",
                    "path": "/tmp/pypi.db",
                    "size_bytes": 512,
                    "packages": 1,
                    "versions": 2,
                    "metadata": {"index_version": "1", "updated_at": "2026-01-01T00:00:00Z"},
                }
                resp = client.post(
                    "/api/v1/index/build",
                    json={
                        "ecosystem": "pypi",
                        "packages": [
                            {
                                "name": "requests",
                                "versions": [
                                    {
                                        "version": "2.31.0",
                                        "release_date": "2023-05-22",
                                        "requires_python": ">=3.7",
                                        "dependencies": {"urllib3": ">=1.21.1,<3"},
                                    }
                                ],
                            }
                        ],
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "success"
                assert data["ecosystem"] == "pypi"
                assert data["packages_indexed"] == 1
                mock_create.assert_called_once()
