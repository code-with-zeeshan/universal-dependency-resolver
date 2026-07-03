from unittest.mock import AsyncMock, patch

import pytest

from backend.data_sources.pub_client import PubClient


class TestPubClient:
    @pytest.fixture
    def client(self):
        return PubClient()

    @pytest.fixture
    def sample_package_data(self):
        return {
            "name": "provider",
            "latest": {
                "version": "1.0.0",
                "pubspec": {
                    "name": "provider",
                    "version": "1.0.0",
                    "description": "A package for state management",
                    "dependencies": {"flutter": {"sdk": "flutter"}},
                    "dev_dependencies": {"test": "^1.16.0"},
                },
            },
            "versions": [
                {
                    "version": "1.0.0",
                    "published": "2023-06-01T00:00:00.000Z",
                    "pubspec": {
                        "name": "provider",
                        "version": "1.0.0",
                        "dependencies": {"flutter": {"sdk": "flutter"}},
                    },
                },
                {
                    "version": "0.9.0",
                    "published": "2023-01-01T00:00:00.000Z",
                    "pubspec": {
                        "name": "provider",
                        "version": "0.9.0",
                        "dependencies": {"flutter": {"sdk": "flutter"}},
                    },
                },
            ],
            "homepage": "https://pub.dev/packages/provider",
            "description": "A package for state management",
        }

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_package_data):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=sample_package_data):
            result = await client.get_package_info("provider")
        assert result is not None
        assert result["name"] == "provider"
        assert result["version"] == "1.0.0"
        assert "dependencies" in result
        assert "versions" in result

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_async_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("API error")):
            result = await client.get_package_info("broken")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_versions_success(self, client, sample_package_data):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=sample_package_data):
            versions = await client.get_package_versions("provider")
        assert len(versions) == 2
        assert versions[0]["version"] == "1.0.0"
        assert versions[1]["version"] == "0.9.0"

    @pytest.mark.asyncio
    async def test_get_package_versions_not_found(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            versions = await client.get_package_versions("nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_package_versions_skips_invalid_versions(self, client):
        data = {
            "name": "bad",
            "versions": [
                {"version": "1.0.0", "published": "2023-01-01", "pubspec": {}},
                {"version": "not-a-version", "published": "2023-01-01", "pubspec": {}},
            ],
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            versions = await client.get_package_versions("bad")
        assert len(versions) == 1
        assert versions[0]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_package_info_skips_flutter_deps(self, client, sample_package_data):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=sample_package_data):
            result = await client.get_package_info("provider")
        assert result is not None
        assert "flutter" not in result.get("dependencies", {}).get("dependencies", {})
        assert "test" in result.get("dependencies", {}).get("dev_dependencies", {})

    @pytest.mark.asyncio
    async def test_get_package_info_skips_invalid_versions(self, client):
        data = {
            "name": "bad",
            "latest": {"version": "1.0.0"},
            "versions": [
                {"version": "1.0.0", "published": "2023-01-01", "pubspec": {"name": "bad"}},
                {"version": "not-a-version", "published": "2023-01-01", "pubspec": {}},
            ],
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_package_info("bad")
        assert result is not None
        assert len(result["versions"]) == 1
        assert result["versions"][0]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_package_info_fallback_to_first_version_pubspec(self, client):
        data = {
            "name": "testpkg",
            "latest": {"version": "1.0.0"},
            "versions": [
                {
                    "version": "1.0.0",
                    "published": "2023-01-01",
                    "pubspec": {
                        "name": "testpkg",
                        "dependencies": {"http": "^1.0.0"},
                    },
                },
            ],
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_package_info("testpkg")
        assert result is not None
        assert "http" in result["dependencies"]["dependencies"]

    @pytest.mark.asyncio
    async def test_get_package_info_non_string_dependency(self, client):
        data = {
            "name": "testpkg",
            "latest": {
                "version": "1.0.0",
                "pubspec": {
                    "name": "testpkg",
                    "dependencies": {
                        "http": {"version": "^1.0.0"},
                    },
                },
            },
            "versions": [
                {
                    "version": "1.0.0",
                    "published": "2023-01-01",
                    "pubspec": {"name": "testpkg"},
                },
            ],
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            result = await client.get_package_info("testpkg")
        assert result is not None
        assert "http" in result["dependencies"]["dependencies"]

    @pytest.mark.asyncio
    async def test_get_package_versions_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("API error")):
            versions = await client.get_package_versions("broken")
        assert versions == []
