from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

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
                "text": ["Google core libraries for Java"],
            }
        ]

    @pytest.fixture
    def sample_search_response(self):
        return {"response": {"docs": [{"g": "com.google.guava", "a": "guava", "latestVersion": "32.1.3-jre", "text": ["Google core libraries for Java"]}]}}

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_search_response):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=sample_search_response,
        ):
            results = await client.search_packages("guava", limit=5)
        assert len(results) == 1
        assert results[0]["name"] == "com.google.guava:guava"

    @pytest.mark.asyncio
    async def test_search_packages_calls_correct_url(
        self, client, sample_search_response
    ):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=sample_search_response,
        ) as mock_get:
            await client.search_packages("guava", limit=5)
        args, kwargs = mock_get.call_args
        url = args[0] if args else ""
        assert "q=guava" in url or kwargs.get("params", {}).get("q") == "guava"

    @pytest.mark.asyncio
    async def test_search_packages_returns_empty_on_failure(self, client):
        with patch.object(client, "_make_request", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException):
                await client.search_packages("nonexistent")

    @pytest.mark.asyncio
    async def test_get_package_info_success(self, client):
        mock_docs = [{"g": "com.google.guava", "a": "guava", "latestVersion": "32.1.3-jre", "versionCount": 10, "repositoryCount": 1, "timestamp": "2023-01-01"}]
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"response": {"docs": mock_docs}})
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client.get_package_info("com.google.guava", "guava")
        assert result is not None
        assert result["info"]["artifact_id"] == "guava"

    @pytest.mark.asyncio
    async def test_get_package_info_calls_correct_url(self, client):
        mock_docs = [{"g": "com.google.guava", "a": "guava", "latestVersion": "32.1.3-jre"}]
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"response": {"docs": mock_docs}})
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            await client.get_package_info("com.google.guava", "guava")
        params = mock_session.get.call_args[1].get("params", {})
        assert "guava" in params.get("q", "")

    @pytest.mark.asyncio
    async def test_get_package_info_not_found(self, client):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"response": {"docs": []}})
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            with pytest.raises(HTTPException) as exc_info:
                await client.get_package_info("com.nonexistent", "missing")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_package_versions_success(self, client):
        mock_docs = [
            {"v": "32.1.3-jre", "timestamp": 1501881872000},
            {"v": "32.1.2-jre", "timestamp": 1501881872000},
            {"v": "32.1.1-jre", "timestamp": 1501881872000},
        ]
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"response": {"docs": mock_docs}})
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            versions = await client.get_package_versions("com.google.guava", "guava")
        assert len(versions) == 3
        assert all("version" in v for v in versions)

    @pytest.mark.asyncio
    async def test_get_package_versions_empty_on_no_data(self, client):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"response": {"docs": []}})
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            versions = await client.get_package_versions("com.nonexistent", "missing")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client):
        with patch.object(
            client,
            "_fetch_and_parse_pom_hierarchy",
            new_callable=AsyncMock,
            return_value={
                "dependencies": [
                    {
                        "name": "com.google.guava:failureaccess",
                        "group_id": "com.google.guava",
                        "artifact_id": "failureaccess",
                        "version": "1.0.1",
                        "scope": "compile",
                        "optional": False,
                        "type": "dependency",
                    }
                ]
            },
        ):
            deps = await client.get_dependencies(
                "com.google.guava", "guava", "32.1.3-jre"
            )
        assert len(deps) == 1
        assert deps[0]["artifact_id"] == "failureaccess"

    @pytest.mark.asyncio
    async def test_get_dependencies_returns_empty_on_error(self, client):
        with patch.object(
            client,
            "_fetch_and_parse_pom_hierarchy",
            new_callable=AsyncMock,
            return_value={"dependencies": []},
        ):
            deps = await client.get_dependencies("com.nonexistent", "missing", "1.0")
        assert deps == []

    @pytest.mark.asyncio
    async def test_check_compatibility_returns_result(self, client):
        with patch.object(client, "_fetch_pom", new_callable=AsyncMock, return_value=None):
            with patch.object(client, "_fetch_and_parse_pom_hierarchy", new_callable=AsyncMock, return_value={"dependencies": []}):
                result = await client.check_compatibility(
                    "com.google.guava", "guava", "32.1.3-jre", {}
                )
        assert isinstance(result, dict)
