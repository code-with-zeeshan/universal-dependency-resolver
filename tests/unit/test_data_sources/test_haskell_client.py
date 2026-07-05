from unittest.mock import AsyncMock, patch

import pytest

from backend.data_sources.haskell_client import HaskellClient


class TestHaskellClient:
    @pytest.fixture
    def client(self):
        return HaskellClient()

    @pytest.mark.asyncio
    async def test_get_package_info_success(self, client):
        data = [{"version": "1.0.0"}, {"version": "0.9.0"}]
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_package_info("my-package")
        assert result is not None
        assert result["name"] == "my-package"
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
        data = [{"version": "2.0.0"}, {"version": "1.0.0"}]
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            versions = await client.get_package_versions("my-package")
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
    async def test_get_package_info_empty_list(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=[]):
            result = await client.get_package_info("empty_pkg")
        # Empty list treated as not found
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_no_versions(self, client):
        # Fake data with no actual versions — client uses first entry
        data = [{"version": "1.0.0"}]
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_package_info("hasversion")
        assert result is not None
        assert result["version"] == "1.0.0"
        assert len(result["versions"]) == 1

    @pytest.mark.asyncio
    async def test_get_package_info_empty_response(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info("missing_pkg")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_versions_as_strings(self, client):
        data = ["1.0.0", "0.9.0"]
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_package_info("str_pkg")
        assert result is not None
        assert result["version"] == "1.0.0"
        assert result["versions"][0]["version"] == "1.0.0"
        assert result["versions"][1]["version"] == "0.9.0"

    @pytest.mark.asyncio
    async def test_get_package_info_preferred_endpoint(self, client):
        data = [{"version": "1.0.0"}]
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data) as mock_get:
            result = await client.get_package_info("test-pkg")
        assert result is not None
        calls = mock_get.call_args_list
        # Should call /package/test-pkg.json
        assert any(".json" in c[0][0] for c in calls)
