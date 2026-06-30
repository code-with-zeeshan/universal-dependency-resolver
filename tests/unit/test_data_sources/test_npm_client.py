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
