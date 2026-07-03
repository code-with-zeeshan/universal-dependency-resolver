from unittest.mock import AsyncMock, patch

import pytest

from backend.data_sources.hex_client import HexClient


class TestHexClient:
    @pytest.fixture
    def client(self):
        return HexClient()

    @pytest.mark.asyncio
    async def test_get_package_info_success(self, client):
        data = {"releases": [{"version": "1.0.0"}, {"version": "0.9.0"}]}
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_package_info("mypackage")
        assert result is not None
        assert result["name"] == "mypackage"
        assert result["version"] == "1.0.0"
        assert len(result["versions"]) == 2

    @pytest.mark.asyncio
    async def test_get_package_info_not_found(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("API error")):
            result = await client.get_package_info("broken")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_versions_success(self, client):
        data = {"releases": [{"version": "2.0.0"}, {"version": "1.0.0"}]}
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            versions = await client.get_package_versions("my_package")
        assert len(versions) == 2
        assert versions[0]["version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_get_package_versions_not_found(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            versions = await client.get_package_versions("nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_package_versions_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("API error")):
            versions = await client.get_package_versions("broken")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_package_info_empty_releases(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={"releases": []}):
            result = await client.get_package_info("empty_pkg")
        assert result is not None
        assert result["version"] == "unknown"
        assert result["versions"] == []

    @pytest.mark.asyncio
    async def test_get_package_info_empty_response(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={}):
            result = await client.get_package_info("missing_pkg")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_releases_as_strings(self, client):
        data = {"releases": ["1.0.0", "0.9.0"]}
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_package_info("str_pkg")
        assert result is not None
        assert result["version"] == "1.0.0"
        assert result["versions"][0]["version"] == "1.0.0"
        assert result["versions"][1]["version"] == "0.9.0"
