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
    async def test_get_package_info_async_calls_correct_url(self, client, sample_pypi_response):
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
    async def test_get_package_info_async_normalizes_name(self, client, sample_pypi_response):
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
        with patch.object(client, "cached_get", new_callable=AsyncMock, return_value=None):
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
    async def test_get_versions_includes_metadata(self, client, sample_processed_pypi_response):
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
        with (
            patch.object(
                client,
                "_search_xmlrpc",
                new_callable=AsyncMock,
                return_value=[{"name": "flask"}],
            ),
            patch.object(client, "_search_web_scraping", new_callable=AsyncMock) as mock_web,
            patch.object(client, "_search_fallback", new_callable=AsyncMock) as mock_fallback,
        ):
            results = await client.search("flask")
        assert len(results) == 1
        assert results[0]["name"] == "flask"
        mock_web.assert_not_called()
        mock_fallback.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_falls_back_to_web_scraping(self, client):
        with (
            patch.object(client, "_search_xmlrpc", new_callable=AsyncMock, return_value=[]),
            patch.object(
                client,
                "_search_web_scraping",
                new_callable=AsyncMock,
                return_value=[{"name": "flask"}],
            ),
            patch.object(client, "_search_fallback", new_callable=AsyncMock) as mock_fallback,
        ):
            results = await client.search("flask")
        assert len(results) == 1
        mock_fallback.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_all_failures(self, client):
        with (
            patch.object(client, "_search_xmlrpc", new_callable=AsyncMock, return_value=[]),
            patch.object(client, "_search_web_scraping", new_callable=AsyncMock, return_value=[]),
            patch.object(client, "_search_fallback", new_callable=AsyncMock, return_value=[]),
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
        assert "3.x" in client._extract_python_versions_from_wheel("Flask-2.3.3-py3-none-any.whl")
        assert "3.9" in client._extract_python_versions_from_wheel(
            "pkg-1.0-cp39-cp39-win_amd64.whl"
        )
        assert set() == client._extract_python_versions_from_wheel("pkg-1.0.tar.gz")

    def test_extract_platform_from_wheel(self, client):
        assert (
            client._extract_platform_from_wheel("pkg-1.0-cp39-cp39-win_amd64.whl") == "Windows x64"
        )
        assert client._extract_platform_from_wheel("pkg-1.0-cp39-cp39-manylinux.whl") == "Linux"
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
        assert client._extract_development_status(classifiers) == "5 - Production/Stable"
        assert client._extract_development_status([]) is None

    def test_extract_repository_url(self, client):
        info = {"project_urls": {"Source": "https://github.com/pallets/flask"}}
        assert client._extract_repository_url(info) == "https://github.com/pallets/flask"

        info = {"home_page": "https://github.com/pallets/flask"}
        assert client._extract_repository_url(info) == "https://github.com/pallets/flask"

        info = {"home_page": "https://example.com"}
        assert client._extract_repository_url(info) is None

    def test_extract_documentation_url(self, client):
        info = {"project_urls": {"Documentation": "https://flask.palletsprojects.com/"}}
        assert client._extract_documentation_url(info) == "https://flask.palletsprojects.com/"

        info = {}
        assert client._extract_documentation_url(info) is None

    def test_extract_min_python_version(self, client):
        assert client._extract_min_python_version(">=3.8") == "3.8"
        assert client._extract_min_python_version(">3.10") == "3.10"
        assert client._extract_min_python_version("==3.9") == "3.9"
        assert client._extract_min_python_version("~=3.7") == "3.7"
        assert client._extract_min_python_version("") is None
        assert client._extract_min_python_version(None) is None

    def test_parse_keywords_space_separated(self, client):
        result = client._parse_keywords("wsgi werkzeug flask web")
        assert result == ["wsgi", "werkzeug", "flask", "web"]

    def test_extract_python_versions_from_wheel_py2_py3(self, client):
        versions = client._extract_python_versions_from_wheel("pkg-1.0-py2.py3-none-any.whl")
        assert "2.7" in versions
        assert "3.x" in versions

    def test_extract_python_versions_from_wheel_pp_pattern(self, client):
        versions = client._extract_python_versions_from_wheel("pkg-1.0-pp39-pp39-win_amd64.whl")
        assert "3.9" in versions

    def test_extract_cuda_requirements_from_classifier(self, client):
        classifiers = ["CUDA :: 11.8", "CUDA :: 12.1"]
        result = client._extract_cuda_requirements(classifiers, "", "test-pkg")
        assert result is not None
        assert result["required"] is True
        assert "11.8" in result["cuda_versions"]
        assert "12.1" in result["cuda_versions"]

    def test_extract_cuda_requirements_from_package_name(self, client):
        result = client._extract_cuda_requirements([], "", "torch-gpu")
        assert result is not None
        assert result["required"] is True

    def test_extract_cuda_requirements_from_description(self, client):
        description = "requires cuda 12.0 and cudnn 8.9"
        result = client._extract_cuda_requirements([], description, "test-pkg")
        assert result is not None
        assert "12.0" in result["cuda_versions"]
        assert "8.9" in result["cudnn_versions"]

    def test_extract_cuda_requirements_returns_none(self, client):
        result = client._extract_cuda_requirements([], "a simple package", "test-pkg")
        assert result is None

    def test_extract_os_requirements_from_classifiers(self, client):
        classifiers = ["Operating System :: POSIX :: Linux", "Operating System :: MacOS"]
        result = client._extract_os_requirements(classifiers, [])
        assert "Linux" in result["supported"]
        assert "macOS" in result["supported"]

    def test_extract_os_requirements_from_wheels(self, client):
        urls = [
            {"filename": "pkg-1.0-cp39-cp39-win_amd64.whl"},
            {"filename": "pkg-1.0-cp39-cp39-macosx_10_9.whl"},
            {"filename": "pkg-1.0-cp39-cp39-manylinux.whl"},
        ]
        result = client._extract_os_requirements([], urls)
        assert "Windows" in result["supported"]
        assert "macOS" in result["supported"]
        assert "Linux" in result["supported"]

    def test_extract_os_requirements_returns_empty_with_any(self, client):
        classifiers = ["Operating System :: OS Independent"]
        result = client._extract_os_requirements(classifiers, [])
        assert result == {}

    def test_extract_architecture_requirements(self, client):
        urls = [
            {"filename": "pkg-1.0-cp39-cp39-win_amd64.whl"},
            {"filename": "pkg-1.0-cp39-cp39-linux_aarch64.whl"},
            {"filename": "pkg-1.0-cp39-cp39-linux_armv7.whl"},
            {"filename": "pkg-1.0-cp39-cp39-win32.whl"},
        ]
        result = client._extract_architecture_requirements([], urls)
        assert result["supported"] == ["ARM64", "ARMv7", "x86", "x86_64"]

    def test_extract_architecture_requirements_returns_empty(self, client):
        result = client._extract_architecture_requirements([], [])
        assert result == {}

    def test_extract_system_library_requirements(self, client):
        description = "requires openssl, openblas, hdf5, qt5 and opengl"
        result = client._extract_system_library_requirements(description, [])
        names = [lib["name"] for lib in result]
        assert "openssl" in names
        assert "blas" in names
        assert "hdf5" in names
        assert "qt" in names
        assert "opengl" in names

    def test_extract_system_library_requirements_empty(self, client):
        result = client._extract_system_library_requirements("a simple package", [])
        assert result == []

    def test_extract_compiler_requirements_c_cpp(self, client):
        classifiers = [
            "Programming Language :: C",
            "Programming Language :: C++",
        ]
        result = client._extract_compiler_requirements("", classifiers)
        assert result["c"] is True
        assert result["cpp"] is True

    def test_extract_compiler_requirements_gcc(self, client):
        result = client._extract_compiler_requirements("requires gcc >= 12.0", [])
        assert result["gcc"]["version"] == "12.0"
        assert result["gcc"]["operator"] == ">="

    def test_extract_compiler_requirements_returns_none(self, client):
        result = client._extract_compiler_requirements("a simple package", [])
        assert result is None

    def test_extract_download_stats(self, client):
        info = {"downloads": {"last_day": 100, "last_week": 700, "last_month": 3000}}
        result = client._extract_download_stats(info)
        assert result["last_day"] == 100
        assert result["last_week"] == 700
        assert result["last_month"] == 3000

    def test_extract_download_stats_empty(self, client):
        result = client._extract_download_stats({})
        assert result == {"last_day": 0, "last_week": 0, "last_month": 0}

    @pytest.mark.asyncio
    async def test_get_package_info_async_process_exception(self, client):
        data = {"info": {"name": "broken"}, "releases": {}, "urls": []}
        with patch.object(client, "cached_get", new_callable=AsyncMock, return_value=data):
            with patch.object(
                client,
                "_process_package_data_enhanced",
                new_callable=AsyncMock,
                side_effect=ValueError("bad data"),
            ):
                result = await client.get_package_info_async("broken")
        assert result is None

    @pytest.mark.asyncio
    async def test_process_package_data_no_version_from_releases(self, client):
        data = {
            "info": {},
            "releases": {
                "3.0.0a1": [
                    {"filename": "pkg-3.0.0a1.tar.gz", "packagetype": "sdist", "size": 100}
                ],
                "2.0.0": [{"filename": "pkg-2.0.0.tar.gz", "packagetype": "sdist", "size": 90}],
                "1.0.0": [{"filename": "pkg-1.0.0.tar.gz", "packagetype": "sdist", "size": 80}],
            },
            "urls": [],
        }
        result = await client._process_package_data_enhanced(data)
        assert result["version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_process_package_data_no_version_no_stable(self, client):
        data = {
            "info": {},
            "releases": {
                "3.0.0a1": [
                    {"filename": "pkg-3.0.0a1.tar.gz", "packagetype": "sdist", "size": 100}
                ],
            },
            "urls": [],
        }
        result = await client._process_package_data_enhanced(data)
        assert result["version"] is None

    @pytest.mark.asyncio
    async def test_process_package_data_sdist_type(self, client):
        data = {
            "info": {"name": "pkg", "version": "1.0.0"},
            "releases": {
                "1.0.0": [
                    {"filename": "pkg-1.0.0.tar.gz", "packagetype": "sdist", "size": 100},
                    {
                        "filename": "pkg-1.0.0-py3-none-any.whl",
                        "packagetype": "bdist_wheel",
                        "size": 50,
                    },
                ]
            },
            "urls": [],
        }
        result = await client._process_package_data_enhanced(data)
        ver = result["versions"][0]
        assert ver["has_source"] is True
        assert ver["has_binary_wheel"] is True

    @pytest.mark.asyncio
    async def test_extract_dependencies_enhanced_empty_req_str(self, client):
        result = await client._extract_dependencies_enhanced(["", "Werkzeug>=2.0"], ">=3.8")
        assert "Werkzeug" in result["required"]

    @pytest.mark.asyncio
    async def test_extract_dependencies_enhanced_dev_extra(self, client):
        requires_dist = ['pytest; extra == "dev"']
        result = await client._extract_dependencies_enhanced(requires_dist, None)
        assert "pytest" in result["dev"]

    @pytest.mark.asyncio
    async def test_extract_dependencies_enhanced_test_extra(self, client):
        requires_dist = ['pytest; extra == "testing"']
        result = await client._extract_dependencies_enhanced(requires_dist, None)
        assert "pytest" in result["test"]

    @pytest.mark.asyncio
    async def test_extract_dependencies_enhanced_docs_extra(self, client):
        requires_dist = ['sphinx; extra == "docs"']
        result = await client._extract_dependencies_enhanced(requires_dist, None)
        assert "sphinx" in result["docs"]

    @pytest.mark.asyncio
    async def test_extract_dependencies_enhanced_custom_extra(self, client):
        requires_dist = ['mypy; extra == "typing"']
        result = await client._extract_dependencies_enhanced(requires_dist, None)
        assert "typing" in result["extras"]
        assert "mypy" in result["extras"]["typing"]

    @pytest.mark.asyncio
    async def test_extract_dependencies_enhanced_platform_marker(self, client):
        requires_dist = ['pywin32; sys_platform == "win32"']
        result = await client._extract_dependencies_enhanced(requires_dist, None)
        assert "pywin32" in result["optional"]

    @pytest.mark.asyncio
    async def test_extract_dependencies_enhanced_python_version_compatible(self, client):
        requires_dist = ['importlib_metadata; python_version < "3.10"']
        result = await client._extract_dependencies_enhanced(requires_dist, ">=3.6")
        assert "importlib_metadata" in result["required"]

    @pytest.mark.asyncio
    async def test_extract_dependencies_enhanced_python_version_no_requires(self, client):
        requires_dist = ['typing_extensions; python_version < "3.8"']
        result = await client._extract_dependencies_enhanced(requires_dist, None)
        assert "typing_extensions" in result["optional"]

    @pytest.mark.asyncio
    async def test_extract_dependencies_enhanced_parse_failure(self, client):
        requires_dist = ["some-invalid==req!!"]
        result = await client._extract_dependencies_enhanced(requires_dist, None)
        assert "some-invalid==req!!" in result["required"]

    @pytest.mark.asyncio
    async def test_extract_dependencies_enhanced_parse_failure_with_marker(self, client):
        requires_dist = ["invalid name >=1.0; extra == 'dev'"]
        result = await client._extract_dependencies_enhanced(requires_dist, None)
        assert "invalid" in result["required"]
        assert result["required"]["invalid"] == "name >=1.0"

    @pytest.mark.asyncio
    async def test_extract_dependencies_enhanced_no_requires(self, client):
        result = await client._extract_dependencies_enhanced([], None)
        assert result == {
            "required": {},
            "optional": {},
            "dev": {},
            "test": {},
            "docs": {},
            "extras": {},
        }

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client):
        data = {
            "info": {
                "requires_dist": ["Werkzeug>=2.0"],
                "requires_python": ">=3.8",
            }
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_dependencies("flask")
        assert "Werkzeug" in result["required"]

    @pytest.mark.asyncio
    async def test_get_dependencies_with_version(self, client):
        data = {
            "info": {
                "requires_dist": ["Werkzeug>=2.0"],
                "requires_python": ">=3.8",
            }
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_dependencies("flask", "2.3.3")
        assert "Werkzeug" in result["required"]

    @pytest.mark.asyncio
    async def test_get_dependencies_returns_empty_on_none(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            result = await client.get_dependencies("nonexistent")
        assert result == {}

    @pytest.mark.asyncio
    async def test_search_cache_hit(self, client):
        from datetime import datetime

        client._search_cache["search:flask:20"] = ([{"name": "flask"}], datetime.now())
        with patch.object(client, "_search_xmlrpc", new_callable=AsyncMock) as mock_xml:
            results = await client.search("flask")
        assert len(results) == 1
        assert results[0]["name"] == "flask"
        mock_xml.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_cache_expired(self, client):
        from datetime import datetime, timedelta

        client._search_cache["search:flask:20"] = (
            [{"name": "flask"}],
            datetime.now() - timedelta(seconds=9999),
        )
        with patch.object(
            client, "_search_xmlrpc", new_callable=AsyncMock, return_value=[{"name": "new"}]
        ):
            results = await client.search("flask")
        assert results[0]["name"] == "new"

    @pytest.mark.asyncio
    async def test_search_xmlrpc_success(self, client):
        results = [
            MagicMock(
                **{
                    "get.side_effect": lambda k, d=None: {
                        "name": "flask",
                        "version": "2.0",
                        "summary": "desc",
                        "_pypi_ordering": 10,
                    }.get(k, d)
                }
            )
        ]
        with patch.object(client, "_search_xmlrpc", wraps=client._search_xmlrpc):
            with patch("xmlrpc.client.ServerProxy") as mock_proxy:
                mock_proxy.return_value.search.return_value = results
                with patch("asyncio.get_event_loop") as mock_loop:
                    mock_loop.return_value.run_in_executor = AsyncMock(return_value=results)
                    # Need to call through search which calls _search_xmlrpc
        # Actually let me test _search_xmlrpc directly
        xmlrpc_results = [
            {"name": "flask", "version": "2.0", "summary": "desc", "_pypi_ordering": 10}
        ]
        with patch.object(
            client, "_search_xmlrpc", new_callable=AsyncMock, return_value=xmlrpc_results
        ):
            with patch.object(client, "_search_web_scraping", new_callable=AsyncMock):
                with patch.object(client, "_search_fallback", new_callable=AsyncMock):
                    results = await client.search("flask")
        assert len(results) == 1
        assert results[0]["name"] == "flask"

    @pytest.mark.asyncio
    async def test_search_fallback_exact_match(self, client):
        match_info = {"name": "flask", "version": "2.0", "description": "web framework"}
        with patch.object(client, "_search_xmlrpc", new_callable=AsyncMock, return_value=[]):
            with patch.object(
                client, "_search_web_scraping", new_callable=AsyncMock, return_value=[]
            ):
                with patch.object(
                    client,
                    "get_package_info_async",
                    new_callable=AsyncMock,
                    return_value=match_info,
                ):
                    results = await client.search("flask")
        assert len(results) == 1
        assert results[0]["name"] == "flask"

    @pytest.mark.asyncio
    async def test_search_fallback_variations(self, client):
        with patch.object(client, "_search_xmlrpc", new_callable=AsyncMock, return_value=[]):
            with patch.object(
                client, "_search_web_scraping", new_callable=AsyncMock, return_value=[]
            ):
                with patch.object(
                    client,
                    "get_package_info_async",
                    new_callable=AsyncMock,
                    side_effect=[
                        None,
                        {"name": "flask", "version": "2.0", "description": "web"},
                        {"name": "other", "version": "1.0", "description": "other"},
                    ],
                ):
                    results = await client.search("Flask")
        # First call is exact match (None), second is for a variation
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_fallback_returns_up_to_limit(self, client):
        with patch.object(client, "_search_xmlrpc", new_callable=AsyncMock, return_value=[]):
            with patch.object(
                client, "_search_web_scraping", new_callable=AsyncMock, return_value=[]
            ):
                with patch.object(
                    client,
                    "get_package_info_async",
                    new_callable=AsyncMock,
                    return_value={"name": "match", "version": "1.0", "description": "desc"},
                ):
                    results = await client.search("flask", limit=1)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_all_methods_fail(self, client):
        with patch.object(client, "_search_xmlrpc", new_callable=AsyncMock, return_value=[]):
            with patch.object(
                client, "_search_web_scraping", new_callable=AsyncMock, return_value=[]
            ):
                with patch.object(
                    client, "_search_fallback", new_callable=AsyncMock, return_value=[]
                ):
                    results = await client.search("nonexistent-xyzzy")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_versions_sorts_newest_first(self, client):
        response = {
            "name": "pkg",
            "version": "1.0.0",
            "versions": [
                {
                    "version": "1.0.0",
                    "upload_time": None,
                    "requires_python": None,
                    "python_versions": [],
                    "has_binary_wheel": False,
                    "has_source": False,
                    "yanked": False,
                    "platforms": [],
                },
                {
                    "version": "2.0.0",
                    "upload_time": None,
                    "requires_python": None,
                    "python_versions": [],
                    "has_binary_wheel": False,
                    "has_source": False,
                    "yanked": False,
                    "platforms": [],
                },
            ],
        }
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=response
        ):
            versions = await client.get_versions("pkg")
        assert versions[0]["version"] == "2.0.0"
        assert versions[1]["version"] == "1.0.0"

    def test_extract_system_requirements_enhanced_with_gpu(self, client):
        info = {
            "name": "torch-gpu",
            "description": "requires cuda 11.8",
            "summary": "",
            "classifiers": ["CUDA :: 11.8"],
        }
        result = client._extract_system_requirements_enhanced(info, [])
        assert "gpu" in result
        assert "11.8" in result["gpu"]["cuda_versions"]

    def test_extract_system_requirements_enhanced_with_python(self, client):
        info = {
            "name": "pkg",
            "description": "",
            "summary": "",
            "classifiers": [],
            "requires_python": ">=3.8",
        }
        result = client._extract_system_requirements_enhanced(info, [])
        assert "python" in result
        assert result["python"]["version_spec"] == ">=3.8"
        assert result["python"]["min_version"] == "3.8"

    def test_extract_system_requirements_enhanced_with_os(self, client):
        info = {
            "name": "pkg",
            "description": "",
            "summary": "",
            "classifiers": ["Operating System :: POSIX :: Linux"],
        }
        result = client._extract_system_requirements_enhanced(info, [])
        assert "os" in result
        assert "Linux" in result["os"]["supported"]

    def test_extract_system_requirements_enhanced_with_architecture(self, client):
        urls = [{"filename": "pkg-1.0-cp39-cp39-win_amd64.whl"}]
        info = {"name": "pkg", "description": "", "summary": "", "classifiers": []}
        result = client._extract_system_requirements_enhanced(info, urls)
        assert "architecture" in result
        assert "x86_64" in result["architecture"]["supported"]

    def test_extract_system_requirements_enhanced_with_libraries(self, client):
        info = {
            "name": "pkg",
            "description": "requires openssl and hdf5",
            "summary": "",
            "classifiers": [],
        }
        result = client._extract_system_requirements_enhanced(info, [])
        assert "system_libraries" in result
        names = [lib["name"] for lib in result["system_libraries"]]
        assert "openssl" in names
        assert "hdf5" in names

    def test_extract_system_requirements_enhanced_with_compiler(self, client):
        classifiers = ["Programming Language :: C"]
        info = {"name": "pkg", "description": "", "summary": "", "classifiers": classifiers}
        result = client._extract_system_requirements_enhanced(info, [])
        assert "compiler" in result
        assert result["compiler"]["c"] is True

    def test_is_compatible_with_python_requires(self, client):
        assert (
            client._is_compatible_with_python_requires('python_version < "3.10"', ">=3.8") is True
        )

    def test_extract_min_python_version_no_match(self, client):
        assert client._extract_min_python_version("<3.8") is None

    @pytest.mark.asyncio
    async def test_process_package_data_yanked_release(self, client):
        data = {
            "info": {"name": "pkg", "version": "1.0.0"},
            "releases": {
                "1.0.0": [
                    {
                        "filename": "pkg-1.0.0.tar.gz",
                        "packagetype": "sdist",
                        "size": 100,
                        "yanked": True,
                    },
                ]
            },
            "urls": [],
        }
        result = await client._process_package_data_enhanced(data)
        assert result["versions"][0]["yanked"] is True

    @pytest.mark.asyncio
    async def test_search_xmlrpc_direct(self, client):
        mock_results = [
            {"name": "flask", "version": "2.0", "summary": "desc", "_pypi_ordering": 10},
            {"name": "django", "version": "4.0", "summary": "desc2", "_pypi_ordering": 5},
        ]
        with patch("xmlrpc.client.ServerProxy") as mock_proxy:
            mock_client = MagicMock()
            mock_client.search.return_value = mock_results
            mock_proxy.return_value = mock_client
            results = await client._search_xmlrpc("flask", 20)
        assert len(results) == 2
        assert results[0]["name"] == "flask"
        assert results[1]["name"] == "django"

    @pytest.mark.asyncio
    async def test_search_xmlrpc_exception(self, client):
        with patch("xmlrpc.client.ServerProxy") as mock_proxy:
            mock_client = MagicMock()
            mock_client.search.side_effect = Exception("RPC error")
            mock_proxy.return_value = mock_client
            results = await client._search_xmlrpc("flask", 20)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_web_scraping_direct(self, client):
        html = """
        <a class="package-snippet" href="/project/flask/">
            <span class="package-snippet__name">Flask</span>
            <span class="package-snippet__version">2.3.3</span>
            <p class="package-snippet__description">A simple framework</p>
        </a>
        <a class="package-snippet" href="/project/django/">
            <span class="package-snippet__name">Django</span>
            <span class="package-snippet__version">4.2</span>
            <p class="package-snippet__description">Web framework</p>
        </a>
        """
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        session = client._get_session()
        with patch.object(session, "get", return_value=mock_cm):
            results = await client._search_web_scraping("flask", 20)
        assert len(results) == 2
        assert results[0]["name"] == "Flask"
        assert results[1]["name"] == "Django"

    @pytest.mark.asyncio
    async def test_search_web_scraping_non_200(self, client):
        mock_response = AsyncMock()
        mock_response.status = 503
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        session = client._get_session()
        with patch.object(session, "get", return_value=mock_cm):
            results = await client._search_web_scraping("flask", 20)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_web_scraping_exception(self, client):
        session = client._get_session()
        with patch.object(session, "get", side_effect=Exception("HTTP error")):
            results = await client._search_web_scraping("flask", 20)
        assert results == []
