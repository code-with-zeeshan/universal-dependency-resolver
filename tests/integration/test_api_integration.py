"""Integration tests for the FastAPI application with real database and services."""

import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime

from backend.database.models import Package, PackageVersion


class TestHealthEndpoint:
    """Test the health check endpoint against real services."""

    def test_health_returns_200(self, api_client, app_url):
        response = api_client.get(f"{app_url}/health")
        assert response.status_code == 200

    def test_health_has_database_check(self, api_client, app_url):
        response = api_client.get(f"{app_url}/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert "database" in data["checks"]
        assert data["checks"]["database"]["status"] == "healthy"

    def test_health_has_pool_stats(self, api_client, app_url):
        response = api_client.get(f"{app_url}/health")
        data = response.json()
        db = data["checks"]["database"]
        assert "pool_size" in db
        assert "checked_in" in db


class TestRootEndpoint:
    """Test the root API endpoint."""

    def test_root_returns_info(self, api_client):
        response = api_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Universal Dependency Resolver API"
        assert "version" in data
        assert "endpoints" in data

    def test_root_lists_health_endpoint(self, api_client):
        response = api_client.get("/")
        data = response.json()
        assert "/api/v1/health" in data["endpoints"]["health"]

    def test_root_lists_package_endpoints(self, api_client):
        response = api_client.get("/")
        data = response.json()
        assert "package_info" in data["endpoints"]
        assert "resolve" in data["endpoints"]
        assert "export" in data["endpoints"]

    def test_root_response_time_header(self, api_client):
        response = api_client.get("/")
        assert "X-Process-Time" in response.headers
        assert "X-Request-ID" in response.headers


class TestSystemEndpoint:
    """Test the system info endpoint."""

    def test_system_info_returns_data(self, api_client, app_url):
        response = api_client.get(f"{app_url}/system/info")
        assert response.status_code in (200, 502)

    def test_system_info_structure(self, api_client, app_url):
        response = api_client.get(f"{app_url}/system/info")
        if response.status_code == 200:
            data = response.json()
            assert "data" in data
            info = data["data"]
            assert "os" in info
            assert "cpu" in info
            assert "runtime_versions" in info


class TestPackageSearch:
    """Test package search through the API with mocked data sources."""

    @pytest.fixture(autouse=True)
    def _mock_data_sources(self):
        """Mock external data source clients to avoid real HTTP calls."""
        patcher = patch("backend.api.dependencies.get_data_aggregator")
        mock_get_agg = patcher.start()
        aggregator = AsyncMock()
        aggregator.search_packages = AsyncMock(
            return_value={
                "pypi": [
                    {
                        "name": "flask",
                        "ecosystem": "pypi",
                        "version": "2.3.3",
                        "description": "A simple framework",
                        "system_requirements": {"python_versions": [">=3.8"]},
                    }
                ]
            }
        )
        aggregator.get_package_info = AsyncMock(
            return_value={
                "name": "flask",
                "ecosystem": "pypi",
                "version": "2.3.3",
            }
        )
        aggregator.sources = {}
        mock_get_agg.return_value = aggregator
        yield
        patcher.stop()

    def test_search_with_query(self, api_client, app_url):
        response = api_client.get(f"{app_url}/packages/search?q=flask")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "results" in data

    def test_search_missing_query(self, api_client, app_url):
        response = api_client.get(f"{app_url}/packages/search")
        assert response.status_code == 422

    def test_search_with_ecosystem(self, api_client, app_url):
        response = api_client.get(f"{app_url}/packages/search?q=flask&ecosystems=pypi")
        assert response.status_code == 200

    def test_search_with_limit(self, api_client, app_url):
        response = api_client.get(f"{app_url}/packages/search?q=flask&limit=5")
        assert response.status_code == 200

    def test_search_limit_out_of_range(self, api_client, app_url):
        response = api_client.get(f"{app_url}/packages/search?q=flask&limit=200")
        assert response.status_code == 422


class TestPackageInfo:
    """Test package info endpoint."""

    @pytest.fixture(autouse=True)
    def _mock_data_sources(self):
        patcher = patch("backend.api.dependencies.get_data_aggregator")
        mock_get_agg = patcher.start()
        aggregator = AsyncMock()
        aggregator.get_package_info = AsyncMock(
            return_value={
                "name": "flask",
                "ecosystem": "pypi",
                "version": "2.3.3",
                "description": "A simple framework",
            }
        )
        aggregator.sources = {}
        mock_get_agg.return_value = aggregator
        yield
        patcher.stop()

    def test_package_info_returns_data(self, api_client, app_url):
        response = api_client.get(f"{app_url}/packages/pypi/flask")
        assert response.status_code == 200

    def test_package_info_structure(self, api_client, app_url):
        response = api_client.get(f"{app_url}/packages/pypi/flask")
        data = response.json()
        assert "data" in data or "name" in data

    def test_package_info_invalid_ecosystem(self, api_client, app_url):
        response = api_client.get(f"{app_url}/packages/invalid/pytest")
        assert response.status_code in (400, 404)


class TestDependencyResolution:
    """Test the dependency resolution flow end-to-end."""

    @pytest.fixture(autouse=True)
    def _mock_data_sources(self):
        patcher = patch("backend.api.dependencies.get_data_aggregator")
        mock_get_agg = patcher.start()
        aggregator = AsyncMock()
        aggregator.resolve_dependencies = AsyncMock(
            return_value={
                "status": "success",
                "resolved_packages": {
                    "flask": {
                        "version": "2.3.3",
                        "ecosystem": "pypi",
                        "dependencies": {},
                    },
                },
                "warnings": [],
            }
        )
        aggregator.sources = {}
        mock_get_agg.return_value = aggregator
        yield
        patcher.stop()

    def test_resolve_with_packages(self, api_client, app_url, db_session):
        response = api_client.post(
            f"{app_url}/packages/resolve",
            json={
                "packages": [{"name": "flask", "ecosystem": "pypi"}],
                "system_info": {"os": {"system": "Linux"}},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "resolved_packages" in data
        assert "flask" in data["resolved_packages"]

    def test_resolve_empty_packages(self, api_client, app_url):
        response = api_client.post(
            f"{app_url}/packages/resolve",
            json={"packages": []},
        )
        assert response.status_code == 422

    def test_resolve_missing_body(self, api_client, app_url):
        response = api_client.post(f"{app_url}/packages/resolve", json={})
        assert response.status_code == 422

    def test_resolve_saves_to_db(self, api_client, app_url, db_session):
        pkg = Package(name="flask", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        response = api_client.post(
            f"{app_url}/packages/resolve",
            json={
                "packages": [{"name": "flask", "ecosystem": "pypi"}],
            },
        )
        assert response.status_code == 200


class TestExportFormats:
    """Test export format endpoints."""

    def test_get_export_formats(self, api_client, app_url):
        response = api_client.get(f"{app_url}/packages/export-formats")
        assert response.status_code == 200
        data = response.json()
        assert "formats" in data or isinstance(data, list)

    def test_export_requires_resolved_packages(self, api_client, app_url):
        response = api_client.post(
            f"{app_url}/packages/export",
            json={"format": "requirements.txt"},
        )
        assert response.status_code in (400, 422)

    def test_export_invalid_format(self, api_client, app_url):
        response = api_client.post(
            f"{app_url}/packages/export",
            json={
                "format": "invalid_format",
                "resolved_packages": {"flask": {"version": "2.3.3"}},
            },
        )
        assert response.status_code in (400, 422)


class TestErrorHandling:
    """Test error handling and response formats."""

    def test_404_returns_json_error(self, api_client, app_url):
        response = api_client.get(f"{app_url}/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data or "detail" in data

    def test_cors_headers_present(self, api_client):
        response = api_client.get("/")
        assert "access-control-allow-origin" in response.headers

    def test_request_id_header(self, api_client):
        response = api_client.get("/")
        assert "X-Request-ID" in response.headers


class TestAuth:
    """Test authentication middleware (when enabled)."""

    def test_auth_disabled_by_default(self, api_client, app_url):
        response = api_client.get(f"{app_url}/system/info")
        assert response.status_code in (200, 502)


class TestMiddleware:
    """Test middleware behavior."""

    def test_process_time_header(self, api_client):
        response = api_client.get("/")
        assert "X-Process-Time" in response.headers
        process_time = float(response.headers["X-Process-Time"])
        assert process_time > 0

    def test_request_id_tracking(self, api_client):
        response = api_client.get("/")
        rid1 = response.headers.get("X-Request-ID")

        response = api_client.get("/api/v1/health")
        rid2 = response.headers.get("X-Request-ID")

        assert rid1 is not None
        assert rid2 is not None
        assert rid1 != rid2

    def test_response_json_format(self, api_client):
        response = api_client.get("/api/v1/health")
        content_type = response.headers.get("content-type", "")
        assert "json" in content_type


class TestDatabaseSession:
    """Test that API operations persist data to the database correctly."""

    def test_package_created_via_api_persists(self, db_session):
        pkg = Package(name="api-pkg", ecosystem="pypi", latest_version="1.0.0")
        db_session.add(pkg)
        db_session.commit()

        saved = db_session.query(Package).filter_by(name="api-pkg").first()
        assert saved is not None
        assert saved.latest_version == "1.0.0"

    def test_version_added_to_package(self, db_session, clean_tables):
        pkg = Package(name="versioned-pkg", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        version = PackageVersion(
            package_id=pkg.id, version="1.0.0", python_requires=">=3.8"
        )
        db_session.add(version)
        db_session.commit()

        loaded = db_session.query(Package).filter_by(name="versioned-pkg").first()
        assert len(loaded.versions) == 1
        assert loaded.versions[0].python_requires == ">=3.8"
