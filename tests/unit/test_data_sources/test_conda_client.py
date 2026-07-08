import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.cache import DictCache
from backend.data_sources.conda_client import CondaClient


class TestCondaClient:
    @pytest.fixture
    def client(self):
        tmpdir = tempfile.mkdtemp()
        cl = CondaClient()
        cl._cache = DictCache(persist_path=os.path.join(tmpdir, "test_cache.json"))
        return cl

    @pytest.fixture
    def sample_package_data(self):
        return {
            "name": "numpy",
            "latest_version": "1.24.3",
            "summary": "NumPy is the fundamental package for array computing with Python.",
            "license": "BSD-3-Clause",
            "home_page": "https://numpy.org",
            "dev_url": "https://github.com/numpy/numpy",
            "doc_url": "https://numpy.org/doc",
            "owner": {"login": "conda-forge"},
            "files": [
                {
                    "version": "1.24.3",
                    "basename": "numpy-1.24.3-py311_0.tar.bz2",
                    "size": 15000000,
                    "upload_time": "2023-04-01",
                    "md5": "abc123",
                    "sha256": "def456",
                    "attrs": {
                        "build": "py311_0",
                        "build_number": 0,
                        "subdir": "noarch",
                        "depends": ["python >=3.8"],
                    },
                }
            ],
            "versions": ["1.24.3", "1.24.2", "1.24.1"],
        }

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_package_data):
        with (
            patch.object(
                client,
                "_fetch_from_anaconda_api",
                new_callable=AsyncMock,
                return_value=sample_package_data,
            ),
            patch.object(
                client,
                "_extract_dependencies_from_repodata",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            result = await client.get_package_info_async("numpy")
        assert result is not None
        assert result["name"] == "numpy"
        assert result["version"] == "1.24.3"

    @pytest.mark.asyncio
    async def test_get_package_info_async_calls_correct_url(self, client, sample_package_data):
        with (
            patch.object(
                client,
                "_fetch_from_anaconda_api",
                new_callable=AsyncMock,
                return_value=sample_package_data,
            ) as mock_fetch,
            patch.object(
                client,
                "_extract_dependencies_from_repodata",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            await client.get_package_info_async("numpy")
        mock_fetch.assert_called_once()
        pkg_name, _channel = mock_fetch.call_args[0]
        assert "numpy" in pkg_name

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(
            client, "_fetch_from_anaconda_api", new_callable=AsyncMock, return_value=None
        ):
            result = await client.get_package_info_async("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_async_handles_bad_data(self, client):
        with patch.object(
            client, "_fetch_from_anaconda_api", new_callable=AsyncMock, return_value=None
        ):
            result = await client.get_package_info_async("bad-pkg")
        assert result is None

    def test_get_package_info_sync_success(self, client, sample_package_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ):
            result = client.get_package_info("numpy")
        assert result is not None
        assert result["name"] == "numpy"

    @pytest.mark.asyncio
    async def test_package_exists_returns_true(self, client):
        session = client._get_session()
        with patch.object(session, "get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_get.return_value = mock_response
            assert await client.package_exists("numpy") is True
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_package_exists_returns_false(self, client):
        session = client._get_session()
        with patch.object(session, "get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_get.return_value = mock_response
            assert await client.package_exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_package_exists_handles_exception(self, client):
        session = client._get_session()
        with patch.object(session, "get", side_effect=Exception("Network error")):
            assert await client.package_exists("numpy") is False

    @pytest.mark.asyncio
    async def test_search_success(self, client, sample_package_data):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[sample_package_data])
        mock_response.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        with patch.object(client, "_get_session", return_value=mock_session):
            results = await client.search("numpy")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_failure(self, client):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[])
        mock_response.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        with patch.object(client, "_get_session", return_value=mock_session):
            results = await client.search("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_exception(self, client):
        mock_response = MagicMock()
        mock_response.__aenter__.side_effect = Exception("Error")
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        with patch.object(client, "_get_session", return_value=mock_session):
            results = await client.search("numpy")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client, sample_package_data):
        with (
            patch.object(
                client,
                "_fetch_from_anaconda_api",
                new_callable=AsyncMock,
                return_value=sample_package_data,
            ),
            patch.object(
                client,
                "_extract_dependencies_from_repodata",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            versions = await client.get_versions("numpy")
        assert len(versions) == 1
        assert all("version" in v for v in versions)

    @pytest.mark.asyncio
    async def test_get_versions_empty_when_no_package(self, client):
        with patch.object(
            client, "_fetch_from_anaconda_api", new_callable=AsyncMock, return_value=None
        ):
            versions = await client.get_versions("nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client):
        with (
            patch.object(
                client,
                "_fetch_from_anaconda_api",
                new_callable=AsyncMock,
                return_value={
                    "name": "numpy",
                    "latest_version": "1.24.3",
                    "summary": "",
                    "files": [
                        {
                            "version": "1.24.3",
                            "basename": "numpy-1.24.3-py311_0.tar.bz2",
                            "size": 15000000,
                            "attrs": {"build": "py311_0", "build_number": 0, "subdir": "noarch"},
                        }
                    ],
                },
            ),
            patch.object(
                client,
                "_extract_dependencies_from_repodata",
                new_callable=AsyncMock,
                return_value={"run": {"python": ">=3.8"}},
            ),
        ):
            deps = await client.get_dependencies("numpy", "1.24.3")
        assert "run" in deps
        assert deps["run"].get("python") == ">=3.8"

    @pytest.mark.asyncio
    async def test_get_dependencies_returns_empty_on_error(self, client):
        with patch.object(
            client, "_fetch_from_anaconda_api", new_callable=AsyncMock, return_value=None
        ):
            deps = await client.get_dependencies("nonexistent", "1.0.0")
        assert deps == {}

    # === New tests below ===

    @pytest.mark.asyncio
    async def test_fetch_from_anaconda_api_success(self, client):
        resp_data = {"name": "numpy", "latest_version": "1.24.3"}
        files_data = [{"version": "1.24.3", "basename": "numpy-1.24.3.tar.bz2", "attrs": {}}]

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=resp_data)
        mock_resp.__aenter__.return_value = mock_resp

        mock_files_resp = MagicMock()
        mock_files_resp.status = 200
        mock_files_resp.json = AsyncMock(return_value=files_data)
        mock_files_resp.__aenter__.return_value = mock_files_resp

        mock_session = MagicMock()
        mock_session.get.side_effect = [mock_resp, mock_files_resp]

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._fetch_from_anaconda_api("numpy", "conda-forge")

        assert result is not None
        assert result["name"] == "numpy"
        assert "files" in result

    @pytest.mark.asyncio
    async def test_fetch_from_anaconda_api_non_200(self, client):
        mock_resp = MagicMock()
        mock_resp.status = 404
        mock_resp.__aenter__.return_value = mock_resp

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._fetch_from_anaconda_api("nonexistent", "conda-forge")

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_from_anaconda_api_exception(self, client):
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Network error")

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._fetch_from_anaconda_api("numpy", "conda-forge")

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_dependencies_from_repodata_cached(self, client):
        from datetime import datetime

        cache_key = "conda-forge:numpy:1.24.3"
        cached = {"run": {"python": ">=3.8"}}
        client._dependency_cache[cache_key] = (cached, datetime.now())

        result = await client._extract_dependencies_from_repodata("numpy", "1.24.3", "conda-forge")

        assert result == cached

    @pytest.mark.asyncio
    async def test_extract_dependencies_from_repodata_not_cached(self, client):
        with patch.object(
            client,
            "_extract_dependencies_from_package_metadata",
            new_callable=AsyncMock,
            return_value={"run": {"python": ">=3.8"}},
        ) as mock_extract:
            result = await client._extract_dependencies_from_repodata(
                "numpy", "1.24.3", "conda-forge"
            )

        assert result == {"run": {"python": ">=3.8"}}
        mock_extract.assert_called_once_with("numpy", "1.24.3", "conda-forge")
        cache_key = "conda-forge:numpy:1.24.3"
        assert cache_key in client._dependency_cache

    @pytest.mark.asyncio
    async def test_fetch_repodata_cached(self, client):
        from datetime import datetime

        cache_key = "conda-forge:linux-64"
        cached = {"packages": {"numpy": {"version": "1.24.3"}}}
        client._repodata_cache[cache_key] = (cached, datetime.now())

        result = await client._fetch_repodata("conda-forge", "linux-64")

        assert result == cached

    @pytest.mark.asyncio
    async def test_fetch_repodata_fetch(self, client):
        repodata = {"packages": {"numpy": {"version": "1.24.3"}}}

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=repodata)
        mock_resp.__aenter__.return_value = mock_resp

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._fetch_repodata("defaults", "linux-64")

        assert result == repodata
        call_url = mock_session.get.call_args[0][0]
        assert "repo.anaconda.com/pkgs/main" in call_url
        assert "linux-64" in call_url

    @pytest.mark.asyncio
    async def test_fetch_repodata_unknown_channel(self, client):
        repodata = {"packages": {}}

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=repodata)
        mock_resp.__aenter__.return_value = mock_resp

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._fetch_repodata("my-custom-channel", "osx-64")

        assert result == repodata
        call_url = mock_session.get.call_args[0][0]
        assert "my-custom-channel" in call_url
        assert "osx-64" in call_url

    @pytest.mark.asyncio
    async def test_extract_dependencies_from_package_metadata(self, client):
        mock_info = {
            "files": [
                {
                    "version": "1.24.3",
                    "attrs": {
                        "depends": ["python >=3.8", "numpy-base >=1.24"],
                        "requirements": {
                            "build": ["cmake >=3.0"],
                            "host": ["gcc_linux-64"],
                        },
                    },
                },
                {
                    "version": "1.24.2",
                    "attrs": {"depends": ["python >=3.7"]},
                },
            ]
        }
        expected = {
            "required": {},
            "build": {"cmake": ">=3.0"},
            "run": {"python": ">=3.8", "numpy-base": ">=1.24"},
            "host": {"gcc_linux-64": "*"},
            "test": {},
        }
        with patch.object(
            client, "_fetch_from_anaconda_api", new_callable=AsyncMock, return_value=mock_info
        ):
            result = await client._extract_dependencies_from_package_metadata(
                "numpy", "1.24.3", "conda-forge"
            )

        assert result == expected

    @pytest.mark.asyncio
    async def test_extract_dependencies_from_package_metadata_no_files(self, client):
        with patch.object(
            client,
            "_fetch_from_anaconda_api",
            new_callable=AsyncMock,
            return_value={"name": "numpy"},
        ):
            result = await client._extract_dependencies_from_package_metadata(
                "numpy", "1.24.3", "conda-forge"
            )

        assert result == {"required": {}, "build": {}, "run": {}, "host": {}, "test": {}}

    @pytest.mark.asyncio
    async def test_get_package_info_async_exception(self, client):
        with patch.object(
            client,
            "_fetch_from_anaconda_api",
            new_callable=AsyncMock,
            side_effect=Exception("Boom"),
        ):
            result = await client.get_package_info_async("numpy")

        assert result is None

    def test_extract_deps_from_files(self, client):
        files = [
            {
                "version": "1.24.3",
                "attrs": {
                    "depends": ["python >=3.8", "libblas >=3.9"],
                },
            }
        ]
        result = client._extract_deps_from_files(files)
        assert result["run"]["python"] == ">=3.8"
        assert result["run"]["libblas"] == ">=3.9"

    def test_parse_conda_dependency_edge_cases(self, client):
        name, constraint = client._parse_conda_dependency("python >=3.8")
        assert name == "python"
        assert constraint == ">=3.8"

        name, constraint = client._parse_conda_dependency("numpy 1.24.*")
        assert name == "numpy"
        assert ">=" in constraint

        name, constraint = client._parse_conda_dependency("pkg 1.2.3")
        assert name == "pkg"
        assert constraint == "==1.2.3"

        name, constraint = client._parse_conda_dependency("python")
        assert name == "python"
        assert constraint == "*"

        name, constraint = client._parse_conda_dependency("")
        assert name is None

        name, constraint = client._parse_conda_dependency(123)
        assert name is None

    def test_extract_system_requirements_cuda(self, client):
        data = {
            "name": "cupy-cuda117",
            "summary": "",
            "description": "CuPy CUDA accelerated",
        }
        files = [
            {
                "attrs": {
                    "build": "py311_cuda118_0",
                    "subdir": "linux-64",
                    "depends": ["python >=3.8"],
                }
            }
        ]
        result = client._extract_system_requirements(data, files)
        assert "gpu" in result
        assert result["gpu"]["required"] is True
        assert "cuda_versions_supported" in result["gpu"]

    def test_extract_system_requirements_platform(self, client):
        data = {"name": "some-package", "summary": "", "description": ""}
        files = [
            {
                "attrs": {
                    "build": "py311_0",
                    "subdir": "linux-64",
                    "depends": [],
                }
            },
            {
                "attrs": {
                    "build": "py311_0",
                    "subdir": "win-64",
                    "depends": [],
                }
            },
        ]
        result = client._extract_system_requirements(data, files)
        assert "platform" in result
        assert "linux-64" in result["platform"]["supported"]
        assert "win-64" in result["platform"]["supported"]

    def test_parse_recipe_metadata(self, client):
        recipe = {
            "package": {"name": "numpy", "version": "1.24.3"},
            "requirements": {
                "build": ["cmake"],
                "host": ["python"],
                "run": ["python >=3.8", "numpy-base"],
            },
            "about": {
                "home": "https://numpy.org",
                "license": "BSD-3",
                "summary": "NumPy numeric library",
            },
        }
        result = client._parse_recipe_metadata(recipe)
        assert result["name"] == "numpy"
        assert result["version"] == "1.24.3"
        assert "python >=3.8" in result["depends"]
        assert result["home"] == "https://numpy.org"
        assert result["license"] == "BSD-3"

    @pytest.mark.asyncio
    async def test_get_dependencies_caching(self, client):
        info = {
            "name": "numpy",
            "latest_version": "1.24.3",
            "summary": "",
            "channel": "conda-forge",
            "files": [
                {
                    "version": "1.24.3",
                    "basename": "numpy-1.24.3-py311_0.tar.bz2",
                    "attrs": {"build": "py311_0", "build_number": 0, "subdir": "noarch"},
                }
            ],
        }
        with (
            patch.object(
                client, "_fetch_from_anaconda_api", new_callable=AsyncMock, return_value=info
            ),
            patch.object(
                client,
                "_extract_dependencies_from_repodata",
                new_callable=AsyncMock,
                return_value={"run": {"python": ">=3.8"}},
            ) as mock_extract,
        ):
            deps1 = await client.get_dependencies("numpy", "1.24.3")
            assert deps1 == {"run": {"python": ">=3.8"}}
            mock_extract.assert_called_once()

            deps2 = await client.get_dependencies("numpy", "1.24.3")
            assert deps2 == {"run": {"python": ">=3.8"}}
            mock_extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_dependencies_without_version(self, client):
        info = {
            "name": "numpy",
            "latest_version": "1.24.3",
            "summary": "",
            "channel": "conda-forge",
            "files": [
                {
                    "version": "1.24.3",
                    "basename": "numpy-1.24.3-py311_0.tar.bz2",
                    "attrs": {"build": "py311_0", "build_number": 0, "subdir": "noarch"},
                }
            ],
        }
        with (
            patch.object(
                client, "_fetch_from_anaconda_api", new_callable=AsyncMock, return_value=info
            ),
            patch.object(
                client,
                "_extract_dependencies_from_repodata",
                new_callable=AsyncMock,
                return_value={"run": {"python": ">=3.8"}},
            ),
        ):
            deps = await client.get_dependencies("numpy")

        assert deps == {"run": {"python": ">=3.8"}}

    @pytest.mark.asyncio
    async def test_search_non_200(self, client):
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_resp.__aenter__.return_value = mock_resp

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        with patch.object(client, "_get_session", return_value=mock_session):
            results = await client.search("numpy")

        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_repodata_exception(self, client):
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Timeout")

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._fetch_repodata("conda-forge", "linux-64")

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_repodata_non_200(self, client):
        mock_resp = MagicMock()
        mock_resp.status = 404
        mock_resp.__aenter__.return_value = mock_resp

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._fetch_repodata("conda-forge", "linux-64")

        assert result is None

    def test_extract_system_requirements_no_latest_version(self, client):
        data = {"name": "numpy", "summary": "", "description": ""}
        files = [{"attrs": {"build": "py311_0", "subdir": "noarch", "depends": ["python >=3.8"]}}]
        result = client._extract_system_requirements(data, files)
        assert "python" in result

    def test_extract_system_requirements_mkl(self, client):
        data = {"name": "mkl-service", "summary": "", "description": ""}
        files = [{"attrs": {"build": "py311_0", "subdir": "noarch", "depends": []}}]
        result = client._extract_system_requirements(data, files)
        assert "mkl" in result

    def test_extract_system_requirements_openmp(self, client):
        data = {"name": "pkg", "summary": "", "description": "requires libgomp support"}
        files = [{"attrs": {"build": "py311_0", "subdir": "noarch", "depends": []}}]
        result = client._extract_system_requirements(data, files)
        assert "openmp" in result

    def test_parse_conda_dependency_unrecognized(self, client):
        _name, constraint = client._parse_conda_dependency("@#$invalid")
        assert constraint == "*"

    def test_parse_conda_dependency_wildcard_parse_fail(self, client):
        name, constraint = client._parse_conda_dependency("pkg 1.*")
        assert name == "pkg"
        assert constraint is not None

    @pytest.mark.asyncio
    async def test_get_dependencies_without_version_not_found(self, client):
        with patch.object(
            client, "_fetch_from_anaconda_api", new_callable=AsyncMock, return_value=None
        ):
            deps = await client.get_dependencies("nonexistent")
        assert deps == {}

    @pytest.mark.asyncio
    async def test_get_package_info_async_derives_latest_version(self, client):
        data = {
            "name": "mypkg",
            "files": [
                {
                    "version": "2.0.0",
                    "basename": "mypkg-2.0.0.tar.bz2",
                    "attrs": {
                        "build": "py311_0",
                        "build_number": 0,
                        "subdir": "noarch",
                        "depends": [],
                    },
                },
                {
                    "version": "1.0.0",
                    "basename": "mypkg-1.0.0.tar.bz2",
                    "attrs": {
                        "build": "py311_0",
                        "build_number": 0,
                        "subdir": "noarch",
                        "depends": [],
                    },
                },
            ],
        }
        with patch.object(
            client, "_fetch_from_anaconda_api", new_callable=AsyncMock, return_value=data
        ):
            with patch.object(
                client,
                "_extract_dependencies_from_repodata",
                new_callable=AsyncMock,
                return_value={},
            ):
                result = await client.get_package_info_async("mypkg")
        assert result is not None
        assert result["version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_extract_dependencies_from_package_metadata_exception(self, client):
        with patch.object(
            client,
            "_fetch_from_anaconda_api",
            new_callable=AsyncMock,
            side_effect=Exception("API fail"),
        ):
            result = await client._extract_dependencies_from_package_metadata(
                "numpy", "1.24.3", "conda-forge"
            )
        assert result == {"required": {}, "build": {}, "run": {}, "host": {}, "test": {}}

    def test_extract_system_requirements_cuda_edge_cases(self, client):
        data = {"name": "cupy-cuda11", "summary": "", "description": ""}
        files = [
            {
                "attrs": {
                    "build": "py38_cu118_0",
                    "subdir": "linux-64",
                    "depends": [],
                }
            },
            {
                "attrs": {
                    "build": "py38_cu11_0",
                    "subdir": "linux-64",
                    "depends": [],
                }
            },
        ]
        result = client._extract_system_requirements(data, files)
        assert "gpu" in result
        assert "cuda_version" in result["gpu"]
        assert "11.x" in result["gpu"]["cuda_versions_supported"]

    def test_extract_system_requirements_cuda_cu_fallback(self, client):
        data = {"name": "pkg", "summary": "", "description": ""}
        files = [
            {
                "attrs": {
                    "build": "cuda_hello_cu118",
                    "subdir": "linux-64",
                    "depends": [],
                }
            },
            {
                "attrs": {
                    "build": "cuda_hello_cu11",
                    "subdir": "linux-64",
                    "depends": [],
                }
            },
        ]
        result = client._extract_system_requirements(data, files)
        assert "gpu" in result
        assert "cuda_versions_supported" in result["gpu"]

    def test_parse_recipe_metadata_requirements_as_list(self, client):
        recipe = {
            "package": {"name": "pkg", "version": "1.0"},
            "requirements": ["python >=3.8", "numpy"],
            "about": {"home": "", "license": "", "summary": ""},
        }
        result = client._parse_recipe_metadata(recipe)
        assert "python >=3.8" in result["depends"]

    @pytest.mark.asyncio
    async def test_get_package_info_async_skips_invalid_version(self, client):
        data = {
            "name": "mypkg",
            "latest_version": "1.0.0",
            "files": [
                {
                    "version": "invalid",
                    "basename": "mypkg-invalid.tar.bz2",
                    "attrs": {
                        "build": "py311_0",
                        "build_number": 0,
                        "subdir": "noarch",
                        "depends": [],
                    },
                },
                {
                    "version": "1.0.0",
                    "basename": "mypkg-1.0.0.tar.bz2",
                    "attrs": {
                        "build": "py311_0",
                        "build_number": 0,
                        "subdir": "noarch",
                        "depends": [],
                    },
                },
            ],
        }
        with patch.object(
            client, "_fetch_from_anaconda_api", new_callable=AsyncMock, return_value=data
        ):
            with patch.object(
                client,
                "_extract_dependencies_from_repodata",
                new_callable=AsyncMock,
                return_value={},
            ):
                result = await client.get_package_info_async("mypkg")
        assert result is not None
        versions = result.get("versions", [])
        assert len(versions) == 1
