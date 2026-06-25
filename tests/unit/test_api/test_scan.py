"""Tests for the scan API routes (/api/v1/scan/*)."""

import json
import zipfile
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.main import app


@pytest.fixture
def mock_manifest_detector():
    with patch("backend.api.routes.scan.ManifestDetector") as m:
        instance = m.return_value
        instance.detect.return_value = [
            {"filename": "requirements.txt", "ecosystem": "pypi"}
        ]
        instance.parse_all.return_value = [
            {"name": "requests", "ecosystem": "pypi", "constraint": ">=2.28.0", "source": "requirements.txt"}
        ]
        instance.normalize.return_value = [
            {"name": "requests", "ecosystem": "pypi", "constraint": ">=2.28.0", "source": "requirements.txt"}
        ]
        yield m


@pytest.fixture
def mock_aggregator():
    with patch("backend.api.routes.scan.DataAggregator") as m:
        instance = m.return_value
        instance.get_package_info = AsyncMock()
        instance.get_package_info.return_value = {
            "name": "requests",
            "ecosystem": {"pypi": {"system_requirements": {}}},
            "versions": {
                "pypi": [{"version": "2.31.0"}, {"version": "2.28.0"}]
            },
            "dependencies": {
                "pypi": {"all": []}
            },
            "system_requirements": {
                "pypi": []
            },
        }
        yield m


@pytest.fixture
def mock_resolver():
    with patch("backend.api.routes.scan.ConflictResolver") as m:
        instance = m.return_value
        instance.resolve_dependencies.return_value = {
            "status": "success",
            "resolved_packages": {"requests": {"version": "2.31.0", "ecosystem": "pypi"}},
            "warnings": [],
        }
        instance._resolve_with_alternatives.return_value = {
            "status": "success",
            "resolved_packages": {"requests": {"version": "2.31.0", "ecosystem": "pypi"}},
            "warnings": [],
        }
        yield m


@pytest.fixture
def mock_scanner():
    with patch("backend.api.routes.scan.SystemScanner") as m:
        instance = m.return_value
        instance.scan_all = AsyncMock()
        instance.scan_all.return_value = {
            "platform": {"system": "Linux", "release": "6.2.0"},
            "cpu": {"brand": "Intel Core i7", "count": 8},
            "gpu": {"available": False, "devices": [], "cuda": None},
            "runtime_versions": {"python": {"version": "3.11.0"}},
            "memory": {"total": 16 * 1024**3},
        }
        yield m


class TestScanLocal:
    def test_scan_local_missing_directory(self, client):
        response = client.post("/api/v1/scan/local", json={"directory_path": "/nonexistent/path"})
        assert response.status_code == 400
        data = response.json()
        assert "not found" in data["error"]["message"].lower()

    def test_scan_local_success(self, client, tmp_path, mock_manifest_detector, mock_aggregator, mock_resolver, mock_scanner):
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "requirements.txt").write_text("requests>=2.28.0\n")

        response = client.post("/api/v1/scan/local", json={"directory_path": str(project)})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["source"] == "local"
        assert "requests" in str(data["packages"])


class TestScanUpload:
    def test_scan_upload_not_zip(self, client):
        response = client.post("/api/v1/scan/upload", files={"file": ("test.txt", b"hello world", "text/plain")})
        assert response.status_code == 400
        assert "zip" in response.json()["error"]["message"].lower()

    def test_scan_upload_success(self, client, mock_manifest_detector, mock_aggregator, mock_resolver, mock_scanner):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("requirements.txt", "requests>=2.28.0\n")
        buf.seek(0)

        response = client.post("/api/v1/scan/upload", files={"file": ("project.zip", buf, "application/zip")})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["source"] == "upload"


class TestScanGitHub:
    def test_scan_github_invalid_url(self, client):
        response = client.post("/api/v1/scan/github", json={"repo_url": "not-a-url"})
        assert response.status_code == 400

    def test_scan_github_success(self, client, mock_manifest_detector, mock_aggregator, mock_resolver, mock_scanner):
        response = client.post("/api/v1/scan/github", json={"repo_url": "https://github.com/psf/requests"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["source"] == "github"


class TestScanNoManifests:
    def test_scan_local_no_manifests(self, client, tmp_path):
        with patch("backend.api.routes.scan.ManifestDetector") as m:
            instance = m.return_value
            instance.detect.return_value = []

            project = tmp_path / "empty"
            project.mkdir()
            response = client.post("/api/v1/scan/local", json={"directory_path": str(project)})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "no_manifests"
