from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.api.dependencies import (
    get_compatibility_db,
    get_conflict_resolver,
    get_data_aggregator,
    get_export_generator,
    get_system_scanner,
)
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
        response = client.get("/api/v1/packages/search?q=flask&ecosystems=pypi&limit=20")
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
            "ecosystems": {"pypi": {"name": "Flask", "version": "2.3.3", "versions": []}},
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
        mock_source.get_versions = AsyncMock(return_value=return_value, side_effect=side_effect)
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


class TestResolveDependencies:
    def test_resolve_success(self, client, mock_aggregator):
        mock_aggregator.get_package_info.return_value = {
            "name": "requests",
            "ecosystems": {"pypi": {"name": "requests", "version": "2.31.0", "versions": []}},
            "system_requirements": {},
            "dependencies": {"pypi": {"all": []}},
        }
        mock_resolver = MagicMock()
        mock_resolver.resolve_dependencies.return_value = {
            "resolved_packages": {"requests": {"version": "2.31.0", "ecosystem": "pypi"}}
        }
        app.dependency_overrides[get_conflict_resolver] = lambda: mock_resolver
        app.dependency_overrides[get_system_scanner] = lambda: MagicMock()
        try:
            response = client.post(
                "/api/v1/packages/resolve",
                json={
                    "packages": [{"name": "requests", "ecosystem": "pypi"}],
                    "auto_detect_system": False,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "resolved_packages" in data["data"]
        finally:
            app.dependency_overrides.pop(get_conflict_resolver, None)
            app.dependency_overrides.pop(get_system_scanner, None)

    def test_resolve_handles_value_error(self, client, mock_aggregator):
        mock_aggregator.get_package_info.side_effect = ValueError("Invalid package")
        mock_resolver = MagicMock()
        app.dependency_overrides[get_conflict_resolver] = lambda: mock_resolver
        app.dependency_overrides[get_system_scanner] = lambda: MagicMock()
        try:
            response = client.post(
                "/api/v1/packages/resolve",
                json={
                    "packages": [{"name": "invalid-package", "ecosystem": "pypi"}],
                    "auto_detect_system": False,
                },
            )
            assert response.status_code == 400
        finally:
            app.dependency_overrides.pop(get_conflict_resolver, None)
            app.dependency_overrides.pop(get_system_scanner, None)

    def test_resolve_handles_generic_error(self, client, mock_aggregator):
        mock_aggregator.get_package_info.side_effect = RuntimeError("Unexpected")
        mock_resolver = MagicMock()
        app.dependency_overrides[get_conflict_resolver] = lambda: mock_resolver
        app.dependency_overrides[get_system_scanner] = lambda: MagicMock()
        try:
            response = client.post(
                "/api/v1/packages/resolve",
                json={
                    "packages": [{"name": "requests", "ecosystem": "pypi"}],
                    "auto_detect_system": False,
                },
            )
            assert response.status_code == 500
        finally:
            app.dependency_overrides.pop(get_conflict_resolver, None)
            app.dependency_overrides.pop(get_system_scanner, None)

    def test_resolve_with_system_info(self, client, mock_aggregator):
        mock_aggregator.get_package_info.return_value = {
            "name": "torch",
            "ecosystems": {"pypi": {"name": "torch", "version": "2.1.0", "versions": []}},
            "system_requirements": {"cuda": {"min_version": "11.7"}},
            "dependencies": {"pypi": {"all": []}},
        }
        mock_resolver = MagicMock()
        mock_resolver.resolve_dependencies.return_value = {
            "resolved_packages": {"torch": {"version": "2.1.0+cu121", "ecosystem": "pypi"}}
        }
        app.dependency_overrides[get_conflict_resolver] = lambda: mock_resolver
        app.dependency_overrides[get_system_scanner] = lambda: MagicMock()
        try:
            response = client.post(
                "/api/v1/packages/resolve",
                json={
                    "packages": [{"name": "torch", "ecosystem": "pypi"}],
                    "auto_detect_system": False,
                    "system_info": {"gpu": {"available": True, "cuda": "12.1"}},
                },
            )
            assert response.status_code == 200
        finally:
            app.dependency_overrides.pop(get_conflict_resolver, None)
            app.dependency_overrides.pop(get_system_scanner, None)


class TestExportConfiguration:
    def test_export_success(self, client):
        mock_generator = MagicMock()
        mock_generator.generate.return_value = "flask==2.3.3\nrequests==2.31.0"
        app.dependency_overrides[get_export_generator] = lambda: mock_generator
        try:
            response = client.post(
                "/api/v1/packages/export",
                json={
                    "resolved_packages": {
                        "flask": {"version": "2.3.3", "ecosystem": "pypi"},
                        "requests": {"version": "2.31.0", "ecosystem": "pypi"},
                    },
                    "format": "requirements.txt",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["format"] == "requirements.txt"
            assert "flask==2.3.3" in data["content"]
        finally:
            app.dependency_overrides.pop(get_export_generator, None)

    def test_export_value_error(self, client):
        mock_generator = MagicMock()
        mock_generator.generate.side_effect = ValueError("Unsupported format")
        app.dependency_overrides[get_export_generator] = lambda: mock_generator
        try:
            response = client.post(
                "/api/v1/packages/export",
                json={
                    "resolved_packages": {},
                    "format": "unsupported",
                },
            )
            assert response.status_code == 400
        finally:
            app.dependency_overrides.pop(get_export_generator, None)

    def test_export_generic_error(self, client):
        mock_generator = MagicMock()
        mock_generator.generate.side_effect = RuntimeError("Export failed")
        app.dependency_overrides[get_export_generator] = lambda: mock_generator
        try:
            response = client.post(
                "/api/v1/packages/export",
                json={
                    "resolved_packages": {},
                    "format": "requirements.txt",
                },
            )
            assert response.status_code == 500
        finally:
            app.dependency_overrides.pop(get_export_generator, None)


class TestGetPackageDependencies:
    def test_get_dependencies_success(self, client, mock_aggregator):
        mock_source = MagicMock()
        mock_source.get_dependencies = AsyncMock(
            return_value=[{"name": "urllib3", "version_spec": ">=1.21.1,<3"}]
        )
        mock_aggregator._get_client = MagicMock(return_value=mock_source)
        response = client.get("/api/v1/packages/pypi/requests/dependencies")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["package"] == "requests"
        assert len(data["dependencies"]) == 1
        mock_aggregator._get_client.assert_called_once()

    def test_get_dependencies_with_version(self, client, mock_aggregator):
        mock_source = MagicMock()
        mock_source.get_dependencies = AsyncMock(return_value=[])
        mock_aggregator._get_client = MagicMock(return_value=mock_source)
        response = client.get("/api/v1/packages/pypi/requests/dependencies?version=2.31.0")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "2.31.0"

    def test_get_dependencies_recursive(self, client, mock_aggregator):
        mock_source = MagicMock()
        mock_source.get_dependencies = AsyncMock(return_value={"urllib3": ">=1.21.1"})
        mock_source.get_package_info = AsyncMock(return_value={})
        mock_aggregator._get_client = MagicMock(return_value=mock_source)
        response = client.get(
            "/api/v1/packages/pypi/requests/dependencies?recursive=true&max_depth=2"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["package"] == "requests"

    def test_get_dependencies_invalid_ecosystem(self, client, mock_aggregator):
        response = client.get("/api/v1/packages/invalideco/pkg/dependencies")
        assert response.status_code == 400

    def test_get_dependencies_value_error(self, client, mock_aggregator):
        mock_source = MagicMock()
        mock_source.get_dependencies = AsyncMock(side_effect=ValueError("Bad request"))
        mock_aggregator._get_client = MagicMock(return_value=mock_source)
        response = client.get("/api/v1/packages/pypi/pkg/dependencies")
        assert response.status_code == 400

    def test_get_dependencies_server_error(self, client, mock_aggregator):
        mock_source = MagicMock()
        mock_source.get_dependencies = AsyncMock(side_effect=RuntimeError("Server error"))
        mock_aggregator._get_client = MagicMock(return_value=mock_source)
        response = client.get("/api/v1/packages/pypi/pkg/dependencies")
        assert response.status_code == 500


class TestGetPackageCompatibility:
    def test_get_compatibility_success(self, client, mock_aggregator):
        mock_aggregator.get_package_info.return_value = {
            "name": "torch",
            "system_requirements": {"cuda": {"min_version": "11.7"}},
        }
        mock_compat_db = MagicMock()
        mock_compat_db.get_compatibility_rules.return_value = {
            "known_conflicts": [],
            "verified_combinations": [],
            "community_reports": [],
        }
        mock_compat_db.get_compatibility_statistics.return_value = {}
        app.dependency_overrides[get_compatibility_db] = lambda: mock_compat_db
        try:
            response = client.get("/api/v1/packages/pypi/torch/compatibility")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["package"] == "torch"
            assert "compatibility" in data
        finally:
            app.dependency_overrides.pop(get_compatibility_db, None)

    def test_get_compatibility_with_version(self, client, mock_aggregator):
        mock_aggregator.get_package_info.return_value = {
            "name": "torch",
            "system_requirements": {"cuda": {"min_version": "11.7"}},
        }
        mock_compat_db = MagicMock()
        mock_compat_db.get_compatibility_rules.return_value = {
            "known_conflicts": [],
            "verified_combinations": [],
            "community_reports": [],
        }
        mock_compat_db.get_compatibility_statistics.return_value = {}
        app.dependency_overrides[get_compatibility_db] = lambda: mock_compat_db
        try:
            response = client.get("/api/v1/packages/pypi/torch/compatibility?version=2.1.0")
            assert response.status_code == 200
            data = response.json()
            assert data["version"] == "2.1.0"
        finally:
            app.dependency_overrides.pop(get_compatibility_db, None)

    def test_get_compatibility_value_error(self, client, mock_aggregator):
        mock_aggregator.get_package_info.side_effect = ValueError("Bad data")
        mock_compat_db = MagicMock()
        app.dependency_overrides[get_compatibility_db] = lambda: mock_compat_db
        try:
            response = client.get("/api/v1/packages/pypi/torch/compatibility")
            assert response.status_code == 400
        finally:
            app.dependency_overrides.pop(get_compatibility_db, None)

    def test_get_compatibility_server_error(self, client, mock_aggregator):
        mock_aggregator.get_package_info.side_effect = RuntimeError("Server error")
        mock_compat_db = MagicMock()
        app.dependency_overrides[get_compatibility_db] = lambda: mock_compat_db
        try:
            response = client.get("/api/v1/packages/pypi/torch/compatibility")
            assert response.status_code == 500
        finally:
            app.dependency_overrides.pop(get_compatibility_db, None)
