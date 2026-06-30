from unittest.mock import AsyncMock, patch

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

    # === New test: get_package_versions filters out yanked ===
    @pytest.mark.asyncio
    async def test_get_package_versions_exclude_yanked(self, client):
        data = {
            "versions": [
                {"num": "1.0.0", "created_at": "2024-01-01", "updated_at": "2024-01-01", "yanked": False, "downloads": 1000, "license": "MIT"},
                {"num": "1.0.1", "created_at": "2024-02-01", "updated_at": "2024-02-01", "yanked": True, "downloads": 100, "license": "MIT"},
                {"num": "1.0.2", "created_at": "2024-03-01", "updated_at": "2024-03-01", "yanked": False, "downloads": 500, "license": "MIT"},
            ]
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            with patch.object(client, "_get_version_features", new_callable=AsyncMock, return_value={}):
                with patch.object(client, "_get_version_msrv", new_callable=AsyncMock, return_value="1.60"):
                    versions = await client.get_package_versions("serde", filters={"exclude_yanked": True})
        assert len(versions) == 2
        assert all(v["version"] in ("1.0.0", "1.0.2") for v in versions)

    # === New test: get_package_versions filters out prerelease ===
    @pytest.mark.asyncio
    async def test_get_package_versions_exclude_prerelease(self, client):
        data = {
            "versions": [
                {"num": "1.0.0", "created_at": "2023-01-01", "updated_at": "2023-01-01", "yanked": False, "downloads": 1000, "license": "MIT"},
                {"num": "1.1.0-beta.1", "created_at": "2023-06-01", "updated_at": "2023-06-01", "yanked": False, "downloads": 50, "license": "MIT"},
                {"num": "1.1.0", "created_at": "2023-12-01", "updated_at": "2023-12-01", "yanked": False, "downloads": 800, "license": "MIT"},
            ]
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            with patch.object(client, "_get_version_features", new_callable=AsyncMock, return_value={}):
                with patch.object(client, "_get_version_msrv", new_callable=AsyncMock, return_value="1.60"):
                    versions = await client.get_package_versions("serde", filters={"exclude_prerelease": True})
        assert len(versions) == 2
        assert all("beta" not in v["version"] for v in versions)

    # === New test: get_package_versions with version_range filter ===
    @pytest.mark.asyncio
    async def test_get_package_versions_version_range(self, client):
        data = {
            "versions": [
                {"num": "0.8.0", "created_at": "2023-01-01", "updated_at": "2023-01-01", "yanked": False, "downloads": 100, "license": "MIT"},
                {"num": "1.0.0", "created_at": "2024-01-01", "updated_at": "2024-01-01", "yanked": False, "downloads": 500, "license": "MIT"},
                {"num": "2.0.0", "created_at": "2024-06-01", "updated_at": "2024-06-01", "yanked": False, "downloads": 300, "license": "MIT"},
            ]
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            with patch.object(client, "_get_version_features", new_callable=AsyncMock, return_value={}):
                with patch.object(client, "_get_version_msrv", new_callable=AsyncMock, return_value="1.60"):
                    with patch.object(client, "_version_matches_range", side_effect=lambda v, r: v == "1.0.0"):
                        versions = await client.get_package_versions("serde", filters={"version_range": ">=1.0, <2.0"})
        assert len(versions) == 1
        assert versions[0]["version"] == "1.0.0"

    # === New test: get_package_versions with min_rust_version filter ===
    @pytest.mark.asyncio
    async def test_get_package_versions_min_rust_version(self, client):
        data = {
            "versions": [
                {"num": "1.0.0", "created_at": "2024-01-01", "updated_at": "2024-01-01", "yanked": False, "downloads": 500, "license": "MIT"},
                {"num": "2.0.0", "created_at": "2024-06-01", "updated_at": "2024-06-01", "yanked": False, "downloads": 300, "license": "MIT"},
            ]
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            with patch.object(client, "_get_version_features", new_callable=AsyncMock, return_value={}):
                with patch.object(client, "_get_version_msrv", side_effect=["1.65", "1.60"]):
                    with patch.object(client, "_rust_version_compatible", side_effect=[False, True]):
                        versions = await client.get_package_versions("serde", filters={"min_rust_version": "1.60"})
        assert len(versions) == 1
        assert versions[0]["version"] == "2.0.0"

    # === New test: get_package_versions re-raises HTTPException ===
    @pytest.mark.asyncio
    async def test_get_package_versions_http_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=HTTPException(status_code=404, detail="Not found")):
            with pytest.raises(HTTPException) as exc_info:
                await client.get_package_versions("unknown")
        assert exc_info.value.status_code == 404

    # === New test: get_package_versions wraps generic exception ===
    @pytest.mark.asyncio
    async def test_get_package_versions_generic_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=ValueError("connection error")):
            with pytest.raises(HTTPException) as exc_info:
                await client.get_package_versions("bad")
        assert exc_info.value.status_code == 500
        assert "Crates versions error" in exc_info.value.detail

    # === New test: get_dependencies with include_dev=True ===
    @pytest.mark.asyncio
    async def test_get_dependencies_include_dev(self, client):
        mock_data = {
            "dependencies": [
                {"crate_id": "dep1", "kind": "normal", "req": "^1.0", "optional": False, "features": [], "default_features": True},
                {"crate_id": "dep2", "kind": "dev", "req": "^2.0", "optional": False, "features": [], "default_features": True},
            ]
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=mock_data):
            with patch.object(client, "_resolve_version_requirement", new_callable=AsyncMock, return_value=None):
                deps = await client.get_dependencies("serde", "1.0.0", include_dev=True)
        assert len(deps["normal"]) == 1
        assert len(deps["dev"]) == 1
        assert deps["dev"][0]["name"] == "dep2"

    # === New test: get_dependencies with include_build=True ===
    @pytest.mark.asyncio
    async def test_get_dependencies_include_build(self, client):
        mock_data = {
            "dependencies": [
                {"crate_id": "dep1", "kind": "normal", "req": "^1.0", "optional": False, "features": [], "default_features": True},
                {"crate_id": "dep2", "kind": "build", "req": "^3.0", "optional": False, "features": [], "default_features": True},
            ]
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=mock_data):
            with patch.object(client, "_resolve_version_requirement", new_callable=AsyncMock, return_value=None):
                deps = await client.get_dependencies("serde", "1.0.0", include_build=True)
        assert len(deps["normal"]) == 1
        assert len(deps["build"]) == 1
        assert deps["build"][0]["name"] == "dep2"

    # === New test: get_dependencies excludes optional when include_optional=False ===
    @pytest.mark.asyncio
    async def test_get_dependencies_exclude_optional(self, client):
        mock_data = {
            "dependencies": [
                {"crate_id": "dep1", "kind": "normal", "req": "^1.0", "optional": False, "features": [], "default_features": True},
                {"crate_id": "dep2", "kind": "normal", "req": "^1.0", "optional": True, "features": [], "default_features": False},
            ]
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=mock_data):
            with patch.object(client, "_resolve_version_requirement", new_callable=AsyncMock, return_value=None):
                deps = await client.get_dependencies("serde", "1.0.0", include_optional=False)
        assert len(deps["normal"]) == 1
        assert deps["normal"][0]["name"] == "dep1"

    # === New test: get_dependencies resolves version requirement ===
    @pytest.mark.asyncio
    async def test_get_dependencies_resolve_version(self, client):
        mock_data = {
            "dependencies": [
                {"crate_id": "serde_derive", "kind": "normal", "req": "^1.0", "optional": False, "features": [], "default_features": True},
            ]
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=mock_data):
            with patch.object(client, "_resolve_version_requirement", new_callable=AsyncMock, return_value="1.0.188"):
                deps = await client.get_dependencies("serde", "1.0.0")
        assert deps["normal"][0].get("resolved_version") == "1.0.188"

    # === New test: get_dependencies fetches latest version when none provided ===
    @pytest.mark.asyncio
    async def test_get_dependencies_no_version(self, client):
        mock_data = {
            "dependencies": [
                {"crate_id": "dep1", "kind": "normal", "req": "^1.0", "optional": False, "features": [], "default_features": True},
            ]
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=mock_data):
            with patch.object(client, "get_package_info", new_callable=AsyncMock, return_value={"info": {"latest_version": "1.0.0"}}):
                with patch.object(client, "_resolve_version_requirement", new_callable=AsyncMock, return_value=None):
                    deps = await client.get_dependencies("serde")
        assert len(deps["normal"]) == 1
        assert deps["normal"][0]["name"] == "dep1"

    # === New test: _resolve_version_requirement finds matching version ===
    @pytest.mark.asyncio
    async def test_resolve_version_requirement_found(self, client):
        with patch.object(client, "get_package_versions", new_callable=AsyncMock, return_value=[
            {"version": "1.0.0"},
            {"version": "1.1.0"},
            {"version": "2.0.0"},
        ]):
            result = await client._resolve_version_requirement("serde", "^1.0")
        assert result == "1.0.0"

    # === New test: _resolve_version_requirement no match ===
    @pytest.mark.asyncio
    async def test_resolve_version_requirement_not_found(self, client):
        with patch.object(client, "get_package_versions", new_callable=AsyncMock, return_value=[
            {"version": "2.0.0"},
            {"version": "3.0.0"},
        ]):
            result = await client._resolve_version_requirement("serde", "^1.0")
        assert result is None

    # === New test: _resolve_version_requirement handles exception ===
    @pytest.mark.asyncio
    async def test_resolve_version_requirement_exception(self, client):
        with patch.object(client, "get_package_versions", new_callable=AsyncMock, side_effect=Exception("error")):
            result = await client._resolve_version_requirement("serde", "^1.0")
        assert result is None

    # === New test: _get_crate_owners fetches and transforms owner data ===
    @pytest.mark.asyncio
    async def test_get_crate_owners_success(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={
            "users": [
                {"id": 1, "login": "alice", "kind": "user"},
                {"id": 2, "login": "bot", "kind": "team"},
            ]
        }):
            owners = await client._get_crate_owners("serde")
        assert len(owners) == 2
        assert owners[0]["login"] == "alice"
        assert owners[1]["kind"] == "team"

    # === New test: _get_crate_owners returns empty on null response ===
    @pytest.mark.asyncio
    async def test_get_crate_owners_empty(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            owners = await client._get_crate_owners("serde")
        assert owners == []

    # === New test: _get_crate_owners returns empty on exception ===
    @pytest.mark.asyncio
    async def test_get_crate_owners_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("error")):
            owners = await client._get_crate_owners("serde")
        assert owners == []

    # === New test: _get_reverse_dependencies returns total count ===
    @pytest.mark.asyncio
    async def test_get_reverse_dependencies_success(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={
            "meta": {"total": 42}
        }):
            count = await client._get_reverse_dependencies("serde")
        assert count == 42

    # === New test: _get_reverse_dependencies returns 0 on null response ===
    @pytest.mark.asyncio
    async def test_get_reverse_dependencies_empty(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            count = await client._get_reverse_dependencies("serde")
        assert count == 0

    # === New test: _get_reverse_dependencies returns 0 on exception ===
    @pytest.mark.asyncio
    async def test_get_reverse_dependencies_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("error")):
            count = await client._get_reverse_dependencies("serde")
        assert count == 0

    # === New test: _get_version_msrv returns correct MSRV by release year ===
    @pytest.mark.asyncio
    async def test_get_version_msrv_by_year(self, client):
        with patch.object(client, "get_package_versions", new_callable=AsyncMock, return_value=[
            {"version": "0.1.0", "release_date": "2017-06-15T00:00:00Z"},
            {"version": "0.2.0", "release_date": "2018-06-15T00:00:00Z"},
            {"version": "0.3.0", "release_date": "2020-06-15T00:00:00Z"},
            {"version": "0.4.0", "release_date": "2021-06-15T00:00:00Z"},
            {"version": "0.5.0", "release_date": "2023-06-15T00:00:00Z"},
        ]):
            assert await client._get_version_msrv("crate", "0.1.0") == "1.0"
            assert await client._get_version_msrv("crate", "0.2.0") == "1.31"
            assert await client._get_version_msrv("crate", "0.3.0") == "1.45"
            assert await client._get_version_msrv("crate", "0.4.0") == "1.56"
            assert await client._get_version_msrv("crate", "0.5.0") == "1.60"

    # === New test: _get_version_msrv returns None when version not found ===
    @pytest.mark.asyncio
    async def test_get_version_msrv_not_found(self, client):
        with patch.object(client, "get_package_versions", new_callable=AsyncMock, return_value=[
            {"version": "1.0.0", "release_date": "2023-01-01T00:00:00Z"},
        ]):
            msrv = await client._get_version_msrv("crate", "2.0.0")
        assert msrv is None

    # === New test: _get_version_features returns default dict ===
    @pytest.mark.asyncio
    async def test_get_version_features(self, client):
        features = await client._get_version_features("serde", "1.0.0")
        assert features == {"default": True}

    # === New test: _rust_version_compatible correctly compares versions ===
    def test_rust_version_compatible(self, client):
        assert client._rust_version_compatible("1.60.0", "1.60") is True
        assert client._rust_version_compatible("1.65.0", "1.60") is True
        assert client._rust_version_compatible("1.60.0", "1.65") is False
        assert client._rust_version_compatible("1.55.0", "1.60") is False
        assert client._rust_version_compatible("1.60.0", "1.60.0") is True

    # === New test: _rust_version_compatible returns True on parse error ===
    def test_rust_version_compatible_exception_safe(self, client):
        assert client._rust_version_compatible("invalid", "1.60") is True

    # === New test: _version_matches_range single condition ===
    def test_version_matches_range_single(self, client):
        assert client._version_matches_range("1.2.3", ">=1.0.0") is True
        assert client._version_matches_range("0.9.0", ">=1.0.0") is False

    # === New test: _version_matches_range multiple comma-separated conditions ===
    def test_version_matches_range_multiple(self, client):
        assert client._version_matches_range("1.5.0", ">=1.0, <2.0") is True
        assert client._version_matches_range("0.5.0", ">=1.0, <2.0") is False
        assert client._version_matches_range("2.5.0", ">=1.0, <2.0") is False

    # === New test: _version_matches_requirement exact and caret ===
    def test_version_matches_requirement_caret(self, client):
        assert client._version_matches_requirement("1.0.0", "1.0.0") is True
        assert client._version_matches_requirement("1.5.0", "^1.0") is True
        assert client._version_matches_requirement("2.0.0", "^1.0") is False

    # === New test: _version_matches_requirement tilde, comparison, wildcard ===
    def test_version_matches_requirement_other(self, client):
        assert client._version_matches_requirement("1.5.0", "~1.5") is True
        assert client._version_matches_requirement("1.6.0", "~1.5") is False
        assert client._version_matches_requirement("2.0.0", ">=1.0") is True
        assert client._version_matches_requirement("0.5.0", ">=1.0") is False
        assert client._version_matches_requirement("1.0.0", "<2.0") is True
        assert client._version_matches_requirement("42.0.0", "*") is True

    # === New test: get_dependency_tree basic with no deps ===
    @pytest.mark.asyncio
    async def test_get_dependency_tree_basic(self, client):
        with patch.object(client, "get_dependencies", new_callable=AsyncMock, return_value={
            "normal": [],
            "build": [],
            "dev": [],
        }):
            tree = await client.get_dependency_tree("serde", "1.0.0")
        assert tree["name"] == "serde"
        assert tree["version"] == "1.0.0"

    # === New test: get_dependency_tree returns early with max_depth=0 ===
    @pytest.mark.asyncio
    async def test_get_dependency_tree_max_depth_zero(self, client):
        tree = await client.get_dependency_tree("serde", "1.0.0", max_depth=0)
        assert tree["name"] == "serde"
        assert tree["dependencies"] == {}

    # === New test: get_dependency_tree respects visited set ===
    @pytest.mark.asyncio
    async def test_get_dependency_tree_visited(self, client):
        tree = await client.get_dependency_tree("serde", "1.0.0", visited={"serde@1.0.0"})
        assert tree["name"] == "serde"
        assert tree["dependencies"] == {}

    # === New test: get_dependency_tree fetches version from package info ===
    @pytest.mark.asyncio
    async def test_get_dependency_tree_fetches_version(self, client):
        with patch.object(client, "get_package_info", new_callable=AsyncMock, return_value={"info": {"latest_version": "1.0.0"}}):
            with patch.object(client, "get_dependencies", new_callable=AsyncMock, return_value={"normal": [], "build": [], "dev": []}):
                tree = await client.get_dependency_tree("serde")
        assert tree["name"] == "serde"
        assert tree["version"] == "1.0.0"

    # === New test: get_dependency_tree with nested dep ===
    @pytest.mark.asyncio
    async def test_get_dependency_tree_nested(self, client):
        with patch.object(client, "get_dependencies", new_callable=AsyncMock, return_value={
            "normal": [{"name": "dep1", "resolved_version": "0.2.0", "optional": False}],
            "build": [],
            "dev": [],
        }):
            tree = await client.get_dependency_tree("serde", "1.0.0", max_depth=1)
        assert tree["name"] == "serde"
        assert len(tree["dependencies"]["normal"]) == 1

    # === New test: get_dependency_tree skips optional deps ===
    @pytest.mark.asyncio
    async def test_get_dependency_tree_skips_optional(self, client):
        with patch.object(client, "get_dependencies", new_callable=AsyncMock, return_value={
            "normal": [{"name": "opt_dep", "resolved_version": "0.1.0", "optional": True}],
            "build": [],
            "dev": [],
        }):
            tree = await client.get_dependency_tree("serde", "1.0.0")
        assert len(tree["dependencies"]["normal"]) == 0

    # === New test: check_compatibility with incompatible Rust version ===
    @pytest.mark.asyncio
    async def test_check_compatibility_rust_incompatible(self, client):
        with patch.object(client, "get_dependencies", new_callable=AsyncMock, return_value={"normal": [], "dev": [], "build": []}):
            with patch.object(client, "_get_version_msrv", new_callable=AsyncMock, return_value="1.65"):
                result = await client.check_compatibility("serde", "1.0.0", {"rust_version": "1.60.0"})
        assert result["compatible"] is False
        assert any("Requires Rust 1.65" in e for e in result["errors"])

    # === New test: check_compatibility with missing feature ===
    @pytest.mark.asyncio
    async def test_check_compatibility_feature_not_available(self, client):
        with patch.object(client, "get_dependencies", new_callable=AsyncMock, return_value={"normal": [], "dev": [], "build": []}):
            with patch.object(client, "_get_version_msrv", new_callable=AsyncMock, return_value=None):
                with patch.object(client, "_get_version_features", new_callable=AsyncMock, return_value={"default": ["std"]}):
                    result = await client.check_compatibility("serde", "1.0.0", {"enabled_features": ["unknown_feature"]})
        assert result["compatible"] is False
        assert any("unknown_feature" in e for e in result["errors"])

    # === New test: check_compatibility with target dep warning ===
    @pytest.mark.asyncio
    async def test_check_compatibility_target_warning(self, client):
        with patch.object(client, "get_dependencies", new_callable=AsyncMock, return_value={
            "normal": [{"name": "linux-dep", "target": 'cfg(target_os = "linux")', "optional": False, "ecosystem": "crates"}],
            "dev": [],
            "build": [],
        }):
            with patch.object(client, "_get_version_msrv", new_callable=AsyncMock, return_value=None):
                result = await client.check_compatibility("serde", "1.0.0", {"target_triple": "x86_64-pc-windows-msvc"})
        assert len(result["warnings"]) > 0

    # === New test: check_compatibility with system dep library warning ===
    @pytest.mark.asyncio
    async def test_check_compatibility_system_dep_warning(self, client):
        with patch.object(client, "get_dependencies", new_callable=AsyncMock, return_value={
            "normal": [{"name": "openssl-sys", "version_requirement": "^0.9", "optional": False, "ecosystem": "crates"}],
            "dev": [],
            "build": [],
        }):
            with patch.object(client, "_get_version_msrv", new_callable=AsyncMock, return_value=None):
                result = await client.check_compatibility("serde", "1.0.0", {"installed_libraries": []})
        assert len(result["warnings"]) > 0

    # === New test: check_compatibility handles exception gracefully ===
    @pytest.mark.asyncio
    async def test_check_compatibility_exception(self, client):
        with patch.object(client, "get_dependencies", new_callable=AsyncMock, side_effect=Exception("network error")):
            result = await client.check_compatibility("serde", "1.0.0", {})
        assert result["compatible"] is True
        assert any("network error" in w for w in result["warnings"])

    # === New test: get_package_info re-raises HTTPException ===
    @pytest.mark.asyncio
    async def test_get_package_info_http_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=HTTPException(status_code=429, detail="rate limited")):
            with pytest.raises(HTTPException) as exc_info:
                await client.get_package_info("serde")
        assert exc_info.value.status_code == 429

    # === New test: get_package_info wraps generic exception ===
    @pytest.mark.asyncio
    async def test_get_package_info_generic_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=ValueError("bad data")):
            with pytest.raises(HTTPException) as exc_info:
                await client.get_package_info("serde")
        assert exc_info.value.status_code == 500
        assert "Crates package info error" in exc_info.value.detail

    # === New test: get_package_versions skips invalid version strings ===
    @pytest.mark.asyncio
    async def test_get_package_versions_skips_invalid(self, client):
        data = {
            "versions": [
                {"num": "1.0.0", "created_at": "2024-01-01", "updated_at": "2024-01-01", "yanked": False, "downloads": 500, "license": "MIT"},
                {"num": "not-a-version", "created_at": "2024-02-01", "updated_at": "2024-02-01", "yanked": False, "downloads": 0, "license": None},
            ]
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=data):
            with patch.object(client, "_get_version_features", new_callable=AsyncMock, return_value={}):
                with patch.object(client, "_get_version_msrv", new_callable=AsyncMock, return_value="1.60"):
                    versions = await client.get_package_versions("serde")
        assert len(versions) == 1
        assert versions[0]["version"] == "1.0.0"
