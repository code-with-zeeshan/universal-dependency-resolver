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


class TestSearchPackages:
    def test_search_with_query(self, client, mock_aggregator):
        mock_aggregator.search_packages.return_value = {}
        response = client.get("/api/v1/packages/search?q=flask")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["query"] == "flask"
        mock_aggregator.search_packages.assert_called_once()

    def test_search_missing_query_returns_422(self, client):
        response = client.get("/api/v1/packages/search")
        assert response.status_code == 422

    def test_search_empty_query(self, client, mock_aggregator):
        mock_aggregator.search_packages.return_value = {}
        response = client.get("/api/v1/packages/search?q=")
        assert response.status_code == 200

    def test_search_with_ecosystem_filter(self, client, mock_aggregator):
        mock_aggregator.search_packages.return_value = {"pypi": []}
        response = client.get("/api/v1/packages/search?q=flask&ecosystems=pypi")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_search_with_limit(self, client, mock_aggregator):
        mock_aggregator.search_packages.return_value = {}
        response = client.get("/api/v1/packages/search?q=flask&limit=5")
        assert response.status_code == 200

    def test_search_limit_out_of_range(self, client):
        response = client.get("/api/v1/packages/search?q=flask&limit=200")
        assert response.status_code == 422

    def test_search_with_multiple_ecosystems(self, client, mock_aggregator):
        mock_aggregator.search_packages.return_value = {"pypi": [], "npm": []}
        response = client.get("/api/v1/packages/search?q=flask&ecosystems=pypi,npm")
        assert response.status_code == 200

    def test_search_returns_paginated_results(self, client, mock_aggregator):
        mock_results = {
            "pypi": [
                {
                    "name": "flask",
                    "version": "2.3.3",
                    "description": "A simple framework",
                }
            ]
        }
        mock_aggregator.search_packages.return_value = mock_results
        response = client.get(
            "/api/v1/packages/search?q=flask&ecosystems=pypi&limit=20"
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        mock_aggregator.search_packages.assert_called_once()

    def test_search_handles_aggregator_error(self, client, mock_aggregator):
        mock_aggregator.search_packages.side_effect = Exception("Search failed")
        response = client.get("/api/v1/packages/search?q=flask")
        assert response.status_code == 500


class TestGetPackageDetails:
    def test_get_package_details_success(self, client, mock_aggregator):
        mock_aggregator.get_package_info.return_value = {
            "name": "flask",
            "ecosystems": {
                "pypi": {
                    "name": "Flask",
                    "version": "2.3.3",
                    "description": "A simple framework",
                    "versions": [],
                }
            },
            "system_requirements": {},
            "compatibility_matrix": {},
        }
        response = client.get("/api/v1/packages/pypi/flask/details")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "flask"
        assert data["data"]["ecosystem"] == "pypi"

    def test_get_package_details_not_found(self, client, mock_aggregator):
        mock_aggregator.get_package_info.return_value = None
        response = client.get("/api/v1/packages/pypi/nonexistent/details")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["error"]["message"]

    def test_get_package_details_missing_ecosystem(self, client, mock_aggregator):
        mock_aggregator.get_package_info.return_value = {
            "name": "flask",
            "ecosystems": {},
        }
        response = client.get("/api/v1/packages/pypi/flask/details")
        assert response.status_code == 404

    def test_get_package_details_invalid_ecosystem(self, client):
        response = client.get("/api/v1/packages/invalideco/some-package/details")
        assert response.status_code == 400

    def test_get_package_details_with_metrics(self, client, mock_aggregator):
        mock_aggregator.get_package_info.return_value = {
            "name": "flask",
            "ecosystems": {
                "pypi": {"name": "Flask", "version": "2.3.3", "versions": []}
            },
            "system_requirements": {},
            "compatibility_matrix": {},
        }
        response = client.get("/api/v1/packages/pypi/flask/details?include_metrics=true")
        assert response.status_code == 200

    def test_get_package_details_handles_value_error(self, client, mock_aggregator):
        mock_aggregator.get_package_info.side_effect = ValueError("Invalid data")
        response = client.get("/api/v1/packages/pypi/flask/details")
        assert response.status_code == 400

    def test_get_package_details_handles_generic_error(self, client, mock_aggregator):
        mock_aggregator.get_package_info.side_effect = Exception("Unexpected error")
        response = client.get("/api/v1/packages/pypi/flask/details")
        assert response.status_code == 500


class TestGetPackageVersions:
    def test_get_versions_success(self, client, mock_aggregator):
        self._setup_mock_source(
            mock_aggregator,
            return_value=[
                {"version": "2.3.3", "upload_time": "2023-08-15"},
                {"version": "2.3.2", "upload_time": "2023-05-20"},
            ],
        )
        response = client.get("/api/v1/packages/pypi/flask/versions")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["package"] == "flask"
        assert len(data["versions"]) == 2
        mock_aggregator._get_client.assert_called_once()

    def test_get_versions_empty(self, client, mock_aggregator):
        self._setup_mock_source(mock_aggregator, return_value=[])
        response = client.get("/api/v1/packages/pypi/unknown/versions")
        assert response.status_code == 200
        data = response.json()
        assert data["total_versions"] == 0

    def test_get_versions_invalid_ecosystem(self, client, mock_aggregator):
        response = client.get("/api/v1/packages/invalideco/pkg/versions")
        assert response.status_code == 400
        data = response.json()
        assert "Unknown ecosystem" in data["error"]["message"]

    def _setup_mock_source(self, mock_aggregator, return_value=None, side_effect=None):
        """Helper to mock _get_client instead of sources dict."""
        mock_source = MagicMock()
        mock_source.get_versions = AsyncMock(
            return_value=return_value, side_effect=side_effect
        )
        mock_aggregator._get_client = MagicMock(return_value=mock_source)
        return mock_source

    def test_get_versions_filters_yanked(self, client, mock_aggregator):
        self._setup_mock_source(
            mock_aggregator,
            return_value=[
                {"version": "1.0.0", "yanked": True},
                {"version": "1.1.0", "yanked": False},
            ],
        )
        response = client.get("/api/v1/packages/pypi/pkg/versions?include_yanked=false")
        assert response.status_code == 200
        data = response.json()
        assert len(data["versions"]) == 1
        assert data["versions"][0]["version"] == "1.1.0"

    def test_get_versions_includes_yanked(self, client, mock_aggregator):
        self._setup_mock_source(
            mock_aggregator,
            return_value=[
                {"version": "1.0.0", "yanked": True},
                {"version": "1.1.0", "yanked": False},
            ],
        )
        response = client.get("/api/v1/packages/pypi/pkg/versions?include_yanked=true")
        assert response.status_code == 200
        data = response.json()
        assert len(data["versions"]) == 2

    def test_get_versions_handles_source_error(self, client, mock_aggregator):
        self._setup_mock_source(
            mock_aggregator,
            side_effect=Exception("Version fetch failed"),
        )
        response = client.get("/api/v1/packages/pypi/flask/versions")
        assert response.status_code == 500

    def test_get_versions_with_compatibility_filter(self, client, mock_aggregator):
        self._setup_mock_source(
            mock_aggregator,
            return_value=[
                {
                    "version": "1.0.0",
                    "python_requires": ">=3.8",
                    "platforms": ["linux"],
                },
                {
                    "version": "2.0.0",
                    "python_requires": ">=3.10",
                    "platforms": ["linux"],
                },
            ],
        )
        response = client.get(
            "/api/v1/packages/pypi/pkg/versions?compatible_with=os=linux,python=3.9"
        )
        assert response.status_code == 200


class TestEcosystems:
    def test_get_ecosystems(self, client):
        response = client.get("/api/v1/packages/ecosystems")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "ecosystems" in data
        assert "pypi" in data["ecosystems"]
        assert "npm" in data["ecosystems"]


class TestExportFormats:
    def test_get_export_formats(self, client):
        response = client.get("/api/v1/packages/export-formats")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["formats"]) > 0
