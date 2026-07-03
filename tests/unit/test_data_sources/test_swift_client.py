from unittest.mock import AsyncMock, patch

import pytest

from backend.data_sources.swift_client import SwiftClient


class TestSwiftClient:
    @pytest.fixture
    def client(self):
        return SwiftClient()

    @pytest.mark.asyncio
    async def test_get_package_info_success(self, client):
        data = {
            "versions": [{"version": "1.0.0"}, {"version": "0.9.0"}],
            "dependencies": {"Alamofire": "~> 5.0"},
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_package_info("owner/repo")
        assert result is not None
        assert result["name"] == "owner/repo"
        assert result["version"] == "1.0.0"
        assert "versions" in result
        assert "dependencies" in result

    @pytest.mark.asyncio
    async def test_get_package_info_not_found(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info("owner/nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("API error")):
            result = await client.get_package_info("owner/broken")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_no_slash(self, client):
        data = {"versions": [{"version": "1.0.0"}], "dependencies": {}}
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_package_info("single")
        assert result is not None
        assert result["name"] == "single"

    @pytest.mark.asyncio
    async def test_get_package_versions_success(self, client):
        data = {"versions": [{"version": "1.0.0"}, {"version": "0.9.0"}]}
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            versions = await client.get_package_versions("owner/repo")
        assert len(versions) == 2
        assert versions[0]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_package_versions_not_found(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            versions = await client.get_package_versions("owner/nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_package_versions_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("API error")):
            versions = await client.get_package_versions("owner/broken")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_package_info_empty_versions(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={"versions": []}):
            result = await client.get_package_info("owner/empty")
        assert result is not None
        assert result["version"] == "unknown"
        assert result["versions"] == []

    @pytest.mark.asyncio
    async def test_get_package_info_versions_as_strings(self, client):
        data = {"versions": ["1.0.0", "0.9.0"], "dependencies": {}}
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_package_info("owner/repo")
        assert result is not None
        assert result["version"] == "1.0.0"
        assert result["versions"][0]["version"] == "1.0.0"
