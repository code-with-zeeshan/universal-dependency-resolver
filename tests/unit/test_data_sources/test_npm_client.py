from unittest.mock import AsyncMock, patch

import pytest

from backend.data_sources.npm_client import DependencyType, NPMClient


class TestNPMClient:
    @pytest.fixture
    def client(self):
        return NPMClient()

    @pytest.fixture
    def sample_search_response(self):
        return {
            "objects": [
                {
                    "package": {
                        "name": "express",
                        "version": "4.18.2",
                        "description": "Fast, unopinionated, minimalist web framework",
                        "keywords": ["express", "framework", "web"],
                        "date": "2023-12-01T00:00:00.000Z",
                        "publisher": {
                            "username": "expressjs",
                            "email": "express@example.com",
                        },
                        "maintainers": [{"username": "dougwilson"}],
                        "links": {
                            "npm": "https://www.npmjs.com/package/express",
                            "homepage": "http://expressjs.com/",
                            "repository": "https://github.com/expressjs/express",
                            "bugs": "https://github.com/expressjs/express/issues",
                        },
                        "license": "MIT",
                        "scope": "unscoped",
                    },
                    "score": {
                        "final": 0.99,
                        "detail": {
                            "quality": 0.98,
                            "popularity": 0.99,
                            "maintenance": 0.97,
                        },
                    },
                    "searchScore": 95.0,
                }
            ],
            "total": 1,
        }

    @pytest.fixture
    def sample_package_response(self):
        return {
            "name": "express",
            "description": "Fast, unopinionated, minimalist web framework",
            "dist-tags": {"latest": "4.18.2"},
            "versions": {
                "4.18.2": {
                    "name": "express",
                    "version": "4.18.2",
                    "description": "Fast, unopinionated, minimalist web framework",
                    "dependencies": {"accepts": "~1.3.8", "debug": "2.6.9"},
                    "engines": {"node": ">= 0.10.0"},
                    "license": "MIT",
                    "dist": {
                        "integrity": "sha512-some",
                        "shasum": "some",
                        "tarball": "https://registry.npmjs.org/express/-/express-4.18.2.tgz",
                        "unpackedSize": 250000,
                        "fileCount": 20,
                    },
                    "scripts": {"test": "mocha --exit"},
                },
                "4.18.1": {
                    "name": "express",
                    "version": "4.18.1",
                    "description": "Express 4.18.1",
                    "dependencies": {"accepts": "~1.3.8"},
                    "engines": {"node": ">= 0.10.0"},
                    "license": "MIT",
                },
            },
            "time": {
                "created": "2010-01-02T00:00:00.000Z",
                "modified": "2023-12-01T00:00:00.000Z",
                "4.18.2": "2023-12-01T00:00:00.000Z",
                "4.18.1": "2023-10-15T00:00:00.000Z",
            },
            "homepage": "http://expressjs.com/",
            "keywords": ["express", "framework", "web"],
            "license": "MIT",
            "author": {"name": "TJ Holowaychuk", "email": "tj@example.com"},
            "maintainers": [{"name": "dougwilson", "email": "doug@example.com"}],
            "repository": {
                "type": "git",
                "url": "https://github.com/expressjs/express",
            },
            "bugs": {"url": "https://github.com/expressjs/express/issues"},
            "readme": "# Express\nFast, unopinionated, minimalist web framework.",
            "users": {"user1": True},
        }

    @pytest.mark.asyncio
    async def test_search_packages_basic(self, client, sample_search_response):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=sample_search_response,
        ):
            results = await client.search_packages("express")
        assert len(results) == 1
        assert results[0]["name"] == "express"
        assert results[0]["version"] == "4.18.2"
        assert (
            results[0]["description"] == "Fast, unopinionated, minimalist web framework"
        )
        assert results[0]["license"] == "MIT"
        assert "score" in results[0]

    @pytest.mark.asyncio
    async def test_search_packages_correct_url(self, client, sample_search_response):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=sample_search_response,
        ) as mock_request:
            await client.search_packages("express", limit=10)
        mock_request.assert_called_once()
        url = mock_request.call_args[0][1]
        assert "search" in url.lower()

    @pytest.mark.asyncio
    async def test_search_packages_passes_params(self, client, sample_search_response):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=sample_search_response,
        ) as mock_request:
            await client.search_packages("react", limit=5)
        url, params = mock_request.call_args[0][0], mock_request.call_args[1].get(
            "params", {}
        )
        assert params.get("text") == "react"
        assert params.get("size") == 5

    @pytest.mark.asyncio
    async def test_search_packages_with_quality_filter(
        self, client, sample_search_response
    ):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=sample_search_response,
        ):
            results = await client.search_packages("express", quality=0.5)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_packages_quality_filter_excludes(
        self, client, sample_search_response
    ):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=sample_search_response,
        ):
            results = await client.search_packages("express", quality=0.99)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_packages_popularity_filter(
        self, client, sample_search_response
    ):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=sample_search_response,
        ):
            results = await client.search_packages("express", popularity=0.5)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_packages_maintenance_filter(
        self, client, sample_search_response
    ):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=sample_search_response,
        ):
            results = await client.search_packages("express", maintenance=0.5)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_packages_returns_empty_on_no_data(self, client):
        with patch.object(
            client, "_make_request", new_callable=AsyncMock, return_value=None
        ):
            results = await client.search_packages("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_handles_empty_objects(self, client):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value={"objects": []},
        ):
            results = await client.search_packages("nothing")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_extracts_score(self, client, sample_search_response):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=sample_search_response,
        ):
            results = await client.search_packages("express")
        assert results[0]["score"]["final"] == 0.99
        assert results[0]["score"]["quality"] == 0.98
        assert results[0]["score"]["popularity"] == 0.99

    @pytest.mark.asyncio
    async def test_get_package_info_success(self, client, sample_package_response):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=sample_package_response,
        ), patch.object(
            client,
            "_check_typescript_support",
            new_callable=AsyncMock,
            return_value=None,
        ), patch.object(
            client, "_get_download_stats", new_callable=AsyncMock, return_value={}
        ), patch.object(
            client, "_check_vulnerabilities", new_callable=AsyncMock, return_value=[]
        ):
            result = await client.get_package_info("express")
        assert result is not None
        assert result["name"] == "express"
        assert result["version"] == "4.18.2"
        assert result["description"] == "Fast, unopinionated, minimalist web framework"
        assert "versions" in result
        assert "dist_tags" in result
        assert "latest_version_info" in result

    @pytest.mark.asyncio
    async def test_get_package_info_handles_404(self, client):
        with patch.object(
            client, "_make_request", new_callable=AsyncMock, return_value=None
        ):
            result = await client.get_package_info("nonexistent-package")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_scoped_package(self, client):
        scoped_response = {
            "name": "@scope/test-package",
            "version": "1.0.0",
            "description": "A scoped test package",
            "dist-tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "name": "@scope/test-package",
                    "version": "1.0.0",
                    "dependencies": {},
                    "license": "MIT",
                }
            },
            "time": {
                "created": "2023-01-01T00:00:00.000Z",
                "modified": "2023-01-01T00:00:00.000Z",
                "1.0.0": "2023-01-01T00:00:00.000Z",
            },
            "license": "MIT",
        }
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=scoped_response,
        ) as mock_request, patch.object(
            client,
            "_check_typescript_support",
            new_callable=AsyncMock,
            return_value=None,
        ), patch.object(
            client, "_get_download_stats", new_callable=AsyncMock, return_value={}
        ), patch.object(
            client, "_check_vulnerabilities", new_callable=AsyncMock, return_value=[]
        ):
            result = await client.get_package_info("@scope/test-package")
        assert result is not None
        assert result["name"] == "@scope/test-package"
        mock_request.assert_called_once()
        url = mock_request.call_args[0][1]
        assert "@scope/test-package" in url

    @pytest.mark.asyncio
    async def test_get_package_info_no_latest_tag(
        self, client, sample_package_response
    ):
        no_tag = dict(sample_package_response)
        no_tag["dist-tags"] = {}
        with patch.object(
            client, "_make_request", new_callable=AsyncMock, return_value=no_tag
        ):
            result = await client.get_package_info("express")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_includes_versions(
        self, client, sample_package_response
    ):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value=sample_package_response,
        ), patch.object(
            client,
            "_check_typescript_support",
            new_callable=AsyncMock,
            return_value=None,
        ), patch.object(
            client, "_get_download_stats", new_callable=AsyncMock, return_value={}
        ), patch.object(
            client, "_check_vulnerabilities", new_callable=AsyncMock, return_value=[]
        ):
            result = await client.get_package_info("express", include_versions=True)
        assert len(result["versions"]) == 2

    @pytest.mark.asyncio
    async def test_get_package_version_success(self, client):
        version_data = {
            "name": "express",
            "version": "4.18.2",
            "description": "Fast, unopinionated, minimalist web framework",
            "dependencies": {"accepts": "~1.3.8"},
            "engines": {"node": ">= 0.10.0"},
            "license": "MIT",
            "dist": {"unpackedSize": 250000},
            "os": ["darwin", "linux"],
            "cpu": ["x64"],
        }
        with patch.object(
            client, "_make_request", new_callable=AsyncMock, return_value=version_data
        ):
            result = await client.get_package_version("express", "4.18.2")
        assert result is not None
        assert result["version"] == "4.18.2"
        assert "dependencies" in result
        assert "system_requirements" in result

    @pytest.mark.asyncio
    async def test_get_package_version_not_found(self, client):
        with patch.object(
            client, "_make_request", new_callable=AsyncMock, return_value=None
        ):
            result = await client.get_package_version("express", "99.99.99")
        assert result is None

    @pytest.fixture
    def sample_versions_list(self):
        return [
            {
                "version": "5.0.0-beta.1",
                "deprecated": None,
                "published": "2023-11-01T00:00:00.000Z",
                "node": ">= 0.10.0",
                "npm": None,
                "dist": {},
                "hasNativeDeps": False,
            },
            {
                "version": "4.18.2",
                "deprecated": None,
                "published": "2023-12-01T00:00:00.000Z",
                "node": ">= 0.10.0",
                "npm": None,
                "dist": {},
                "hasNativeDeps": False,
            },
            {
                "version": "4.18.1",
                "deprecated": "This version is deprecated",
                "published": "2023-10-15T00:00:00.000Z",
                "node": ">= 0.10.0",
                "npm": None,
                "dist": {},
                "hasNativeDeps": False,
            },
        ]

    @pytest.fixture
    def sample_package_info_response(
        self, sample_package_response, sample_versions_list
    ):
        response = {k: v for k, v in sample_package_response.items() if k != "versions"}
        response["versions"] = sample_versions_list
        response["latest_version_info"] = {
            "dependencies": {"dependencies": {"accepts": "~1.3.8"}},
            "engines": {"node": ">= 0.10.0"},
        }
        response["downloads"] = {}
        response["typescript"] = None
        response["vulnerabilities"] = []
        return response

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client, sample_package_info_response):
        with patch.object(
            client,
            "get_package_info",
            new_callable=AsyncMock,
            return_value=sample_package_info_response,
        ):
            versions = await client.get_versions("express")
        assert len(versions) == 2
        assert all("version" in v for v in versions)
        assert all("published" in v for v in versions)
        assert all("dist" in v for v in versions)

    @pytest.mark.asyncio
    async def test_get_versions_empty_when_no_package(self, client):
        with patch.object(
            client, "get_package_info", new_callable=AsyncMock, return_value=None
        ):
            versions = await client.get_versions("nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_versions_filters_prereleases(
        self, client, sample_package_info_response
    ):
        with patch.object(
            client,
            "get_package_info",
            new_callable=AsyncMock,
            return_value=sample_package_info_response,
        ):
            versions = await client.get_versions("express", include_prereleases=False)
        assert all("beta" not in v["version"] for v in versions)

    @pytest.mark.asyncio
    async def test_get_versions_includes_prereleases(
        self, client, sample_package_info_response
    ):
        with patch.object(
            client,
            "get_package_info",
            new_callable=AsyncMock,
            return_value=sample_package_info_response,
        ):
            versions = await client.get_versions("express", include_prereleases=True)
        version_strings = [v["version"] for v in versions]
        assert "5.0.0-beta.1" in version_strings

    @pytest.mark.asyncio
    async def test_make_request_tries_mirrors(self, client):
        client.mirror_urls = ["https://mirror.example.com"]
        client.registry_url = "https://registry.npmjs.org"

        with patch.object(
            client.__class__.__mro__[1], "_make_request", new_callable=AsyncMock
        ) as mock_base:
            mock_base.side_effect = [None, {"result": "from_mirror"}]
            result = await client._make_request(
                "GET", "https://registry.npmjs.org/package/test"
            )
        assert result == {"result": "from_mirror"}
        assert mock_base.call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_returns_first_success(self, client):
        with patch.object(
            client.__class__.__mro__[1], "_make_request", new_callable=AsyncMock
        ) as mock_base:
            mock_base.side_effect = [{"result": "primary"}]
            result = await client._make_request(
                "GET", "https://registry.npmjs.org/package/test"
            )
        assert result == {"result": "primary"}
        assert mock_base.call_count == 1

    @pytest.mark.asyncio
    async def test_make_request_all_fail(self, client):
        client.mirror_urls = [
            "https://mirror1.example.com",
            "https://mirror2.example.com",
        ]
        with patch.object(
            client.__class__.__mro__[1], "_make_request", new_callable=AsyncMock, return_value=None
        ):
            result = await client._make_request(
                "GET", "https://registry.npmjs.org/package/test"
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_search_packages_empty_query(self, client):
        with patch.object(
            client,
            "_make_request",
            new_callable=AsyncMock,
            return_value={"objects": []},
        ):
            results = await client.search_packages("")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client, sample_package_info_response):
        with patch.object(
            client,
            "get_package_info",
            new_callable=AsyncMock,
            return_value=sample_package_info_response,
        ):
            result = await client.get_dependencies("express")
        assert "direct" in result
        assert "transitive" in result

    def test_format_person_string(self, client):
        result = client._format_person("TJ Holowaychuk <tj@example.com>")
        assert result["name"] == "TJ Holowaychuk"
        assert result["email"] == "tj@example.com"

    def test_format_person_dict(self, client):
        result = client._format_person({"name": "TJ", "email": "tj@example.com"})
        assert result["name"] == "TJ"
        assert result["email"] == "tj@example.com"

    def test_format_person_empty(self, client):
        result = client._format_person("")
        assert result["name"] == ""

    # === New test: resolve_version finds best matching version
    @pytest.mark.asyncio
    async def test_resolve_version_finds_best_match(self, client):
        with patch.object(
            client, "get_versions", new_callable=AsyncMock, return_value=[
                {"version": "4.17.0", "deprecated": None},
                {"version": "4.18.0", "deprecated": None},
                {"version": "4.18.2", "deprecated": None},
            ],
        ), patch.object(
            client, "_version_matches_requirement", side_effect=lambda v, r: v in ("4.18.0", "4.18.2")
        ):
            result = await client.resolve_version("lodash", "^4.18.0")
        assert result == "4.18.2"

    # === New test: resolve_version returns None when no versions exist
    @pytest.mark.asyncio
    async def test_resolve_version_no_versions(self, client):
        with patch.object(
            client, "get_versions", new_callable=AsyncMock, return_value=[]
        ):
            result = await client.resolve_version("unknown", "^1.0.0")
        assert result is None

    # === New test: resolve_version returns None when no version matches
    @pytest.mark.asyncio
    async def test_resolve_version_no_matching_versions(self, client):
        with patch.object(
            client, "get_versions", new_callable=AsyncMock, return_value=[
                {"version": "1.0.0", "deprecated": None},
                {"version": "1.0.1", "deprecated": None},
            ],
        ), patch.object(
            client, "_version_matches_requirement", return_value=False
        ):
            result = await client.resolve_version("pkg", "^2.0.0")
        assert result is None

    # === New test: _resolve_transitive_dependencies recurses into nested deps
    @pytest.mark.asyncio
    async def test_resolve_transitive_dependencies_basic(self, client):
        deps = {"sub-pkg": "^1.0.0"}
        visited: set = set()
        with patch.object(
            client, "resolve_version", new_callable=AsyncMock, return_value="1.0.0",
        ), patch.object(
            client, "get_package_version", new_callable=AsyncMock, return_value={
                "dependencies": {
                    "dependencies": {"nested-dep": "^2.0.0"},
                },
                "engines": {},
            },
        ):
            result = await client._resolve_transitive_dependencies(deps, visited, 3)
        assert "sub-pkg" in result
        assert result["sub-pkg"]["version"] == "1.0.0"
        assert "nested-dep" in result

    # === New test: _resolve_transitive_dependencies stops at max_depth
    @pytest.mark.asyncio
    async def test_resolve_transitive_dependencies_max_depth(self, client):
        result = await client._resolve_transitive_dependencies({"a": "^1.0.0"}, set(), 0)
        assert result == {}

    # === New test: check_compatibility with node engine mismatch
    @pytest.mark.asyncio
    async def test_check_compatibility_node_mismatch(self, client):
        with patch.object(
            client, "get_package_version", new_callable=AsyncMock, return_value={
                "engines": {"node": ">=18.0.0"},
                "dependencies": {},
            },
        ), patch.object(
            client, "_check_node_compatibility", return_value=False,
        ):
            result = await client.check_compatibility("pkg", "1.0.0", {"node_version": "16.0.0"})
        assert not result["compatible"]
        assert any("Node" in e for e in result["errors"])

    # === New test: check_compatibility with npm warning and native deps warning
    @pytest.mark.asyncio
    async def test_check_compatibility_npm_and_native_warnings(self, client):
        with patch.object(
            client, "get_package_version", new_callable=AsyncMock, return_value={
                "engines": {"npm": ">=8.0.0"},
                "dependencies": {},
                "gypfile": True,
            },
        ), patch.object(
            client, "_check_npm_compatibility", return_value=False,
        ):
            result = await client.check_compatibility("pkg", "1.0.0", {"npm_version": "6.0.0"})
        assert result["compatible"]
        assert any("npm" in w for w in result["warnings"])
        assert any("native" in w for w in result["warnings"])

    # === New test: check_compatibility fully compatible (no errors or warnings)
    @pytest.mark.asyncio
    async def test_check_compatibility_fully_compatible(self, client):
        with patch.object(
            client, "get_package_version", new_callable=AsyncMock, return_value={
                "engines": {"node": ">=14.0.0", "npm": ">=6.0.0"},
                "dependencies": {},
            },
        ), patch.object(
            client, "_check_node_compatibility", return_value=True,
        ), patch.object(
            client, "_check_npm_compatibility", return_value=True,
        ):
            result = await client.check_compatibility("pkg", "1.0.0", {
                "node_version": "20.0.0", "npm_version": "10.0.0",
            })
        assert result["compatible"]

    # === New test: check_compatibility package not found
    @pytest.mark.asyncio
    async def test_check_compatibility_package_not_found(self, client):
        with patch.object(
            client, "get_package_version", new_callable=AsyncMock, return_value=None,
        ):
            result = await client.check_compatibility("missing", "1.0.0", {})
        assert not result["compatible"]
        assert any("not found" in e for e in result["errors"])

    # === New test: _check_node_compatibility and _check_npm_compatibility semver checks
    def test_check_node_npm_compatibility(self, client):
        assert client._check_node_compatibility("16.0.0", "16.0.0") is True
        assert client._check_node_compatibility("16.0.1", "16.0.0") is False
        assert client._check_node_compatibility("18.0.0", ">=16.0.0") is True
        assert client._check_node_compatibility("14.0.0", ">=16.0.0") is False
        assert client._check_npm_compatibility("8.0.0", ">=6.0.0") is True
        assert client._check_npm_compatibility("5.0.0", ">=6.0.0") is False
        assert client._check_npm_compatibility("8.0.0", "^8.0.0") is True
        assert client._check_npm_compatibility("9.0.0", "^8.0.0") is False

    # === New test: get_dependencies with type filtering
    @pytest.mark.asyncio
    async def test_get_dependencies_with_type_filtering(self, client):
        modified = {
            "latest_version_info": {
                "dependencies": {
                    "dependencies": {"accepts": "~1.3.8"},
                    "devDependencies": {"mocha": "^10.0.0"},
                    "peerDependencies": {"react": "^18.0.0"},
                },
            },
            "downloads": {},
            "typescript": None,
            "vulnerabilities": [],
        }
        with patch.object(
            client, "get_package_info", new_callable=AsyncMock, return_value=modified,
        ):
            result = await client.get_dependencies(
                "express",
                types=[DependencyType.DEV_DEPENDENCIES, DependencyType.PEER_DEPENDENCIES],
            )
        assert "devDependencies" in result["direct"]
        assert "peerDependencies" in result["direct"]
        assert "dependencies" not in result["direct"]
        assert result["direct"]["devDependencies"]["mocha"] == "^10.0.0"

    # === New test: get_dependencies with transitive resolution
    @pytest.mark.asyncio
    async def test_get_dependencies_with_transitive_resolution(self, client):
        modified = {
            "latest_version_info": {
                "dependencies": {
                    "dependencies": {"accepts": "~1.3.8"},
                },
            },
            "downloads": {},
            "typescript": None,
            "vulnerabilities": [],
        }
        with patch.object(
            client, "get_package_info", new_callable=AsyncMock, return_value=modified,
        ), patch.object(
            client, "_resolve_transitive_dependencies", new_callable=AsyncMock, return_value={
                "accepts": {"version": "1.3.8", "dependencies": {}},
            },
        ):
            result = await client.get_dependencies("express", include_transitive=True)
        assert "accepts" in result["transitive"]
        assert result["transitive"]["accepts"]["version"] == "1.3.8"

    # === New test: get_package_version with os/cpu and system_requirements
    @pytest.mark.asyncio
    async def test_get_package_version_with_os_cpu_system_requirements(self, client):
        version_data = {
            "name": "native-pkg",
            "version": "1.0.0",
            "description": "Has native deps",
            "os": ["linux"],
            "cpu": ["x64", "arm64"],
            "engines": {"node": ">=14.0.0"},
            "dependencies": {"node-gyp": "^9.0.0"},
        }
        with patch.object(
            client, "_make_request", new_callable=AsyncMock, return_value=version_data,
        ):
            result = await client.get_package_version("native-pkg", "1.0.0")
        assert result is not None
        assert result["os"] == ["linux"]
        assert result["cpu"] == ["x64", "arm64"]
        assert result["system_requirements"]["build_tools_required"] is True
        assert result["system_requirements"]["python_required"] is True

    # === New test: _build_dependency_tree resolves deps recursively
    @pytest.mark.asyncio
    async def test_build_dependency_tree_basic(self, client):
        visited: set = set()
        with patch.object(
            client, "get_package_version", new_callable=AsyncMock, return_value={
                "dependencies": {
                    "dependencies": {"dep1": "^1.0.0", "dep2": "^2.0.0"},
                },
            },
        ), patch.object(
            client, "resolve_version", new_callable=AsyncMock,
            side_effect=lambda n, s: "1.0.0" if "dep1" in n else "2.0.0",
        ):
            result = await client._build_dependency_tree("root", "1.0.0", visited, 3)
        assert "dep1" in result
        assert "dep2" in result
        assert result["dep1"]["version"] == "1.0.0"
        assert result["dep1"]["resolved"] is True
        assert result["dep2"]["version"] == "2.0.0"

    # === New test: _build_dependency_tree detects circular deps
    @pytest.mark.asyncio
    async def test_build_dependency_tree_circular(self, client):
        visited = {"root@1.0.0"}
        result = await client._build_dependency_tree("root", "1.0.0", visited, 3)
        assert result == {"circular": True}

    # === New test: _format_person None and partial dict
    def test_format_person_edge_cases(self, client):
        result = client._format_person(None)
        assert result == {}
        result = client._format_person({"name": "Alice"})
        assert result["name"] == "Alice"
        assert result["email"] is None
        result = client._format_person({"email": "alice@example.com"})
        assert result["name"] == ""
        assert result["email"] == "alice@example.com"

    # === search_packages: popularity filter excludes (line 105)
    @pytest.mark.asyncio
    async def test_search_packages_popularity_filter_excludes(self, client, sample_search_response):
        with patch.object(client, "_make_request", new_callable=AsyncMock, return_value=sample_search_response):
            results = await client.search_packages("express", popularity=0.995)
        assert len(results) == 0

    # === search_packages: maintenance filter excludes (line 107)
    @pytest.mark.asyncio
    async def test_search_packages_maintenance_filter_excludes(self, client, sample_search_response):
        with patch.object(client, "_make_request", new_callable=AsyncMock, return_value=sample_search_response):
            results = await client.search_packages("express", maintenance=0.98)
        assert len(results) == 0

    # === get_dependencies with version param (line 307)
    @pytest.mark.asyncio
    async def test_get_dependencies_with_version(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={
            "dependencies": {
                "dependencies": {"accepts": "~1.3.8"},
            },
        }):
            result = await client.get_dependencies("express", version="4.18.2")
        assert "direct" in result
        assert "dependencies" in result["direct"]

    # === get_dependencies returns empty when get_package_info returns None (line 313)
    @pytest.mark.asyncio
    async def test_get_dependencies_no_info(self, client):
        with patch.object(client, "get_package_info", new_callable=AsyncMock, return_value=None):
            result = await client.get_dependencies("nonexistent")
        assert result == {}

    # === get_dependencies returns empty when pkg_data is None (line 317)
    @pytest.mark.asyncio
    async def test_get_dependencies_pkg_data_none(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value=None):
            result = await client.get_dependencies("pkg", version="1.0.0")
        assert result == {}

    # === get_dependencies with version and types filter
    @pytest.mark.asyncio
    async def test_get_dependencies_with_version_and_types(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={
            "dependencies": {
                "dependencies": {"accepts": "~1.3.8"},
                "devDependencies": {"mocha": "^10.0.0"},
            },
        }):
            result = await client.get_dependencies("express", version="4.18.2",
                types=[DependencyType.DEV_DEPENDENCIES])
        assert "devDependencies" in result["direct"]
        assert "dependencies" not in result["direct"]

    # === _resolve_transitive_dependencies: resolve_version returns None (line 358)
    @pytest.mark.asyncio
    async def test_resolve_transitive_deps_skip_when_no_resolved_version(self, client):
        with patch.object(client, "resolve_version", new_callable=AsyncMock, return_value=None):
            result = await client._resolve_transitive_dependencies({"sub": "^1.0.0"}, set(), 3)
        assert result == {}

    # === _resolve_transitive_dependencies: dep_info is None (line 364)
    @pytest.mark.asyncio
    async def test_resolve_transitive_deps_skip_when_no_dep_info(self, client):
        with patch.object(client, "resolve_version", new_callable=AsyncMock, return_value="1.0.0"), \
             patch.object(client, "get_package_version", new_callable=AsyncMock, return_value=None):
            result = await client._resolve_transitive_dependencies({"sub": "^1.0.0"}, set(), 3)
        assert result == {}

    # === check_compatibility: OS mismatch (lines 415-416)
    @pytest.mark.asyncio
    async def test_check_compatibility_os_mismatch(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={
            "engines": {},
            "dependencies": {},
            "os": ["linux"],
        }):
            result = await client.check_compatibility("pkg", "1.0.0", {"os": "win32"})
        assert not result["compatible"]
        assert any("OS" in e for e in result["errors"])

    # === check_compatibility: CPU mismatch (lines 420-421)
    @pytest.mark.asyncio
    async def test_check_compatibility_cpu_mismatch(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={
            "engines": {},
            "dependencies": {},
            "cpu": ["x64"],
        }):
            result = await client.check_compatibility("pkg", "1.0.0", {"cpu": "arm64"})
        assert not result["compatible"]
        assert any("CPU" in e for e in result["errors"])

    # === check_compatibility: peer dep missing (lines 433-437)
    @pytest.mark.asyncio
    async def test_check_compatibility_peer_dep_missing(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={
            "engines": {},
            "dependencies": {
                "peerDependencies": {"react": "^18.0.0"},
            },
        }):
            result = await client.check_compatibility("pkg", "1.0.0", {"installed_packages": {}})
        assert result["compatible"]
        assert any("missing" in w.lower() for w in result["warnings"])

    # === check_compatibility: peer dep version mismatch (lines 438-441)
    @pytest.mark.asyncio
    async def test_check_compatibility_peer_dep_version_mismatch(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={
            "engines": {},
            "dependencies": {
                "peerDependencies": {"react": "^18.0.0"},
            },
        }):
            result = await client.check_compatibility("pkg", "1.0.0", {"installed_packages": {"react": "17.0.0"}})
        assert result["compatible"]
        assert any("mismatch" in w.lower() for w in result["warnings"])

    # === get_dependency_tree basic (lines 455-476)
    @pytest.mark.asyncio
    async def test_get_dependency_tree_basic(self, client):
        with patch.object(client, "get_package_info", new_callable=AsyncMock, return_value={
            "version": "1.0.0",
            "latest_version_info": {"dependencies": {}},
        }), \
             patch.object(client, "_build_dependency_tree", new_callable=AsyncMock, return_value={}):
            result = await client.get_dependency_tree("express")
        assert result["name"] == "express"
        assert result["version"] == "1.0.0"

    # === get_dependency_tree with version param
    @pytest.mark.asyncio
    async def test_get_dependency_tree_with_version(self, client):
        with patch.object(client, "_build_dependency_tree", new_callable=AsyncMock, return_value={}):
            result = await client.get_dependency_tree("express", version="4.18.2")
        assert result["name"] == "express"
        assert result["version"] == "4.18.2"

    # === get_dependency_tree when info is None (line 467)
    @pytest.mark.asyncio
    async def test_get_dependency_tree_no_info(self, client):
        with patch.object(client, "get_package_info", new_callable=AsyncMock, return_value=None):
            result = await client.get_dependency_tree("nonexistent")
        assert result["name"] == "nonexistent"
        assert result["version"] == "latest"

    # === _build_dependency_tree: pkg_data is None (line 498)
    @pytest.mark.asyncio
    async def test_build_dep_tree_no_pkg_data(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value=None):
            result = await client._build_dependency_tree("root", "1.0.0", set(), 3)
        assert result == {}

    # === _build_dependency_tree: resolve_version fails (lines 509-510)
    @pytest.mark.asyncio
    async def test_build_dep_tree_unresolved_dep(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={
            "dependencies": {"dependencies": {"missing": "^99.0.0"}},
        }), \
             patch.object(client, "resolve_version", new_callable=AsyncMock, return_value=None):
            result = await client._build_dependency_tree("root", "1.0.0", set(), 3)
        assert "missing" in result
        assert result["missing"]["resolved"] is False

    # === get_versions with include_deprecated
    @pytest.mark.asyncio
    async def test_get_versions_include_deprecated(self, client, sample_package_info_response):
        with patch.object(client, "get_package_info", new_callable=AsyncMock, return_value=sample_package_info_response):
            versions = await client.get_versions("express", include_deprecated=True)
        version_strings = [v["version"] for v in versions]
        assert "4.18.1" in version_strings

    # === analyze_package success (lines 529-596)
    @pytest.mark.asyncio
    async def test_analyze_package_basic(self, client):
        info = {
            "name": "webpack", "version": "5.0.0", "description": "A bundler",
            "license": "MIT", "author": {"name": "Tobias"},
            "homepage": "https://webpack.js.org",
            "repository": {"url": "https://github.com/webpack"},
            "readme": "# Webpack",
            "time": {"modified": "2026-06-01T00:00:00.000Z"},
            "versions": [{"version": "5.0.0"}],
            "maintainers": [{"name": "tobias"}],
            "keywords": ["web", "pack"],
            "downloads": {"weekly": 5000000},
            "typescript": {"has_types": True},
            "vulnerabilities": [],
        }
        pkg_data = {
            "dependencies": {
                "dependencies": {"tapable": "^2.0.0"},
                "devDependencies": {"mocha": "^10.0.0"},
                "peerDependencies": {},
                "optionalDependencies": {},
            },
            "engines": {"node": ">=14.0.0"},
            "dist": {"unpackedSize": 1000000, "fileCount": 50},
            "scripts": {"test": "jest"},
        }
        with patch.object(client, "get_package_info", new_callable=AsyncMock, return_value=info), \
             patch.object(client, "get_package_version", new_callable=AsyncMock, return_value=pkg_data), \
             patch.object(client, "_has_deprecated_dependencies", new_callable=AsyncMock, return_value=False):
            result = await client.analyze_package("webpack")
        assert result["name"] == "webpack"
        assert result["quality_score"] > 0

    # === analyze_package: no info (line 532)
    @pytest.mark.asyncio
    async def test_analyze_package_no_info(self, client):
        with patch.object(client, "get_package_info", new_callable=AsyncMock, return_value=None):
            result = await client.analyze_package("nonexistent")
        assert result == {}

    # === analyze_package: no pkg_data (line 539)
    @pytest.mark.asyncio
    async def test_analyze_package_no_pkg_data(self, client):
        with patch.object(client, "get_package_info", new_callable=AsyncMock, return_value={"name": "pkg", "version": "1.0.0", "versions": []}), \
             patch.object(client, "get_package_version", new_callable=AsyncMock, return_value=None):
            result = await client.analyze_package("pkg")
        assert result == {}

    # === _get_download_stats success (lines 599-616)
    @pytest.mark.asyncio
    async def test_get_download_stats_success(self, client):
        def side_effect(method, url, **kwargs):
            if "last-day" in url:
                return {"downloads": 100}
            if "last-week" in url:
                return {"downloads": 700}
            if "last-month" in url:
                return {"downloads": 3000}
            if "last-year" in url:
                return {"downloads": 36000}
            return None
        with patch.object(client, "_make_request", new_callable=AsyncMock, side_effect=side_effect):
            stats = await client._get_download_stats("express")
        assert stats["daily"] == 100
        assert stats["weekly"] == 700
        assert stats["monthly"] == 3000
        assert stats["yearly"] == 36000

    # === _get_download_stats: some endpoints return None
    @pytest.mark.asyncio
    async def test_get_download_stats_partial_data(self, client):
        calls = 0
        def side_effect(method, url, **kwargs):
            nonlocal calls
            calls += 1
            return None if calls == 1 else {"downloads": 50}
        with patch.object(client, "_make_request", new_callable=AsyncMock, side_effect=side_effect):
            stats = await client._get_download_stats("express")
        assert stats["daily"] == 0

    # === _get_download_stats exception (lines 618-619)
    @pytest.mark.asyncio
    async def test_get_download_stats_exception(self, client):
        with patch.object(client, "_make_request", new_callable=AsyncMock, side_effect=Exception("API error")):
            stats = await client._get_download_stats("express")
        assert stats == {"daily": 0, "weekly": 0, "monthly": 0, "yearly": 0}

    # === _check_typescript_support: inline types (lines 626-629)
    @pytest.mark.asyncio
    async def test_check_typescript_support_inline_types(self, client):
        result = await client._check_typescript_support("pkg", {"types": "index.d.ts"})
        assert result["has_types"] is True
        assert result["included"] is True

    # === _check_typescript_support: typings field
    @pytest.mark.asyncio
    async def test_check_typescript_support_typings_field(self, client):
        result = await client._check_typescript_support("pkg", {"typings": "index.d.ts"})
        assert result["has_types"] is True

    # === _check_typescript_support: @types package exists (lines 631-639)
    @pytest.mark.asyncio
    async def test_check_typescript_support_at_types_package(self, client):
        with patch.object(client, "_package_exists", new_callable=AsyncMock, return_value=True):
            result = await client._check_typescript_support("express", {})
        assert result["has_types"] is True
        assert result["types_package"] == "@types/express"

    # === _check_typescript_support: no types (line 641)
    @pytest.mark.asyncio
    async def test_check_typescript_support_no_types(self, client):
        with patch.object(client, "_package_exists", new_callable=AsyncMock, return_value=False):
            result = await client._check_typescript_support("no-types-pkg", {})
        assert result["has_types"] is False
        assert result["types_package"] is None

    # === _package_exists returns True (lines 644-648)
    @pytest.mark.asyncio
    async def test_package_exists_true(self, client):
        with patch.object(client, "get_package_info", new_callable=AsyncMock, return_value={"name": "express"}):
            assert await client._package_exists("express") is True

    # === _package_exists returns False
    @pytest.mark.asyncio
    async def test_package_exists_false(self, client):
        with patch.object(client, "get_package_info", new_callable=AsyncMock, return_value=None):
            assert await client._package_exists("nonexistent") is False

    # === _check_vulnerabilities (lines 653-654)
    @pytest.mark.asyncio
    async def test_check_vulnerabilities(self, client):
        result = await client._check_vulnerabilities("express", "1.0.0")
        assert result == []

    # === _has_deprecated_dependencies: True (lines 657-666)
    @pytest.mark.asyncio
    async def test_has_deprecated_dependencies_true(self, client):
        pkg_data = {"dependencies": {"dependencies": {"old-pkg": "^1.0.0"}}}
        with patch.object(client, "resolve_version", new_callable=AsyncMock, return_value="1.0.0"), \
             patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={"deprecated": "This is deprecated"}):
            result = await client._has_deprecated_dependencies(pkg_data)
        assert result is True

    # === _has_deprecated_dependencies: False
    @pytest.mark.asyncio
    async def test_has_deprecated_dependencies_false(self, client):
        pkg_data = {"dependencies": {"dependencies": {"good-pkg": "^1.0.0"}}}
        with patch.object(client, "resolve_version", new_callable=AsyncMock, return_value="1.0.0"), \
             patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={"deprecated": None}):
            result = await client._has_deprecated_dependencies(pkg_data)
        assert result is False

    # === _has_deprecated_dependencies: resolve_version returns None
    @pytest.mark.asyncio
    async def test_has_deprecated_dependencies_skip_unresolved(self, client):
        pkg_data = {"dependencies": {"dependencies": {"unresolved": "^99.0.0"}}}
        with patch.object(client, "resolve_version", new_callable=AsyncMock, return_value=None):
            result = await client._has_deprecated_dependencies(pkg_data)
        assert result is False

    # === _has_deprecated_dependencies: dep_info is None
    @pytest.mark.asyncio
    async def test_has_deprecated_dependencies_skip_no_dep_info(self, client):
        pkg_data = {"dependencies": {"dependencies": {"pkg": "^1.0.0"}}}
        with patch.object(client, "resolve_version", new_callable=AsyncMock, return_value="1.0.0"), \
             patch.object(client, "get_package_version", new_callable=AsyncMock, return_value=None):
            result = await client._has_deprecated_dependencies(pkg_data)
        assert result is False

    # === _calculate_quality_score: max score (lines 671-715)
    def test_calculate_quality_score_max(self, client):
        info = {
            "readme": "# README",
            "homepage": "https://example.com",
            "repository": {"url": "https://github.com"},
            "license": "MIT",
            "keywords": ["key"],
            "time": {"modified": "2026-06-01T00:00:00.000Z"},
            "downloads": {"weekly": 2000000},
            "typescript": {"has_types": True},
            "vulnerabilities": [],
        }
        pkg_data = {"scripts": {"test": "jest"}}
        score = client._calculate_quality_score(info, pkg_data)
        assert score == 0.95

    # === _calculate_quality_score: medium score (no optional fields)
    def test_calculate_quality_score_medium(self, client):
        info = {
            "readme": "# README",
            "homepage": "",
            "repository": None,
            "license": "",
            "keywords": [],
            "time": {"modified": "2020-01-01T00:00:00.000Z"},
            "downloads": {"weekly": 500},
            "typescript": {"has_types": False},
            "vulnerabilities": [{"id": "CVE-123"}],
        }
        pkg_data = {"scripts": {}}
        score = client._calculate_quality_score(info, pkg_data)
        assert score < 1.0

    # === _calculate_quality_score: low weekly downloads
    def test_calculate_quality_score_low_downloads(self, client):
        info = {
            "readme": "# README",
            "time": {"modified": "2020-01-01T00:00:00.000Z"},
            "downloads": {"weekly": 50},
        }
        pkg_data = {}
        score = client._calculate_quality_score(info, pkg_data)
        assert 0 < score < 0.5

    # === _process_versions: skips invalid version (lines 723-724)
    def test_process_versions_skips_invalid(self, client):
        versions_data = {
            "invalid": {"deprecated": None},
            "1.0.0": {"deprecated": None, "dist": {}},
        }
        result = client._process_versions(versions_data, {})
        assert len(result) == 1
        assert result[0]["version"] == "1.0.0"

    # === _process_versions: engines not a dict (line 728)
    def test_process_versions_engines_not_dict(self, client):
        versions_data = {
            "1.0.0": {"deprecated": None, "engines": "node >= 14", "dist": {}},
        }
        result = client._process_versions(versions_data, {})
        assert len(result) == 1
        assert result[0]["node"] is None

    # === _extract_detailed_requirements: npm (line 783)
    def test_extract_detailed_requirements_with_npm(self, client):
        data = {"engines": {"node": ">=14.0.0", "npm": ">=6.0.0"}}
        result = client._extract_detailed_requirements(data)
        assert result["npm"]["spec"] == ">=6.0.0"

    # === _extract_detailed_requirements: scripts trigger build_tools (line 814)
    def test_extract_detailed_requirements_scripts_build(self, client):
        data = {
            "scripts": {"install": "node-gyp rebuild"},
            "dependencies": {},
        }
        result = client._extract_detailed_requirements(data)
        assert result["build_tools_required"] is True

    # === _extract_detailed_requirements: deps trigger native (lines 802-808)
    def test_extract_detailed_requirements_native_deps(self, client):
        data = {
            "dependencies": {"nan": "^2.0.0"},
            "scripts": {},
        }
        result = client._extract_detailed_requirements(data)
        assert result["build_tools_required"] is True
        assert result["python_required"] is True
        assert "nan" in result["native_modules"]

    # === _version_matches_requirement: * operator (line 878)
    def test_version_matches_requirement_star(self, client):
        req = client._parse_version_requirement("*")
        assert client._version_matches_requirement("1.0.0", req) is True

    # === _version_matches_requirement: ^ with major > 0 (line 889)
    def test_version_matches_requirement_caret_major(self, client):
        req = client._parse_version_requirement("^4.0.0")
        assert client._version_matches_requirement("4.2.0", req) is True
        assert client._version_matches_requirement("5.0.0", req) is False

    # === _version_matches_requirement: ^ with major=0, minor>0 (lines 890-891)
    def test_version_matches_requirement_caret_zero_minor(self, client):
        req = client._parse_version_requirement("^0.2.0")
        assert client._version_matches_requirement("0.2.1", req) is True
        assert client._version_matches_requirement("0.3.0", req) is False

    # === _version_matches_requirement: ^ with major=0, minor=0 (lines 892-893)
    def test_version_matches_requirement_caret_zero_zero(self, client):
        req = client._parse_version_requirement("^0.0.1")
        assert client._version_matches_requirement("0.0.1", req) is True
        assert client._version_matches_requirement("0.0.2", req) is False

    # === _version_matches_requirement: ~ operator (lines 895-910)
    def test_version_matches_requirement_tilde(self, client):
        req = client._parse_version_requirement("~1.2.0")
        assert client._version_matches_requirement("1.2.5", req) is True
        assert client._version_matches_requirement("1.3.0", req) is False

    # === _version_matches_requirement: >= operator (lines 912-919)
    def test_version_matches_requirement_gte(self, client):
        req = client._parse_version_requirement(">=4.0.0")
        assert client._version_matches_requirement("5.0.0", req) is True
        assert client._version_matches_requirement("3.0.0", req) is False

    # === _version_matches_requirement: <= operator (lines 922-928)
    def test_version_matches_requirement_lte(self, client):
        req = client._parse_version_requirement("<=3.0.0")
        assert client._version_matches_requirement("2.0.0", req) is True
        assert client._version_matches_requirement("4.0.0", req) is False

    # === _version_matches_requirement: exact match (lines 930-937)
    def test_version_matches_requirement_exact(self, client):
        req = client._parse_version_requirement("1.0.0")
        assert client._version_matches_requirement("1.0.0", req) is True
        assert client._version_matches_requirement("1.0.1", req) is False

    # === _version_matches_requirement: invalid version string (line 875)
    def test_version_matches_requirement_invalid_version(self, client):
        req = client._parse_version_requirement("^1.0.0")
        assert client._version_matches_requirement("not-a-version", req) is False

    # === _version_matches_requirement: exception caught (lines 939-940)
    def test_version_matches_requirement_exception(self, client):
        req = client._parse_version_requirement("^1.0.0")
        with patch("backend.data_sources.npm_client.parse_version", side_effect=ValueError("oops")):
            assert client._version_matches_requirement("1.0.0", req) is False

    # === _check_os_compatibility: blocked (line 960)
    def test_check_os_compatibility_blocked(self, client):
        assert client._check_os_compatibility("win32", ["!win32", "linux"]) is False

    # === _check_os_compatibility: allowed list not matched (lines 962-963)
    def test_check_os_compatibility_allowed_not_matched(self, client):
        assert client._check_os_compatibility("win32", ["linux", "darwin"]) is False

    # === _check_os_compatibility: any (lines 953-954)
    def test_check_os_compatibility_any(self, client):
        assert client._check_os_compatibility("win32", ["any"]) is True

    # === _check_os_compatibility: empty list (line 953)
    def test_check_os_compatibility_empty(self, client):
        assert client._check_os_compatibility("linux", []) is True

    # === _check_cpu_compatibility: blocked (line 975)
    def test_check_cpu_compatibility_blocked(self, client):
        assert client._check_cpu_compatibility("x64", ["!x64", "arm64"]) is False

    # === _check_cpu_compatibility: allowed list not matched (lines 977-978)
    def test_check_cpu_compatibility_allowed_not_matched(self, client):
        assert client._check_cpu_compatibility("s390x", ["x64", "arm64"]) is False

    # === _check_cpu_compatibility: any (lines 968-969)
    def test_check_cpu_compatibility_any(self, client):
        assert client._check_cpu_compatibility("x64", ["any"]) is True

    # === _check_cpu_compatibility: empty list (line 968)
    def test_check_cpu_compatibility_empty(self, client):
        assert client._check_cpu_compatibility("x64", []) is True

    # === _extract_min_version (line 986)
    def test_extract_min_version(self, client):
        assert client._extract_min_version(">=14.0.0") == "14.0.0"
        assert client._extract_min_version("^1.2") == "1.2"
        assert client._extract_min_version("*") is None

    # === _extract_publisher: string (line 1034)
    def test_extract_publisher_string(self, client):
        result = client._extract_publisher("someuser")
        assert result["username"] == "someuser"

    # === _extract_publisher: empty string
    def test_extract_publisher_empty_string(self, client):
        result = client._extract_publisher("")
        assert result["username"] == ""

    # === _extract_repository: from GitHub links (lines 1041-1046)
    def test_extract_repository_from_github_links(self, client):
        links = {"homepage": "https://github.com/expressjs/express", "repository": None}
        result = client._extract_repository(links)
        assert result == "https://github.com/expressjs/express"

    # === _extract_repository: from gitlab links
    def test_extract_repository_from_gitlab_links(self, client):
        links = {"bugs": "https://gitlab.com/user/repo/issues", "repository": None}
        result = client._extract_repository(links)
        assert result == "https://gitlab.com/user/repo"

    # === _extract_repository: from bitbucket links
    def test_extract_repository_from_bitbucket_links(self, client):
        links = {"homepage": "https://bitbucket.org/user/repo", "repository": None}
        result = client._extract_repository(links)
        assert result == "https://bitbucket.org/user/repo"

    # === _extract_repository: no match found (lines 1047-1048)
    def test_extract_repository_no_match(self, client):
        links = {"homepage": "https://example.com/pkg", "repository": None}
        result = client._extract_repository(links)
        assert result is None

    # === _extract_repository_info: string (line 1054)
    def test_extract_repository_info_string(self, client):
        result = client._extract_repository_info("https://github.com/user/repo")
        assert result["type"] == "git"
        assert result["url"] == "https://github.com/user/repo"

    # === _calculate_quality_score: days between 365-730 (line 700)
    def test_calculate_quality_score_days_365_730(self, client):
        info = {
            "readme": "# README",
            "time": {"modified": "2025-01-01T00:00:00.000Z"},
            "downloads": {"weekly": 50},
        }
        score = client._calculate_quality_score(info, {})
        assert 0 < score

    # === _calculate_quality_score: weekly > 10000 (line 706)
    def test_calculate_quality_score_weekly_gt_10000(self, client):
        info = {
            "readme": "# README",
            "time": {"modified": "2020-01-01T00:00:00.000Z"},
            "downloads": {"weekly": 50000},
        }
        score = client._calculate_quality_score(info, {})
        assert 0 < score

    # === _calculate_quality_score: weekly > 1000 (line 708)
    def test_calculate_quality_score_weekly_gt_1000(self, client):
        info = {
            "readme": "# README",
            "time": {"modified": "2020-01-01T00:00:00.000Z"},
            "downloads": {"weekly": 5000},
        }
        score = client._calculate_quality_score(info, {})
        assert 0 < score

    # === _calculate_quality_score: weekly > 100 (line 710)
    def test_calculate_quality_score_weekly_gt_100(self, client):
        info = {
            "readme": "# README",
            "time": {"modified": "2020-01-01T00:00:00.000Z"},
            "downloads": {"weekly": 500},
        }
        score = client._calculate_quality_score(info, {})
        assert 0 < score

    # === _version_matches_requirement: ^ with req_v parse fail (line 886)
    def test_version_matches_requirement_caret_parse_fail(self, client):
        from packaging import version as pv
        call_count = [0]
        def mock_parse(v):
            call_count[0] += 1
            if call_count[0] == 2:
                return None
            return pv.parse(v)
        with patch("backend.data_sources.npm_client.parse_version", side_effect=mock_parse):
            req = client._parse_version_requirement("^1.0.0")
            result = client._version_matches_requirement("1.0.0", req)
        assert result is False

    # === _version_matches_requirement: ~ with req_v parse fail (line 908)
    def test_version_matches_requirement_tilde_parse_fail(self, client):
        from packaging import version as pv
        call_count = [0]
        def mock_parse(v):
            call_count[0] += 1
            if call_count[0] == 2:
                return None
            return pv.parse(v)
        with patch("backend.data_sources.npm_client.parse_version", side_effect=mock_parse):
            req = client._parse_version_requirement("~1.0.0")
            result = client._version_matches_requirement("1.0.0", req)
        assert result is False

    # === _version_matches_requirement: >= with req_v parse fail (line 918)
    def test_version_matches_requirement_gte_parse_fail(self, client):
        from packaging import version as pv
        call_count = [0]
        def mock_parse(v):
            call_count[0] += 1
            if call_count[0] == 2:
                return None
            return pv.parse(v)
        with patch("backend.data_sources.npm_client.parse_version", side_effect=mock_parse):
            req = client._parse_version_requirement(">=1.0.0")
            result = client._version_matches_requirement("2.0.0", req)
        assert result is False

    # === _version_matches_requirement: <= with req_v parse fail (line 927)
    def test_version_matches_requirement_lte_parse_fail(self, client):
        from packaging import version as pv
        call_count = [0]
        def mock_parse(v):
            call_count[0] += 1
            if call_count[0] == 2:
                return None
            return pv.parse(v)
        with patch("backend.data_sources.npm_client.parse_version", side_effect=mock_parse):
            req = client._parse_version_requirement("<=2.0.0")
            result = client._version_matches_requirement("1.0.0", req)
        assert result is False

    # === _version_matches_requirement: exact with req_v parse fail (line 936)
    def test_version_matches_requirement_exact_parse_fail(self, client):
        from packaging import version as pv
        call_count = [0]
        def mock_parse(v):
            call_count[0] += 1
            if call_count[0] == 2:
                return None
            return pv.parse(v)
        with patch("backend.data_sources.npm_client.parse_version", side_effect=mock_parse):
            req = client._parse_version_requirement("1.0.0")
            result = client._version_matches_requirement("1.0.0", req)
        assert result is False

    # === _check_os_compatibility: os in allowed list (line 965)
    def test_check_os_compatibility_in_allowed(self, client):
        assert client._check_os_compatibility("linux", ["linux", "!win32"]) is True

    # === _check_cpu_compatibility: cpu in allowed list (line 980)
    def test_check_cpu_compatibility_in_allowed(self, client):
        assert client._check_cpu_compatibility("x64", ["x64", "!arm64"]) is True
