from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_sources.pypi_client import PyPIClient


class TestPyPIClient:
    @pytest.fixture
    def client(self):
        return PyPIClient()

    @pytest.fixture
    def sample_pypi_response(self):
        return {
            "info": {
                "name": "Flask",
                "version": "2.3.3",
                "summary": "A simple framework",
                "home_page": "https://flask.palletsprojects.com/",
                "license": "BSD-3-Clause",
                "author": "Armin Ronacher",
                "author_email": "armin@example.com",
                "keywords": "wsgi,werkzeug,flask,web",
                "requires_python": ">=3.8",
                "requires_dist": ["Werkzeug>=2.3.0", "Jinja2>=3.1.2", "click>=8.1.3"],
                "classifiers": [
                    "Development Status :: 5 - Production/Stable",
                    "Programming Language :: Python :: 3",
                ],
                "project_urls": {"Source": "https://github.com/pallets/flask"},
                "downloads": {
                    "last_day": 50000,
                    "last_week": 350000,
                    "last_month": 1500000,
                },
            },
            "releases": {
                "2.3.3": [
                    {
                        "filename": "Flask-2.3.3-py3-none-any.whl",
                        "packagetype": "bdist_wheel",
                        "size": 96200,
                        "upload_time": "2023-08-15T15:00:00",
                        "requires_python": ">=3.8",
                        "yanked": False,
                    }
                ],
                "2.3.2": [
                    {
                        "filename": "Flask-2.3.2-py3-none-any.whl",
                        "packagetype": "bdist_wheel",
                        "size": 95800,
                        "upload_time": "2023-05-20T14:00:00",
                        "requires_python": ">=3.8",
                        "yanked": False,
                    }
                ],
            },
            "urls": [
                {
                    "filename": "Flask-2.3.3-py3-none-any.whl",
                    "packagetype": "bdist_wheel",
                    "size": 96200,
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_pypi_response):
        with patch.object(
            client,
            "cached_get",
            new_callable=AsyncMock,
            return_value=sample_pypi_response,
        ):
            result = await client.get_package_info_async("flask")
        assert result is not None
        assert result["name"] == "Flask"
        assert result["version"] == "2.3.3"
        assert result["description"] == "A simple framework"
        assert result["homepage"] == "https://flask.palletsprojects.com/"
        assert "dependencies" in result
        assert "versions" in result

    @pytest.mark.asyncio
    async def test_get_package_info_async_calls_correct_url(
        self, client, sample_pypi_response
    ):
        with patch.object(
            client,
            "cached_get",
            new_callable=AsyncMock,
            return_value=sample_pypi_response,
        ) as mock_get:
            await client.get_package_info_async("flask")
        mock_get.assert_called_once()
        cache_key, url = mock_get.call_args[0]
        assert "pypi:flask" in cache_key
        assert "/pypi/flask/json" in url

    @pytest.mark.asyncio
    async def test_get_package_info_async_normalizes_name(
        self, client, sample_pypi_response
    ):
        with patch.object(
            client,
            "cached_get",
            new_callable=AsyncMock,
            return_value=sample_pypi_response,
        ) as mock_get:
            await client.get_package_info_async("Flask_WEB")
        mock_get.assert_called_once()
        cache_key, url = mock_get.call_args[0]
        assert "pypi:" in cache_key
        assert "flask-web" in cache_key or "flask_web" in url

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=None
        ):
            result = await client.get_package_info_async("nonexistent-package")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_async_handles_bad_data(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value={"invalid": True}
        ):
            result = await client.get_package_info_async("bad-package")
        assert result is not None
        assert result.get("name") is None

    def test_get_package_info_sync_success(self, client, sample_pypi_response):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_pypi_response,
        ):
            result = client.get_package_info("flask")
        assert result is not None
        assert result["info"]["name"] == "Flask"

    def test_get_package_info_sync_not_found(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            result = client.get_package_info("nonexistent")
        assert result is None

    async def test_package_exists_returns_true(self, client):
        session = client._get_session()
        with patch.object(session, "head", new_callable=AsyncMock) as mock_head:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_head.return_value = mock_response
            assert await client.package_exists("flask") is True
            mock_head.assert_called_once()

    async def test_package_exists_returns_false(self, client):
        session = client._get_session()
        with patch.object(session, "head", new_callable=AsyncMock) as mock_head:
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_head.return_value = mock_response
            assert await client.package_exists("nonexistent") is False

    async def test_package_exists_handles_exception(self, client):
        session = client._get_session()
        with patch.object(session, "head", side_effect=Exception("Network error")):
            assert await client.package_exists("flask") is False

    @pytest.fixture
    def sample_processed_pypi_response(self):
        return {
            "name": "Flask",
            "version": "2.3.3",
            "versions": [
                {
                    "version": "2.3.3",
                    "upload_time": "2023-09-01T00:00:00",
                    "requires_python": ">=3.8",
                    "python_versions": ["3.8", "3.9", "3.10", "3.11"],
                    "has_binary_wheel": True,
                    "has_source": True,
                    "yanked": False,
                    "platforms": ["linux", "macos"],
                },
                {
                    "version": "2.3.2",
                    "upload_time": "2023-08-15T00:00:00",
                    "requires_python": ">=3.8",
                    "python_versions": ["3.8", "3.9", "3.10", "3.11"],
                    "has_binary_wheel": True,
                    "has_source": False,
                    "yanked": False,
                    "platforms": ["linux"],
                },
            ],
            "description": "A simple framework",
            "author": "Armin Ronacher",
        }

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client, sample_processed_pypi_response):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_processed_pypi_response,
        ):
            versions = await client.get_versions("flask")
        assert len(versions) == 2
        assert versions[0]["version"] in ("2.3.3", "2.3.2")
        assert all("version" in v for v in versions)
        assert all("upload_time" in v for v in versions)
        assert versions == sorted(versions, key=lambda x: x["version"], reverse=True)

    @pytest.mark.asyncio
    async def test_get_versions_empty_when_no_package(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            versions = await client.get_versions("nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_versions_includes_metadata(
        self, client, sample_processed_pypi_response
    ):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_processed_pypi_response,
        ):
            versions = await client.get_versions("flask")
        for v in versions:
            assert "python_versions" in v
            assert "has_binary" in v
            assert "has_source" in v
            assert "platforms" in v

    @pytest.mark.asyncio
    async def test_search_calls_xmlrpc(self, client):
        with patch.object(
            client,
            "_search_xmlrpc",
            new_callable=AsyncMock,
            return_value=[{"name": "flask"}],
        ), patch.object(
            client, "_search_web_scraping", new_callable=AsyncMock
        ) as mock_web, patch.object(
            client, "_search_fallback", new_callable=AsyncMock
        ) as mock_fallback:
            results = await client.search("flask")
        assert len(results) == 1
        assert results[0]["name"] == "flask"
        mock_web.assert_not_called()
        mock_fallback.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_falls_back_to_web_scraping(self, client):
        with patch.object(
            client, "_search_xmlrpc", new_callable=AsyncMock, return_value=[]
        ), patch.object(
            client,
            "_search_web_scraping",
            new_callable=AsyncMock,
            return_value=[{"name": "flask"}],
        ), patch.object(
            client, "_search_fallback", new_callable=AsyncMock
        ) as mock_fallback:
            results = await client.search("flask")
        assert len(results) == 1
        mock_fallback.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_all_failures(self, client):
        with patch.object(
            client, "_search_xmlrpc", new_callable=AsyncMock, return_value=[]
        ), patch.object(
            client, "_search_web_scraping", new_callable=AsyncMock, return_value=[]
        ), patch.object(
            client, "_search_fallback", new_callable=AsyncMock, return_value=[]
        ):
            results = await client.search("flask")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_exception(self, client):
        with patch.object(
            client,
            "_search_xmlrpc",
            new_callable=AsyncMock,
            side_effect=Exception("XML-RPC error"),
        ):
            results = await client.search("flask")
        assert results == []

    def test_extract_python_versions_from_wheel(self, client):
        assert "3.x" in client._extract_python_versions_from_wheel(
            "Flask-2.3.3-py3-none-any.whl"
        )
        assert "3.9" in client._extract_python_versions_from_wheel(
            "pkg-1.0-cp39-cp39-win_amd64.whl"
        )
        assert set() == client._extract_python_versions_from_wheel("pkg-1.0.tar.gz")

    def test_extract_platform_from_wheel(self, client):
        assert (
            client._extract_platform_from_wheel("pkg-1.0-cp39-cp39-win_amd64.whl")
            == "Windows x64"
        )
        assert (
            client._extract_platform_from_wheel("pkg-1.0-cp39-cp39-manylinux.whl")
            == "Linux"
        )
        assert client._extract_platform_from_wheel("pkg-1.0.tar.gz") is None

    def test_parse_keywords(self, client):
        assert client._parse_keywords("wsgi,werkzeug,flask,web") == [
            "wsgi",
            "werkzeug",
            "flask",
            "web",
        ]
        assert client._parse_keywords("") == []
        assert client._parse_keywords(None) == []

    def test_extract_development_status(self, client):
        classifiers = [
            "Development Status :: 5 - Production/Stable",
            "License :: OSI Approved :: MIT",
        ]
        assert (
            client._extract_development_status(classifiers) == "5 - Production/Stable"
        )
        assert client._extract_development_status([]) is None

    def test_extract_repository_url(self, client):
        info = {"project_urls": {"Source": "https://github.com/pallets/flask"}}
        assert (
            client._extract_repository_url(info) == "https://github.com/pallets/flask"
        )

        info = {"home_page": "https://github.com/pallets/flask"}
        assert (
            client._extract_repository_url(info) == "https://github.com/pallets/flask"
        )

        info = {"home_page": "https://example.com"}
        assert client._extract_repository_url(info) is None

    def test_extract_documentation_url(self, client):
        info = {"project_urls": {"Documentation": "https://flask.palletsprojects.com/"}}
        assert (
            client._extract_documentation_url(info)
            == "https://flask.palletsprojects.com/"
        )

        info = {}
        assert client._extract_documentation_url(info) is None

    def test_extract_min_python_version(self, client):
        assert client._extract_min_python_version(">=3.8") == "3.8"
        assert client._extract_min_python_version(">3.10") == "3.10"
        assert client._extract_min_python_version("==3.9") == "3.9"
        assert client._extract_min_python_version("") is None
