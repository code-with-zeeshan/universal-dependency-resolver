from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_sources.conda_client import CondaClient


class TestCondaClient:
    @pytest.fixture
    def client(self):
        return CondaClient()

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
        with patch.object(
            client,
            "_fetch_from_anaconda_api",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ):
            with patch.object(
                client,
                "_extract_dependencies_from_repodata",
                new_callable=AsyncMock,
                return_value={},
            ):
                result = await client.get_package_info_async("numpy")
        assert result is not None
        assert result["name"] == "numpy"
        assert result["version"] == "1.24.3"

    @pytest.mark.asyncio
    async def test_get_package_info_async_calls_correct_url(
        self, client, sample_package_data
    ):
        with patch.object(
            client,
            "_fetch_from_anaconda_api",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ) as mock_fetch:
            with patch.object(
                client,
                "_extract_dependencies_from_repodata",
                new_callable=AsyncMock,
                return_value={},
            ):
                await client.get_package_info_async("numpy")
        mock_fetch.assert_called_once()
        pkg_name, channel = mock_fetch.call_args[0]
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

    def test_package_exists_returns_true(self, client):
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            assert client.package_exists("numpy") is True

    def test_package_exists_returns_false(self, client):
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response
            assert client.package_exists("nonexistent") is False

    def test_package_exists_handles_exception(self, client):
        with patch("requests.get", side_effect=Exception("Network error")):
            assert client.package_exists("numpy") is False

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
        with patch.object(
            client,
            "_fetch_from_anaconda_api",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ):
            with patch.object(
                client,
                "_extract_dependencies_from_repodata",
                new_callable=AsyncMock,
                return_value={},
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
        with patch.object(
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
        ):
            with patch.object(
                client,
                "_extract_dependencies_from_repodata",
                new_callable=AsyncMock,
                return_value={"run": {"python": ">=3.8"}},
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
