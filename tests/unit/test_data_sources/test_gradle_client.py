from unittest.mock import AsyncMock, patch

import pytest

from backend.data_sources.gradle_client import GradleClient


class TestGradleClient:
    @pytest.fixture
    def client(self):
        return GradleClient()

    @pytest.mark.asyncio
    async def test_get_package_info_success(self, client):
        data = {"versions": ["1.0.0", "0.9.0"]}
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_package_info("com.example:lib")
        assert result is not None
        assert result["name"] == "com.example:lib"
        assert result["version"] == "1.0.0"
        assert "versions" in result

    @pytest.mark.asyncio
    async def test_get_package_info_not_found(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info("com.example:nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_exception(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, side_effect=Exception("API error")
        ):
            result = await client.get_package_info("com.example:broken")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_splits_colon(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value={"versions": ["2.0.0"]}
        ) as mock_get:
            result = await client.get_package_info("org.gradle:plugin")
        assert result is not None
        mock_get.assert_called_once()
        url = mock_get.call_args[0][0]
        assert "org.gradle" in url
        assert "plugin" in url

    @pytest.mark.asyncio
    async def test_get_package_info_no_colon_uses_name_as_both(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value={"versions": ["1.0.0"]}
        ):
            result = await client.get_package_info("simple")
        assert result is not None
        assert result["name"] == "simple"

    @pytest.mark.asyncio
    async def test_get_package_versions_success(self, client):
        data = {"versions": ["1.0.0", "0.9.0"]}
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            versions = await client.get_package_versions("com.example:lib")
        assert len(versions) == 2
        assert versions[0]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_package_versions_not_found(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            versions = await client.get_package_versions("com.example:nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_package_versions_exception(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, side_effect=Exception("API error")
        ):
            versions = await client.get_package_versions("com.example:broken")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_package_info_empty_versions(self, client):
        # Empty response body treated as not found
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={}):
            result = await client.get_package_info("com.example:empty")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_no_versions_field(self, client):
        # Response missing 'versions' key — client treats unknown version
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={"name": "pkg"}):
            result = await client.get_package_info("com.example:nover")
        assert result is not None
        assert result["version"] == "unknown"
        assert result["versions"] == []
