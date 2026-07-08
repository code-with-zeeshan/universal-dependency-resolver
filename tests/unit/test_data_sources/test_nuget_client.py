from unittest.mock import AsyncMock, patch

import pytest

from backend.data_sources.nuget_client import NuGetClient


class TestNuGetClient:
    @pytest.fixture
    def client(self):
        return NuGetClient()

    @pytest.fixture
    def sample_package_data(self):
        return {
            "@id": "https://api.nuget.org/v3/registration5-semver1/newtonsoft.json/index.json",
            "id": "Newtonsoft.Json",
            "version": "13.0.3",
            "description": "Json.NET is a popular high-performance JSON framework for .NET",
            "authors": "James Newton-King",
            "licenseUrl": "https://licenses.nuget.org/MIT",
            "projectUrl": "https://www.newtonsoft.com/json",
            "tags": ["json", "serialization", "framework"],
            "published": "2023-08-15T00:00:00+00:00",
            "dependencyGroups": [
                {
                    "@type": "PackageDependencyGroup",
                    "targetFramework": ".NETStandard2.0",
                    "dependencies": [],
                }
            ],
        }

    @pytest.fixture
    def sample_search_results(self):
        return {
            "data": [
                {
                    "id": "Newtonsoft.Json",
                    "version": "13.0.3",
                    "description": "JSON framework for .NET",
                    "totalDownloads": 3000000000,
                    "tags": ["json", "serialization"],
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_package_data):
        client.registration_base_url = "https://api.nuget.org/v3/registration5-semver1"
        mock_registration = {
            "count": 1,
            "items": [
                {
                    "items": [
                        {
                            "catalogEntry": sample_package_data,
                        }
                    ]
                }
            ],
        }
        with (
            patch.object(
                client,
                "_initialize_service_endpoints",
                new_callable=AsyncMock,
            ),
            patch.object(
                client,
                "_get",
                new_callable=AsyncMock,
                return_value=mock_registration,
            ),
        ):
            result = await client.get_package_info_async("Newtonsoft.Json")
        assert result is not None
        assert result["name"] == "newtonsoft.json"
        assert result["version"] == "13.0.3"

    @pytest.mark.asyncio
    async def test_get_package_info_async_calls_correct_url(self, client, sample_package_data):
        client.registration_base_url = "https://api.nuget.org/v3/registration5-semver1"
        mock_registration = {
            "count": 1,
            "items": [
                {
                    "items": [
                        {
                            "catalogEntry": sample_package_data,
                        }
                    ]
                }
            ],
        }
        with (
            patch.object(
                client,
                "_initialize_service_endpoints",
                new_callable=AsyncMock,
            ),
            patch.object(
                client,
                "_get",
                new_callable=AsyncMock,
                return_value=mock_registration,
            ) as mock_get,
        ):
            await client.get_package_info_async("Newtonsoft.Json")
        mock_get.assert_called_once()
        url = mock_get.call_args[0][0]
        assert "newtonsoft.json" in url.lower()

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        client.registration_base_url = "https://api.nuget.org/v3/registration5-semver1"
        with (
            patch.object(
                client,
                "_initialize_service_endpoints",
                new_callable=AsyncMock,
            ),
            patch.object(client, "_get", new_callable=AsyncMock, return_value=None),
        ):
            result = await client.get_package_info_async("Nonexistent.Package")
        assert result is None

    def test_get_package_info_sync_success(self, client, sample_package_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ):
            result = client.get_package_info("Newtonsoft.Json")
        assert result is not None
        assert result["id"] == "Newtonsoft.Json"

    @pytest.mark.asyncio
    async def test_package_exists_returns_true(self, client):
        session = client._get_session()
        with patch.object(session, "head", new_callable=AsyncMock) as mock_head:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_head.return_value = mock_response
            assert await client.package_exists("Newtonsoft.Json") is True
            mock_head.assert_called_once()

    @pytest.mark.asyncio
    async def test_package_exists_returns_false(self, client):
        session = client._get_session()
        with patch.object(session, "head", new_callable=AsyncMock) as mock_head:
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_head.return_value = mock_response
            assert await client.package_exists("Nonexistent.Package") is False

    @pytest.mark.asyncio
    async def test_package_exists_handles_exception(self, client):
        session = client._get_session()
        with patch.object(session, "head", side_effect=Exception("Network error")):
            assert await client.package_exists("Newtonsoft.Json") is False

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_search_results):
        client.search_url = "https://azuresearch-usnc.nuget.org/query"
        with (
            patch.object(
                client,
                "_initialize_service_endpoints",
                new_callable=AsyncMock,
            ),
            patch.object(
                client, "_get", new_callable=AsyncMock, return_value=sample_search_results
            ),
        ):
            results = await client.search_packages("json", limit=10)
        assert len(results) == 1
        assert results[0]["name"] == "Newtonsoft.Json"

    @pytest.mark.asyncio
    async def test_search_packages_calls_correct_url(self, client, sample_search_results):
        client.search_url = "https://azuresearch-usnc.nuget.org/query"
        with (
            patch.object(
                client,
                "_initialize_service_endpoints",
                new_callable=AsyncMock,
            ),
            patch.object(
                client, "_get", new_callable=AsyncMock, return_value=sample_search_results
            ) as mock_get,
        ):
            await client.search_packages("json", limit=5)
        _args, kwargs = mock_get.call_args
        params = kwargs.get("params", {})
        assert params.get("q") == "json"
        assert params.get("take") == 5

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_no_results(self, client):
        client.search_url = "https://azuresearch-usnc.nuget.org/query"
        with (
            patch.object(
                client,
                "_initialize_service_endpoints",
                new_callable=AsyncMock,
            ),
            patch.object(client, "_get", new_callable=AsyncMock, return_value={"data": []}),
        ):
            results = await client.search_packages("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_exception(self, client):
        client.search_url = "https://azuresearch-usnc.nuget.org/query"
        with (
            patch.object(
                client,
                "_initialize_service_endpoints",
                new_callable=AsyncMock,
            ),
            patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("Error")),
        ):
            results = await client.search_packages("json")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_with_prerelease_filter(self, client, sample_search_results):
        client.search_url = "https://azuresearch-usnc.nuget.org/query"
        with (
            patch.object(
                client,
                "_initialize_service_endpoints",
                new_callable=AsyncMock,
            ),
            patch.object(
                client, "_get", new_callable=AsyncMock, return_value=sample_search_results
            ) as mock_get,
        ):
            await client.search_packages("json", include_prerelease=True)
        _args, kwargs = mock_get.call_args
        params = kwargs.get("params", {})
        assert params.get("prerelease") == "true"

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client):
        client.registration_base_url = "https://api.nuget.org/v3/registration5-semver1"
        mock_registration = {
            "count": 2,
            "items": [
                {
                    "items": [
                        {
                            "catalogEntry": {
                                "version": "13.0.3",
                                "published": "2023-08-15",
                                "projectUrl": "https://newtonsoft.com",
                            }
                        },
                        {
                            "catalogEntry": {
                                "version": "13.0.2",
                                "published": "2023-06-01",
                                "projectUrl": "https://newtonsoft.com",
                            }
                        },
                    ]
                }
            ],
        }
        with (
            patch.object(
                client,
                "_initialize_service_endpoints",
                new_callable=AsyncMock,
            ),
            patch.object(client, "_get", new_callable=AsyncMock, return_value=mock_registration),
        ):
            versions = await client.get_versions("Newtonsoft.Json")
        assert len(versions) >= 1
        assert all("version" in v for v in versions)

    @pytest.mark.asyncio
    async def test_get_versions_empty_on_no_package(self, client):
        client.registration_base_url = "https://api.nuget.org/v3/registration5-semver1"
        with (
            patch.object(
                client,
                "_initialize_service_endpoints",
                new_callable=AsyncMock,
            ),
            patch.object(client, "_get", new_callable=AsyncMock, return_value=None),
        ):
            versions = await client.get_versions("Nonexistent.Package")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_package_version_success(self, client, sample_package_data):
        client.registration_base_url = "https://api.nuget.org/v3/registration5-semver1"
        mock_version_data = {
            "catalogEntry": sample_package_data,
        }
        with (
            patch.object(
                client,
                "_initialize_service_endpoints",
                new_callable=AsyncMock,
            ),
            patch.object(
                client,
                "_get",
                new_callable=AsyncMock,
                return_value=mock_version_data,
            ),
        ):
            result = await client.get_package_version("Newtonsoft.Json", "13.0.3")
        assert result is not None
        assert result["version"] == "13.0.3"

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client, sample_package_data):
        client.registration_base_url = "https://api.nuget.org/v3/registration5-semver1"
        mock_version_data = {
            "catalogEntry": sample_package_data,
        }
        with (
            patch.object(
                client,
                "_initialize_service_endpoints",
                new_callable=AsyncMock,
            ),
            patch.object(
                client,
                "_get",
                new_callable=AsyncMock,
                return_value=mock_version_data,
            ),
        ):
            deps = await client.get_dependencies("Newtonsoft.Json", "13.0.3")
        assert isinstance(deps, dict)

    @pytest.mark.asyncio
    async def test_get_dependencies_empty_on_error(self, client):
        client.registration_base_url = "https://api.nuget.org/v3/registration5-semver1"
        with (
            patch.object(
                client,
                "_initialize_service_endpoints",
                new_callable=AsyncMock,
            ),
            patch.object(client, "_get", new_callable=AsyncMock, return_value=None),
        ):
            deps = await client.get_dependencies("Nonexistent.Package", "1.0")
        assert deps == {}

    @pytest.mark.asyncio
    async def test_check_compatibility_returns_result(self, client, sample_package_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ):
            result = await client.check_compatibility("Newtonsoft.Json", "13.0.3", {})
        assert isinstance(result, dict)

    # ─── __aenter__ ────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_aenter_calls_initialize(self):
        client = NuGetClient()
        with patch.object(
            client, "_initialize_service_endpoints", new_callable=AsyncMock
        ) as mock_init:
            async with client as c:
                assert c is client
            mock_init.assert_awaited_once()

    # ─── _initialize_service_endpoints ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_initialize_endpoints_early_return_when_already_set(self):
        client = NuGetClient()
        client._service_endpoints = {"already": "set"}
        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            await client._initialize_service_endpoints()
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_endpoints_sets_fallbacks_when_no_resources(self):
        client = NuGetClient()
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={}):
            await client._initialize_service_endpoints()
        assert client.search_url == "https://azuresearch-usnc.nuget.org/query"
        assert client.package_base_url == "https://api.nuget.org/v3-flatcontainer"
        assert client.registration_base_url == "https://api.nuget.org/v3/registration5-semver1"

    @pytest.mark.asyncio
    async def test_initialize_endpoints_fallbacks_on_exception(self):
        client = NuGetClient()
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("boom")):
            await client._initialize_service_endpoints()
        assert client.search_url == "https://azuresearch-usnc.nuget.org/query"

    # ─── _set_fallback_endpoints ───────────────────────────────────────────────

    def test_set_fallback_endpoints(self):
        client = NuGetClient()
        client.search_url = None
        client.package_base_url = None
        client.registration_base_url = None
        client._set_fallback_endpoints()
        assert client.search_url == "https://azuresearch-usnc.nuget.org/query"
        assert client.package_base_url == "https://api.nuget.org/v3-flatcontainer"
        assert client.registration_base_url == "https://api.nuget.org/v3/registration5-semver1"

    # ─── search_packages ───────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_search_packages_initializes_endpoints_when_search_url_none(self):
        client = NuGetClient()
        client.search_url = None
        with (
            patch.object(
                client, "_initialize_service_endpoints", new_callable=AsyncMock
            ) as mock_init,
            patch.object(client, "_get", new_callable=AsyncMock, return_value={"data": []}),
        ):
            await client.search_packages("json")
        mock_init.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_packages_with_target_framework(self):
        client = NuGetClient()
        client.search_url = "https://azuresearch-usnc.nuget.org/query"
        with (
            patch.object(client, "_initialize_service_endpoints", new_callable=AsyncMock),
            patch.object(
                client, "_get", new_callable=AsyncMock, return_value={"data": []}
            ) as mock_get,
        ):
            await client.search_packages("json", target_framework="net6.0")
        params = mock_get.call_args[1]["params"]
        assert params["supportedFramework"] == "net6.0"

    @pytest.mark.asyncio
    async def test_search_packages_returns_empty_when_no_data_key(self):
        client = NuGetClient()
        client.search_url = "https://azuresearch-usnc.nuget.org/query"
        with (
            patch.object(client, "_initialize_service_endpoints", new_callable=AsyncMock),
            patch.object(client, "_get", new_callable=AsyncMock, return_value={"nope": "x"}),
        ):
            results = await client.search_packages("json")
        assert results == []

    # ─── get_package_info_async ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_package_info_async_initializes_endpoints_when_base_url_none(self):
        client = NuGetClient()
        client.registration_base_url = None
        with (
            patch.object(
                client, "_initialize_service_endpoints", new_callable=AsyncMock
            ) as mock_init,
            patch.object(client, "_get", new_callable=AsyncMock, return_value=None),
        ):
            await client.get_package_info_async("Newtonsoft.Json")
        mock_init.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_package_info_async_fetches_paginated_items(self):
        client = NuGetClient()
        client.registration_base_url = "https://api.nuget.org/v3/registration5-semver1"
        page_url = "https://api.nuget.org/v3/registration5-semver1/newtonsoft.json/page/1"
        mock_registration = {
            "count": 2,
            "items": [
                {
                    "@id": page_url,
                }
            ],
        }
        mock_page = {
            "items": [
                {
                    "catalogEntry": {
                        "version": "13.0.3",
                        "description": "JSON framework",
                        "authors": "James Newton-King",
                        "published": "2023-08-15T00:00:00+00:00",
                        "dependencyGroups": [],
                    }
                }
            ]
        }
        with (
            patch.object(client, "_initialize_service_endpoints", new_callable=AsyncMock),
            patch.object(
                client, "_get", new_callable=AsyncMock, side_effect=[mock_registration, mock_page]
            ),
        ):
            result = await client.get_package_info_async("Newtonsoft.Json")
        assert result is not None
        assert result["version"] == "13.0.3"

    # ─── get_versions ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_versions_filters_prereleases(self):
        client = NuGetClient()
        client.registration_base_url = "https://api.nuget.org/v3/registration5-semver1"
        mock_registration = {
            "count": 2,
            "items": [
                {
                    "items": [
                        {"catalogEntry": {"version": "13.0.3", "dependencyGroups": []}},
                        {"catalogEntry": {"version": "14.0.0-beta1", "dependencyGroups": []}},
                    ]
                }
            ],
        }
        with (
            patch.object(client, "_initialize_service_endpoints", new_callable=AsyncMock),
            patch.object(client, "_get", new_callable=AsyncMock, return_value=mock_registration),
        ):
            versions = await client.get_versions("Newtonsoft.Json", include_prereleases=False)
        versions_str = [v["version"] for v in versions]
        assert "14.0.0-beta1" not in versions_str
        assert "13.0.3" in versions_str

    @pytest.mark.asyncio
    async def test_get_versions_filters_unlisted(self):
        client = NuGetClient()
        client.registration_base_url = "https://api.nuget.org/v3/registration5-semver1"
        mock_registration = {
            "count": 2,
            "items": [
                {
                    "items": [
                        {"catalogEntry": {"version": "13.0.3", "dependencyGroups": []}},
                        {
                            "catalogEntry": {
                                "version": "13.0.2",
                                "listed": False,
                                "dependencyGroups": [],
                            }
                        },
                    ]
                }
            ],
        }
        with (
            patch.object(client, "_initialize_service_endpoints", new_callable=AsyncMock),
            patch.object(client, "_get", new_callable=AsyncMock, return_value=mock_registration),
        ):
            versions = await client.get_versions("Newtonsoft.Json", include_unlisted=False)
        versions_str = [v["version"] for v in versions]
        assert "13.0.2" not in versions_str

    # ─── get_dependencies ──────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_dependencies_without_version(self, client):
        with patch.object(client, "get_package_info_async", new_callable=AsyncMock) as mock_info:
            mock_info.return_value = {
                "dependencies": {
                    ".NETStandard2.0": {"Newtonsoft.Json.Bson": {"version_range": "[1.0.0,)"}}
                }
            }
            deps = await client.get_dependencies("Newtonsoft.Json")
        assert ".NETStandard2.0" in deps

    @pytest.mark.asyncio
    async def test_get_dependencies_with_target_framework(self):
        client = NuGetClient()
        client.registration_base_url = "https://api.nuget.org/v3/registration5-semver1"
        version_data = {
            "catalogEntry": {
                "version": "13.0.3",
                "dependencyGroups": [
                    {
                        "targetFramework": ".NETStandard2.0",
                        "dependencies": [{"id": "Newtonsoft.Json.Bson", "range": "[1.0.0,)"}],
                    },
                    {
                        "targetFramework": "net6.0",
                        "dependencies": [{"id": "Some.Package", "range": "[2.0.0,)"}],
                    },
                ],
            }
        }
        with patch.object(client, "_initialize_service_endpoints", new_callable=AsyncMock):
            with patch.object(client, "_get", new_callable=AsyncMock, return_value=version_data):
                deps = await client.get_dependencies(
                    "Newtonsoft.Json", "13.0.3", target_framework="net6.0"
                )
        assert "net6.0" in deps
        assert ".NETStandard2.0" not in deps

    # ─── _process_catalog_entry ────────────────────────────────────────────────

    def test_process_catalog_entry_empty_returns_none(self, client):
        assert client._process_catalog_entry({}) is None

    def test_process_catalog_entry_invalid_version_returns_none(self, client):
        result = client._process_catalog_entry({"version": "invalid"})
        assert result is None

    # ─── _extract_version_info ─────────────────────────────────────────────────

    def test_extract_version_info_skips_invalid_version(self, client):
        versions = [
            {"version": "1.0.0", "downloads": 100},
            {"version": "not-a-version", "downloads": 50},
        ]
        result = client._extract_version_info(versions)
        versions_out = [v["version"] for v in result]
        assert "not-a-version" not in versions_out
        assert "1.0.0" in versions_out

    # ─── _extract_repository_info ──────────────────────────────────────────────

    def test_extract_repository_info_returns_repo(self, client):
        entry = {
            "repository": {
                "type": "git",
                "url": "https://github.com/test/repo",
                "branch": "main",
                "commit": "abc123",
            }
        }
        result = client._extract_repository_info(entry)
        assert result == {
            "type": "git",
            "url": "https://github.com/test/repo",
            "branch": "main",
            "commit": "abc123",
        }

    def test_extract_repository_info_returns_none_when_no_repo(self, client):
        assert client._extract_repository_info({}) is None

    # ─── _is_newer_version ─────────────────────────────────────────────────────

    def test_is_newer_version_returns_false_when_unparseable(self, client):
        assert client._is_newer_version("invalid", "1.0.0") is False
        assert client._is_newer_version("1.0.0", "invalid") is False
        assert client._is_newer_version("invalid", "invalid") is False

    # ─── _parse_nuget_version_requirement ──────────────────────────────────────

    def test_parse_nuget_version_requirement_exact(self, client):
        req = client._parse_nuget_version_requirement("[1.2.3]")
        assert req.operator == "="
        assert req.major == 1
        assert req.minor == 2
        assert req.patch == 3

    def test_parse_nuget_version_requirement_minimum(self, client):
        req = client._parse_nuget_version_requirement("[1.2.3,)")
        assert req.operator == ">="
        assert req.major == 1
        assert req.minor == 2
        assert req.patch == 3

    def test_parse_nuget_version_requirement_floating_minor(self, client):
        req = client._parse_nuget_version_requirement("1.2.*")
        assert req.operator == "~"
        assert req.major == 1
        assert req.minor == 2
        assert req.is_floating is True

    def test_parse_nuget_version_requirement_floating_major(self, client):
        req = client._parse_nuget_version_requirement("1.*")
        assert req.operator == "~"
        assert req.major == 1
        assert req.is_floating is True

    def test_parse_nuget_version_requirement_unmatched_spec(self, client):
        req = client._parse_nuget_version_requirement("something-weird")
        assert req.raw == "something-weird"
        assert req.operator is None

    def test_parse_nuget_version_requirement_caches_result(self, client):
        req1 = client._parse_nuget_version_requirement("[1.0.0]")
        req2 = client._parse_nuget_version_requirement("[1.0.0]")
        assert req1 is req2

    # ─── check_compatibility ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_check_compatibility_package_not_found(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value=None):
            result = await client.check_compatibility("Unknown", "1.0", {})
        assert result["compatible"] is False
        assert "Package version not found" in result["errors"]

    @pytest.mark.asyncio
    async def test_check_compatibility_framework_mismatch(self, client):
        pkg_data = {
            "system_requirements": {
                "target_frameworks": ["net8.0"],
            },
            "dependencies": {},
        }
        with patch.object(
            client, "get_package_version", new_callable=AsyncMock, return_value=pkg_data
        ):
            result = await client.check_compatibility(
                "Some.Package", "1.0", {"target_frameworks": ["native"]}
            )
        assert result["compatible"] is False
        assert any("target frameworks" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_check_compatibility_nuget_version_too_low(self, client):
        pkg_data = {
            "system_requirements": {
                "target_frameworks": [],
                "min_client_version": "6.0.0",
            },
            "dependencies": {},
        }
        with patch.object(
            client, "get_package_version", new_callable=AsyncMock, return_value=pkg_data
        ):
            result = await client.check_compatibility(
                "Some.Package", "1.0", {"nuget_version": "5.0.0", "target_frameworks": []}
            )
        assert result["compatible"] is False
        assert any("NuGet client version" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_check_compatibility_dev_dependency_warning(self, client):
        pkg_data = {
            "system_requirements": {
                "target_frameworks": [],
                "development_dependency": True,
                "min_client_version": None,
            },
            "dependencies": {},
        }
        with patch.object(
            client, "get_package_version", new_callable=AsyncMock, return_value=pkg_data
        ):
            result = await client.check_compatibility(
                "Some.Package", "1.0", {"target_frameworks": []}
            )
        assert result["compatible"] is True
        assert any("development dependency" in w for w in result["warnings"])

    # ─── _check_framework_compatibility ────────────────────────────────────────

    def test_check_framework_compatibility_returns_matching(self, client):
        result = client._check_framework_compatibility(["net6.0", "net8.0"], ["net6.0", "native"])
        assert "net6.0" in result
        assert "net8.0" not in result

    def test_check_framework_compatibility_netstandard_with_netfx(self, client):
        result = client._check_framework_compatibility(["netstandard2.0"], ["net472"])
        assert "netstandard2.0" in result

    def test_check_framework_compatibility_netstandard_with_netcore(self, client):
        result = client._check_framework_compatibility(["netstandard2.0"], ["net6.0"])
        assert "netstandard2.0" in result

    def test_check_framework_compatibility_empty_on_no_match(self, client):
        result = client._check_framework_compatibility(["net8.0"], ["native"])
        assert result == []

    # ─── _is_framework_compatible ──────────────────────────────────────────────

    def test_is_framework_compatible_identical(self, client):
        assert client._is_framework_compatible("net6.0", "net6.0") is True

    def test_is_framework_compatible_netstandard_with_netfx46(self, client):
        assert client._is_framework_compatible("netstandard2.0", "net472") is True

    def test_is_framework_compatible_netstandard_with_net5plus(self, client):
        assert client._is_framework_compatible("netstandard2.0", "net6.0") is True

    def test_is_framework_compatible_net_versions_forward(self, client):
        assert client._is_framework_compatible("net6.0", "net8.0") is True

    def test_is_framework_compatible_net_versions_backward(self, client):
        assert client._is_framework_compatible("net8.0", "net6.0") is False

    def test_is_framework_compatible_unrelated(self, client):
        assert client._is_framework_compatible("win8", "net6.0") is False

    def test_is_framework_compatible_netstandard_with_low_netfx(self, client):
        assert client._is_framework_compatible("netstandard2.0", "win8") is False

    # ─── _extract_framework_version ────────────────────────────────────────────

    def test_extract_framework_version_with_dot(self, client):
        assert client._extract_framework_version("net6.0") == 6.0

    def test_extract_framework_version_without_dot(self, client):
        assert client._extract_framework_version("net472") == 472.0

    def test_extract_framework_version_no_match(self, client):
        assert client._extract_framework_version("native") is None

    # ─── _check_nuget_version_compatibility ────────────────────────────────────

    def test_check_nuget_version_compatible_true(self, client):
        assert client._check_nuget_version_compatibility("6.0.0", "5.0.0") is True

    def test_check_nuget_version_compatible_false(self, client):
        assert client._check_nuget_version_compatibility("5.0.0", "6.0.0") is False

    def test_check_nuget_version_compatible_fallback_on_parse_failure(self, client):
        assert client._check_nuget_version_compatibility("invalid", "6.0.0") is True
