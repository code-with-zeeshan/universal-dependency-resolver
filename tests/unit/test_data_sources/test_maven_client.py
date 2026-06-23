from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_sources.maven_client import MavenClient


class TestMavenClient:
    @pytest.fixture
    def client(self):
        return MavenClient()

    @pytest.fixture
    def sample_search_results(self):
        return [
            {
                "id": "com.google.guava:guava",
                "g": "com.google.guava",
                "a": "guava",
                "latestVersion": "32.1.3-jre",
                "score": 100,
                "description": "Google core libraries for Java",
            }
        ]

    @pytest.fixture
    def sample_package_info(self):
        return {
            "groupId": "com.google.guava",
            "artifactId": "guava",
            "version": "32.1.3-jre",
            "description": "Google core libraries for Java",
            "versions": ["32.1.3-jre", "32.1.2-jre", "31.1-jre"],
        }

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_search_results):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"response": {"docs": sample_search_results}},
        ):
            results = await client.search_packages("guava", limit=5)
        assert len(results) == 1
        assert results[0]["id"] == "com.google.guava:guava"

    @pytest.mark.asyncio
    async def test_search_packages_calls_correct_url(
        self, client, sample_search_results
    ):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"response": {"docs": sample_search_results}},
        ) as mock_get:
            await client.search_packages("guava", limit=5)
        url = mock_get.call_args[0][0]
        assert "q=guava" in url
        assert "rows=5" in url

    @pytest.mark.asyncio
    async def test_search_packages_returns_empty_on_failure(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            results = await client.search_packages("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_package_info_success(self, client, sample_package_info):
        with patch.object(
            client,
            "cached_get",
            new_callable=AsyncMock,
            return_value=sample_package_info,
        ):
            result = await client.get_package_info("com.google.guava", "guava")
        assert result is not None
        assert result["artifactId"] == "guava"

    @pytest.mark.asyncio
    async def test_get_package_info_calls_correct_url(
        self, client, sample_package_info
    ):
        with patch.object(
            client,
            "cached_get",
            new_callable=AsyncMock,
            return_value=sample_package_info,
        ) as mock_get:
            await client.get_package_info("com.google.guava", "guava")
        cache_key, url = mock_get.call_args[0]
        assert "guava" in cache_key

    @pytest.mark.asyncio
    async def test_get_package_info_not_found(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=None
        ):
            result = await client.get_package_info("com.nonexistent", "missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_versions_success(self, client, sample_package_info):
        with patch.object(
            client,
            "cached_get",
            new_callable=AsyncMock,
            return_value=sample_package_info,
        ):
            versions = await client.get_package_versions("com.google.guava", "guava")
        assert len(versions) == 3
        assert all("version" in v for v in versions)

    @pytest.mark.asyncio
    async def test_get_package_versions_empty_on_no_data(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=None
        ):
            versions = await client.get_package_versions("com.nonexistent", "missing")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client):
        mock_deps = [
            {
                "groupId": "com.google.guava",
                "artifactId": "failureaccess",
                "version": "1.0.1",
                "scope": "compile",
                "optional": False,
            }
        ]
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=mock_deps
        ):
            deps = await client.get_dependencies(
                "com.google.guava", "guava", "32.1.3-jre"
            )
        assert len(deps) == 1
        assert deps[0]["artifactId"] == "failureaccess"

    @pytest.mark.asyncio
    async def test_get_dependencies_returns_empty_on_error(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=None
        ):
            deps = await client.get_dependencies("com.nonexistent", "missing", "1.0")
        assert deps == []

    @pytest.mark.asyncio
    async def test_check_compatibility_returns_result(self, client):
        with patch.object(client, "cached_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                {"version": "32.1.3-jre", "javaVersion": "1.8"},
                {"response": {"docs": []}},
            ]
            result = await client.check_compatibility(
                "com.google.guava", "guava", "32.1.3-jre", {}
            )
        assert isinstance(result, dict)
