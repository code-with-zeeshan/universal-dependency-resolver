from unittest.mock import AsyncMock, patch

import pytest

from backend.data_sources.cocoapods_client import CocoaPodsClient


class TestCocoaPodsClient:
    @pytest.fixture
    def client(self):
        return CocoaPodsClient()

    @pytest.fixture
    def sample_pod_data(self):
        return {
            "name": "Alamofire",
            "version": "5.7.1",
            "summary": "Elegant HTTP Networking in Swift",
            "homepage": "https://github.com/Alamofire/Alamofire",
            "license": "MIT",
            "authors": "Alamofire Software Foundation",
            "source": {
                "git": "https://github.com/Alamofire/Alamofire.git",
                "tag": "5.7.1",
            },
            "platforms": {"ios": "10.0", "osx": "10.12"},
            "swift_versions": ["5.3", "5.4", "5.5"],
        }

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_pod_data):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={
                "name": "Alamofire",
                "version": "5.7.1",
                "summary": "Elegant HTTP Networking in Swift",
                "homepage": "https://github.com/Alamofire/Alamofire",
                "license": "MIT",
                "authors": "Alamofire Software Foundation",
                "source": {"git": "https://github.com/Alamofire/Alamofire.git", "tag": "5.7.1"},
                "platforms": {"ios": "10.0", "osx": "10.12"},
                "swift_versions": ["5.3", "5.4", "5.5"],
                "versions": ["5.7.1", "5.7.0"],
            },
        ):
            with patch.object(
                client,
                "_get_podspec",
                new_callable=AsyncMock,
                return_value={
                    "name": "Alamofire",
                    "version": "5.7.1",
                    "description": "Elegant HTTP Networking in Swift",
                    "homepage": "https://github.com/Alamofire/Alamofire",
                    "source": {"git": "https://github.com/Alamofire/Alamofire.git", "tag": "5.7.1"},
                    "license": "MIT",
                    "authors": {"Alamofire Software Foundation": ""},
                    "platforms": {"ios": "10.0", "osx": "10.12"},
                    "swift_versions": ["5.3", "5.4", "5.5"],
                },
            ):
                result = await client.get_package_info_async("Alamofire")
        assert result is not None
        assert result["name"] == "Alamofire"
        assert result["version"] == "5.7.1"

    @pytest.mark.asyncio
    async def test_get_package_info_async_calls_correct_url(self, client, sample_pod_data):
        with (
            patch.object(
                client, "_get", new_callable=AsyncMock, return_value=sample_pod_data
            ) as mock_get,
            patch.object(client, "_get_podspec", new_callable=AsyncMock, return_value={}),
        ):
            await client.get_package_info_async("Alamofire")
        mock_get.assert_called()
        url = mock_get.call_args[0][0]
        assert "alamofire" in url.lower()

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info_async("nonexistent")
        assert result is None

    def test_get_package_info_sync_success(self, client, sample_pod_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_pod_data,
        ):
            result = client.get_package_info("Alamofire")
        assert result is not None
        assert result["name"] == "Alamofire"

    @pytest.mark.asyncio
    async def test_package_exists_returns_true(self, client):
        session = client._get_session()
        with patch.object(session, "get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_get.return_value = mock_response
            assert await client.package_exists("Alamofire") is True
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_package_exists_returns_false(self, client):
        session = client._get_session()
        with patch.object(session, "get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_get.return_value = mock_response
            assert await client.package_exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_package_exists_handles_exception(self, client):
        session = client._get_session()
        with patch.object(session, "get", side_effect=Exception("Network error")):
            assert await client.package_exists("Alamofire") is False

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_pod_data):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=[sample_pod_data]):
            results = await client.search_packages("Alamofire", limit=10)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_no_results(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=[]):
            results = await client.search_packages("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("Error")):
            results = await client.search_packages("Alamofire")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client, sample_pod_data):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"name": "Alamofire", "versions": ["5.7.1", "5.7.0"]},
        ):
            versions = await client.get_versions("Alamofire")
        assert len(versions) >= 1
        assert all("version" in v for v in versions)

    @pytest.mark.asyncio
    async def test_get_versions_empty_when_no_package(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            versions = await client.get_versions("nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client, sample_pod_data):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=sample_pod_data
        ):
            with patch.object(
                client,
                "_get_podspec",
                new_callable=AsyncMock,
                return_value={"dependencies": {"UIKit": ["~> 1.0"]}},
            ):
                deps = await client.get_dependencies("Alamofire", "5.7.1")
        assert isinstance(deps, dict)

    @pytest.mark.asyncio
    async def test_get_dependencies_returns_empty_on_error(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            deps = await client.get_dependencies("nonexistent", "1.0")
        assert deps == {}

    @pytest.mark.asyncio
    async def test_get_dependencies_without_version_fetches_info(self, client):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value={"name": "Alamofire", "version": "5.7.1"},
        ):
            with patch.object(
                client,
                "_get_podspec",
                new_callable=AsyncMock,
                return_value={"dependencies": {"UIKit": ["~> 1.0"]}},
            ):
                deps = await client.get_dependencies("Alamofire")
        assert isinstance(deps, dict)

    @pytest.mark.asyncio
    async def test_get_dependencies_without_version_returns_empty_on_no_info(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            deps = await client.get_dependencies("nonexistent")
        assert deps == {}

    @pytest.mark.asyncio
    async def test_get_package_info_async_no_latest_version(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value={"name": "Foo", "versions": []}
        ):
            result = await client.get_package_info_async("Foo")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_async_no_versions_key(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={"name": "Foo"}):
            result = await client.get_package_info_async("Foo")
        assert result is None

    def test_parse_dependencies_with_subspecs(self, client):
        spec_data = {
            "dependencies": {"UIKit": ["~> 1.0"]},
            "subspecs": [
                {
                    "name": "Core",
                    "dependencies": {"Foundation": ["~> 1.0"]},
                }
            ],
        }
        result = client._parse_dependencies(spec_data)
        assert len(result["dependencies"]) == 2
        assert result["dependencies"][1]["subspec"] == "Core"

    def test_parse_dependencies_with_test_spec(self, client):
        spec_data = {
            "dependencies": {"UIKit": ["~> 1.0"]},
            "test_spec": {
                "dependencies": {"Quick": ["~> 2.0"]},
            },
        }
        result = client._parse_dependencies(spec_data)
        assert len(result["dependencies"]) == 1
        assert len(result["development_dependencies"]) == 1
        assert result["development_dependencies"][0]["name"] == "Quick"

    def test_parse_dependencies_test_spec_not_dict(self, client):
        spec_data = {
            "test_spec": "some_string",
        }
        result = client._parse_dependencies(spec_data)
        assert result == {"dependencies": [], "development_dependencies": []}

    def test_parse_version_spec_string(self, client):
        assert client._parse_version_spec("~> 1.0") == "~> 1.0"

    def test_parse_version_spec_list(self, client):
        assert client._parse_version_spec([">= 1.0", "< 2.0"]) == ">= 1.0, < 2.0"

    def test_parse_version_spec_dict(self, client):
        assert client._parse_version_spec({"git": "https://example.com"}) == str(
            {"git": "https://example.com"}
        )

    def test_parse_version_spec_else(self, client):
        assert client._parse_version_spec(42) == ""

    def test_extract_system_requirements_with_swift_version(self, client):
        spec_data = {"platforms": {"ios": "10.0"}, "swift_version": "5.0"}
        reqs = client._extract_system_requirements(spec_data)
        assert reqs["swift"] == {"version": "5.0"}

    def test_extract_system_requirements_with_swift_versions(self, client):
        spec_data = {"swift_versions": ["5.3", "5.4"]}
        reqs = client._extract_system_requirements(spec_data)
        assert reqs["swift"] == {"versions": ["5.3", "5.4"]}

    def test_extract_system_requirements_frameworks(self, client):
        spec_data = {"frameworks": ["UIKit", "Foundation"]}
        reqs = client._extract_system_requirements(spec_data)
        assert "frameworks" in reqs

    def test_extract_system_requirements_libraries(self, client):
        spec_data = {"libraries": ["xml2", "z"]}
        reqs = client._extract_system_requirements(spec_data)
        assert "libraries" in reqs

    def test_extract_system_requirements_compiler_flags(self, client):
        spec_data = {"compiler_flags": "-ObjC"}
        reqs = client._extract_system_requirements(spec_data)
        assert "compiler_flags" in reqs

    def test_extract_system_requirements_requires_arc(self, client):
        spec_data = {"requires_arc": True}
        reqs = client._extract_system_requirements(spec_data)
        assert reqs["requires_arc"] is True

    def test_extract_system_requirements_platforms_not_dict(self, client):
        spec_data = {"platforms": ["ios"]}
        reqs = client._extract_system_requirements(spec_data)
        assert "ios_deployment_target" not in reqs
