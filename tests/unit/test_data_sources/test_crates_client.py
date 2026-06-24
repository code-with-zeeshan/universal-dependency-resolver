from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.data_sources.crates_client import CratesClient


class TestCratesClient:
    @pytest.fixture
    def client(self):
        return CratesClient()

    @pytest.fixture
    def sample_crate_data(self):
        return {
            "crate": {
                "id": "serde",
                "name": "serde",
                "description": "A generic serialization framework",
                "max_version": "1.0.188",
                "repository": "https://github.com/serde-rs/serde",
                "max_stars": 8000,
                "downloads": 50000000,
                "homepage": "https://serde.rs",
                "license": "MIT",
                "documentation": "https://docs.rs/serde",
                "keywords": [],
                "categories": [],
                "created_at": "2023-09-01",
                "updated_at": "2023-09-01",
                "recent_downloads": 1000,
            },
            "versions": [
                {
                    "num": "1.0.188",
                    "created_at": "2023-09-01",
                    "updated_at": "2023-09-01",
                    "license": "MIT",
                    "downloads": 1000000,
                    "yanked": False,
                },
                {
                    "num": "1.0.187",
                    "created_at": "2023-08-15",
                    "updated_at": "2023-08-15",
                    "license": "MIT",
                    "downloads": 900000,
                    "yanked": False,
                },
            ],
        }

    @pytest.fixture
    def sample_search_results(self):
        return {
            "crates": [
                {
                    "id": "serde",
                    "name": "serde",
                    "description": "Serialization framework",
                    "max_version": "1.0.188",
                    "downloads": 50000000,
                    "recent_downloads": 1000,
                    "homepage": "https://serde.rs",
                    "repository": "https://github.com/serde-rs/serde",
                    "documentation": "https://docs.rs/serde",
                    "keywords": [],
                    "categories": [],
                    "created_at": "2023-09-01",
                    "updated_at": "2023-09-01",
                }
            ],
            "meta": {"total": 1},
        }

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_search_results):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=sample_search_results
        ):
            results = await client.search_packages("serde", limit=10)
        assert len(results) == 1
        assert results[0]["name"] == "serde"

    @pytest.mark.asyncio
    async def test_search_packages_calls_correct_url(
        self, client, sample_search_results
    ):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=sample_search_results
        ) as mock_get:
            await client.search_packages("serde", limit=5)
        args, kwargs = mock_get.call_args
        params = kwargs.get("params", {})
        assert params.get("q") == "serde"
        assert params.get("per_page") == 5

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_no_results(self, client):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"crates": [], "meta": {"total": 0}},
        ):
            results = await client.search_packages("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_error(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            results = await client.search_packages("error")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_package_info_success(self, client, sample_crate_data):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=sample_crate_data
        ):
            with patch.object(client, "_get_crate_owners", new_callable=AsyncMock, return_value=[]):
                with patch.object(client, "_get_reverse_dependencies", new_callable=AsyncMock, return_value=0):
                    result = await client.get_package_info("serde")
        assert result is not None
        assert result["name"] == "serde"
        assert result["info"]["latest_version"] == "1.0.188"

    @pytest.mark.asyncio
    async def test_get_package_info_calls_correct_url(self, client, sample_crate_data):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=sample_crate_data
        ) as mock_get:
            with patch.object(client, "_get_crate_owners", new_callable=AsyncMock, return_value=[]):
                with patch.object(client, "_get_reverse_dependencies", new_callable=AsyncMock, return_value=0):
                    await client.get_package_info("serde")
        url = mock_get.call_args[0][0]
        assert "/api/v1/crates/serde" in url

    @pytest.mark.asyncio
    async def test_get_package_info_not_found(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await client.get_package_info("nonexistent")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_package_info_handles_missing_crate_key(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value={"versions": []}
        ):
            with pytest.raises(HTTPException) as exc_info:
                await client.get_package_info("bad-data")
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_get_package_versions_success(self, client, sample_crate_data):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=sample_crate_data
        ):
            with patch.object(client, "_get_version_features", new_callable=AsyncMock, return_value=[]):
                with patch.object(client, "_get_version_msrv", new_callable=AsyncMock, return_value="1.60"):
                    versions = await client.get_package_versions("serde")
        assert len(versions) == 2
        assert versions[0]["version"] == "1.0.188"

    @pytest.mark.asyncio
    async def test_get_package_versions_empty_on_no_data(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await client.get_package_versions("nonexistent")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client):
        mock_deps = {
            "deps": [
                {
                    "crate_id": "serde_derive",
                    "kind": "normal",
                    "req": "^1.0",
                    "optional": False,
                }
            ]
        }
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=mock_deps
        ):
            deps = await client.get_dependencies("serde", "1.0.188")
        assert "normal" in deps

    @pytest.mark.asyncio
    async def test_get_dependencies_empty_on_error(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            deps = await client.get_dependencies("nonexistent", "1.0")
        assert deps == {"normal": [], "dev": [], "build": []}

    @pytest.mark.asyncio
    async def test_check_compatibility_returns_result(self, client, sample_crate_data):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value=sample_crate_data.__class__({"crate": {"id": "serde"}}),
        ):
            with patch.object(client, "check_compatibility") as mock_check:
                mock_check.return_value = {"compatible": True}
                result = await client.check_compatibility("serde", "1.0.188", {})
                assert isinstance(result, dict)
