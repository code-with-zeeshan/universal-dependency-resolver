from datetime import datetime, timedelta
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

    @pytest.mark.asyncio
    async def test_get_effective_pom(self, client):
        mock_pom_data = {
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
        }
        with patch.object(
            client,
            "_fetch_and_parse_pom_hierarchy",
            new_callable=AsyncMock,
            return_value=mock_pom_data,
        ):
            result = await client.get_effective_pom("com.google.guava", "guava", "32.1.3-jre")
        assert "dependencies" in result
        assert result["dependencies"][0]["artifact_id"] == "failureaccess"

    @pytest.mark.asyncio
    async def test_get_effective_pom_ensures_central_repo(self, client):
        with patch.object(
            client,
            "_fetch_and_parse_pom_hierarchy",
            new_callable=AsyncMock,
        ) as mock_fetch:
            await client.get_effective_pom("com.google.guava", "guava", "32.1.3-jre", repositories=[])
        args, _ = mock_fetch.call_args
        repos = args[3]
        assert any(repo["id"] == "central" for repo in repos)

    @pytest.mark.asyncio
    async def test_resolve_version_from_range_fixed(self, client):
        result = await client.resolve_version_from_range(
            "g", "a", {"type": "fixed", "version": "1.0.0"}
        )
        assert result == "1.0.0"

    @pytest.mark.asyncio
    async def test_resolve_version_from_range_returns_highest(self, client):
        range_info = {
            "type": "range",
            "min_version": "1.0.0",
            "max_version": "3.0.0",
            "min_inclusive": True,
            "max_inclusive": True,
        }
        with patch.object(
            client,
            "get_package_versions",
            new_callable=AsyncMock,
            return_value=[{"version": v} for v in ("1.0.0", "2.0.0", "3.0.0")],
        ):
            with patch.object(client, "_version_matches_range", side_effect=lambda v, r: True):
                result = await client.resolve_version_from_range("g", "a", range_info)
        assert result == "3.0.0"

    @pytest.mark.asyncio
    async def test_resolve_version_from_range_no_match(self, client):
        range_info = {
            "type": "range",
            "min_version": "4.0.0",
            "max_version": "5.0.0",
            "min_inclusive": True,
            "max_inclusive": True,
        }
        with patch.object(
            client,
            "get_package_versions",
            new_callable=AsyncMock,
            return_value=[{"version": "1.0.0"}, {"version": "2.0.0"}],
        ):
            with patch.object(client, "_version_matches_range", return_value=False):
                result = await client.resolve_version_from_range("g", "a", range_info)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_transitive_dependencies(self, client):
        mock_pom = {
            "dependencies": [
                {
                    "group_id": "com.google.guava",
                    "artifact_id": "failureaccess",
                    "version": "unspecified",
                    "scope": "compile",
                }
            ]
        }
        with patch.object(
            client,
            "get_effective_pom",
            new_callable=AsyncMock,
            return_value=mock_pom,
        ):
            result = await client.get_transitive_dependencies(
                "com.google.guava", "guava", "32.1.3-jre"
            )
        assert len(result) == 1
        assert result[0]["artifact_id"] == "failureaccess"

    @pytest.mark.asyncio
    async def test_get_transitive_dependencies_skips_visited(self, client):
        result = await client.get_transitive_dependencies(
            "com.google.guava",
            "guava",
            "32.1.3-jre",
            visited={"com.google.guava:guava:32.1.3-jre"},
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_get_transitive_dependencies_respects_exclusions(self, client):
        result = await client.get_transitive_dependencies(
            "com.google.guava",
            "guava",
            "32.1.3-jre",
            exclusions=[{"group_id": "com.google.guava", "artifact_id": "guava"}],
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_get_dependency_tree(self, client):
        mock_deps = [
            {
                "group_id": "com.google.guava",
                "artifact_id": "failureaccess",
                "version": "1.0.1",
                "scope": "compile",
                "optional": False,
            }
        ]
        with patch.object(
            client,
            "get_dependencies",
            new_callable=AsyncMock,
            return_value=mock_deps,
        ):
            result = await client.get_dependency_tree(
                "com.google.guava",
                "guava",
                "32.1.3-jre",
                max_depth=2,
                visited={"com.google.guava:failureaccess:1.0.1"},
            )
        assert result["name"] == "com.google.guava:guava"
        assert len(result["dependencies"]) == 1
        assert result["dependencies"][0]["dependencies"] == []

    @pytest.mark.asyncio
    async def test_get_dependency_tree_max_depth_zero(self, client):
        result = await client.get_dependency_tree(
            "com.google.guava", "guava", "32.1.3-jre", max_depth=0
        )
        assert result["dependencies"] == []

    @pytest.mark.asyncio
    async def test_get_dependency_tree_skips_excluded_scopes(self, client):
        mock_deps = [
            {
                "group_id": "g",
                "artifact_id": "test-lib",
                "version": "1.0",
                "scope": "test",
                "optional": False,
            },
            {
                "group_id": "g",
                "artifact_id": "provided-lib",
                "version": "1.0",
                "scope": "provided",
                "optional": False,
            },
            {
                "group_id": "g",
                "artifact_id": "optional-lib",
                "version": "1.0",
                "scope": "compile",
                "optional": True,
            },
        ]
        with patch.object(
            client,
            "get_dependencies",
            new_callable=AsyncMock,
            return_value=mock_deps,
        ):
            result = await client.get_dependency_tree(
                "com.google.guava", "guava", "32.1.3-jre"
            )
        assert result["dependencies"] == []

    def test_is_maven_version(self, client):
        assert client._is_maven_version("1.0.0") is True
        assert client._is_maven_version("32.1.3-jre") is True
        assert client._is_maven_version("1.0.0-SNAPSHOT") is True
        assert client._is_maven_version("1") is True
        assert client._is_maven_version("invalid") is False
        assert client._is_maven_version("") is False
        assert client._is_maven_version("a.b.c") is False

    def test_sort_maven_version_standard(self, client):
        from packaging.version import Version

        parsed = client._sort_maven_version("1.0.0")
        assert parsed[0] == Version("1.0.0")
        assert parsed[1] == 0

    def test_sort_maven_version_snapshot(self, client):
        from packaging.version import Version

        parsed = client._sort_maven_version("1.0.0-SNAPSHOT")
        assert isinstance(parsed[0], Version)
        assert parsed[1] in (0, 1)

    def test_sort_maven_version_unparseable(self, client):
        from packaging.version import Version

        parsed = client._sort_maven_version("abc")
        assert parsed[1] == 2
        assert parsed[2] == "abc"

    def test_compare_java_versions(self, client):
        assert client._compare_java_versions("11", "8") > 0
        assert client._compare_java_versions("1.8", "11") < 0
        assert client._compare_java_versions("11", "11") == 0
        assert client._compare_java_versions("11.0.1", "11") == 0
        assert client._compare_java_versions("1.8.0_202", "1.8.0_191") == 0

    def test_parse_version_range_syntax_exact(self, client):
        result = client._parse_version_range_syntax("[1.0.0]")
        assert result["min_version"] == "1.0.0"
        assert result["max_version"] == "1.0.0"
        assert result["min_inclusive"] is True
        assert result["max_inclusive"] is True

    def test_parse_version_range_syntax_lower_bound_only(self, client):
        result = client._parse_version_range_syntax("[1.0.0,)")
        assert result["min_version"] == "1.0.0"
        assert result["max_version"] is None
        assert result["min_inclusive"] is True

    def test_parse_version_range_syntax_upper_bound_only(self, client):
        result = client._parse_version_range_syntax("(,2.0.0]")
        assert result["min_version"] is None
        assert result["max_version"] == "2.0.0"
        assert result["max_inclusive"] is True

    def test_parse_version_range_syntax_open_range(self, client):
        result = client._parse_version_range_syntax("(1.0.0,2.0.0)")
        assert result["min_version"] == "1.0.0"
        assert result["max_version"] == "2.0.0"
        assert result["min_inclusive"] is False
        assert result["max_inclusive"] is False

    def test_parse_version_range_syntax_closed_range(self, client):
        result = client._parse_version_range_syntax("[1.0.0,2.0.0]")
        assert result["min_version"] == "1.0.0"
        assert result["max_version"] == "2.0.0"
        assert result["min_inclusive"] is True
        assert result["max_inclusive"] is True

    def test_version_matches_range_inside(self, client):
        range_info = {"min_version": "1.0.0", "max_version": "3.0.0", "min_inclusive": True, "max_inclusive": True}
        assert client._version_matches_range("2.0.0", range_info) is True

    def test_version_matches_range_below(self, client):
        range_info = {"min_version": "1.0.0", "max_version": "3.0.0", "min_inclusive": True, "max_inclusive": True}
        assert client._version_matches_range("0.9.0", range_info) is False

    def test_version_matches_range_above(self, client):
        range_info = {"min_version": "1.0.0", "max_version": "3.0.0", "min_inclusive": True, "max_inclusive": True}
        assert client._version_matches_range("4.0.0", range_info) is False

    def test_version_matches_range_exclusive_bounds(self, client):
        range_info = {"min_version": "1.0.0", "max_version": "3.0.0", "min_inclusive": False, "max_inclusive": False}
        assert client._version_matches_range("1.0.0", range_info) is False
        assert client._version_matches_range("3.0.0", range_info) is False
        assert client._version_matches_range("2.0.0", range_info) is True

    def test_merge_poms_child_overrides_properties(self, client):
        parent = {
            "properties": {"java.version": "8"},
            "dependency_management": {},
            "dependencies": [],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        child = {
            "properties": {"java.version": "11"},
            "dependency_management": {},
            "dependencies": [],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        merged = client._merge_poms(parent, child)
        assert merged["properties"]["java.version"] == "11"

    def test_merge_poms_child_dep_overrides_parent(self, client):
        parent = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [
                {"group_id": "g", "artifact_id": "a", "version": "1.0", "scope": "compile"}
            ],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        child = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [
                {"group_id": "g", "artifact_id": "a", "version": "2.0", "scope": "runtime"}
            ],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        merged = client._merge_poms(parent, child)
        assert len(merged["dependencies"]) == 1
        assert merged["dependencies"][0]["version"] == "2.0"

    def test_merge_poms_combines_repositories(self, client):
        parent = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [],
            "repositories": [{"id": "central", "url": "https://repo1.maven.org"}],
            "plugin_repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        child = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [],
            "repositories": [{"id": "custom", "url": "https://custom.repo"}],
            "plugin_repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        merged = client._merge_poms(parent, child)
        assert len(merged["repositories"]) == 2

    def test_extract_properties(self, client):
        import xml.etree.ElementTree as ET

        xml = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <properties>
    <java.version>11</java.version>
    <maven.compiler.source>${java.version}</maven.compiler.source>
  </properties>
</project>'''
        root = ET.fromstring(xml)
        namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}
        result = client._extract_properties(root, namespaces)
        assert result["java.version"] == "11"
        assert result["maven.compiler.source"] == "${java.version}"

    def test_extract_properties_no_properties_section(self, client):
        import xml.etree.ElementTree as ET

        xml = '<project xmlns="http://maven.apache.org/POM/4.0.0"><packaging>jar</packaging></project>'
        root = ET.fromstring(xml)
        namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}
        result = client._extract_properties(root, namespaces)
        assert result == {}

    def test_get_element_text_with_namespace(self, client):
        import xml.etree.ElementTree as ET

        xml = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <packaging>jar</packaging>
</project>'''
        root = ET.fromstring(xml)
        namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}
        result = client._get_element_text(root, "packaging", namespaces)
        assert result == "jar"

    def test_get_element_text_without_namespace(self, client):
        import xml.etree.ElementTree as ET

        xml = "<project><packaging>war</packaging></project>"
        root = ET.fromstring(xml)
        namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}
        result = client._get_element_text(root, "packaging", namespaces)
        assert result == "war"

    def test_get_element_text_not_found(self, client):
        import xml.etree.ElementTree as ET

        xml = "<project><packaging>jar</packaging></project>"
        root = ET.fromstring(xml)
        namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}
        result = client._get_element_text(root, "nonexistent", namespaces)
        assert result is None

    def test_get_element_text_empty_element(self, client):
        import xml.etree.ElementTree as ET

        xml = "<project><packaging></packaging></project>"
        root = ET.fromstring(xml)
        namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}
        result = client._get_element_text(root, "packaging", namespaces)
        assert result is None

    def test_should_include_transitive_dependency(self, client):
        assert client._should_include_transitive_dependency("compile", "compile") is True
        assert client._should_include_transitive_dependency("compile", "runtime") is True
        assert client._should_include_transitive_dependency("compile", "test") is False
        assert client._should_include_transitive_dependency("compile", "provided") is False
        assert client._should_include_transitive_dependency("runtime", "compile") is False
        assert client._should_include_transitive_dependency("runtime", "runtime") is True
        assert client._should_include_transitive_dependency("test", "compile") is True
        assert client._should_include_transitive_dependency("test", "runtime") is True
        assert client._should_include_transitive_dependency("test", "test") is True
        assert client._should_include_transitive_dependency("provided", "compile") is False
        assert client._should_include_transitive_dependency("system", "compile") is False

    def test_should_cache(self, client):
        with patch("backend.data_sources.maven_client.ENABLE_CACHE", True):
            client._pom_cache = {}
            assert client._should_cache("https://repo1.maven.org/maven2/...") is True
            assert client._should_cache("https://search.maven.org/...") is False

    def test_should_cache_disabled(self, client):
        with patch("backend.data_sources.maven_client.ENABLE_CACHE", False):
            client._pom_cache = None
            assert client._should_cache("https://repo1.maven.org/maven2/...") is False

    def test_should_cache_no_cache_store(self, client):
        with patch("backend.data_sources.maven_client.ENABLE_CACHE", True):
            client._pom_cache = None
            assert client._should_cache("https://repo1.maven.org/maven2/...") is False

    # === New test: __init__ attributes
    def test_init_attributes(self):
        client = MavenClient()
        assert client.ecosystem == "maven"
        assert "search.maven.org" in client.base_url
        assert client.artifact_url == "https://search.maven.org/artifact"
        assert "repo1.maven.org" in client.maven_repo_url
        assert client.additional_repos == []
        assert client._cache_ttl > 0
        assert client.max_retries > 0
        assert client.timeout > 0
        assert client._pom_cache is not None

    # === New test: _normalize_maven_coordinates
    def test_normalize_maven_coordinates(self, client):
        g, a = client._normalize_maven_coordinates("COM.Google.Guava", "Guava_ABC")
        assert g == "com.google.guava"
        assert a == "guava-abc"

    # === New test: get_package_versions filters stable (excludes SNAPSHOT/alpha/beta)
    @pytest.mark.asyncio
    async def test_get_package_versions_filter_stable(self, client):
        mock_docs = [
            {"v": "1.0.0", "timestamp": 1501881872000},
            {"v": "1.1.0-SNAPSHOT", "timestamp": 1501881872000},
            {"v": "1.2.0-alpha", "timestamp": 1501881872000},
            {"v": "1.3.0-beta", "timestamp": 1501881872000},
        ]
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"response": {"docs": mock_docs}})
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            versions = await client.get_package_versions(
                "g", "a", filters={"release_type": "stable"}
            )
        assert len(versions) == 1
        assert versions[0]["version"] == "1.0.0"

    # === New test: get_package_versions filters snapshot (excludes non-SNAPSHOT)
    @pytest.mark.asyncio
    async def test_get_package_versions_filter_snapshot(self, client):
        mock_docs = [
            {"v": "1.0.0", "timestamp": 1501881872000},
            {"v": "1.1.0-SNAPSHOT", "timestamp": 1501881872000},
        ]
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"response": {"docs": mock_docs}})
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            versions = await client.get_package_versions(
                "g", "a", filters={"release_type": "snapshot"}
            )
        assert len(versions) == 1
        assert "SNAPSHOT" in versions[0]["version"]

    # === New test: get_package_versions filters by version_range
    @pytest.mark.asyncio
    async def test_get_package_versions_filter_version_range(self, client):
        mock_docs = [
            {"v": "1.0.0", "timestamp": 1501881872000},
            {"v": "2.0.0", "timestamp": 1501881872000},
            {"v": "3.0.0", "timestamp": 1501881872000},
        ]
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"response": {"docs": mock_docs}})
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            versions = await client.get_package_versions(
                "g", "a", filters={"version_range": "[1.5.0,2.5.0]"}
            )
        assert len(versions) == 1
        assert versions[0]["version"] == "2.0.0"

    # === New test: get_package_versions returns empty when no docs
    @pytest.mark.asyncio
    async def test_get_package_versions_empty_response(self, client):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"response": {"docs": []}})
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            versions = await client.get_package_versions("g", "a")
        assert versions == []

    # === New test: _fetch_pom_from_repos tries repos in order, returns first success
    @pytest.mark.asyncio
    async def test_fetch_pom_from_repos_order(self, client):
        repos = [
            {"id": "first", "url": "https://first.repo"},
            {"id": "second", "url": "https://second.repo"},
        ]
        urls_called = []

        async def mock_fetch(url):
            urls_called.append(url)
            if "first" in url:
                return None
            return "<project></project>"

        with patch.object(client, "_fetch_pom_content", side_effect=mock_fetch):
            result = await client._fetch_pom_from_repos("g", "a", "1.0", repos)
        assert result == "<project></project>"
        assert len(urls_called) == 2
        assert "first" in urls_called[0]
        assert "second" in urls_called[1]

    # === New test: _fetch_pom_from_repos all repos fail returns None
    @pytest.mark.asyncio
    async def test_fetch_pom_from_repos_all_fail(self, client):
        with patch.object(
            client, "_fetch_pom_content", new_callable=AsyncMock, return_value=None
        ):
            result = await client._fetch_pom_from_repos(
                "g", "a", "1.0", [{"id": "test", "url": "https://test.repo"}]
            )
        assert result is None

    # === New test: _fetch_pom_from_repos with additional_repos
    @pytest.mark.asyncio
    async def test_fetch_pom_from_repos_with_additional(self, client):
        client.additional_repos = ["https://additional.repo"]
        repos = [{"id": "primary", "url": "https://primary.repo"}]
        urls_called = []

        async def mock_fetch(url):
            urls_called.append(url)
            if "primary" in url:
                return None
            return "<project></project>"

        with patch.object(client, "_fetch_pom_content", side_effect=mock_fetch):
            result = await client._fetch_pom_from_repos("g", "a", "1.0", repos)
        assert result == "<project></project>"
        assert any("additional" in u for u in urls_called)

    # === New test: _apply_profiles merges profile data into pom_data
    def test_apply_profiles(self, client):
        pom_data = {
            "properties": {},
            "dependencies": [],
            "dependency_management": {},
            "repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {
                "test-profile": {
                    "properties": {"java.version": "11"},
                    "dependencies": [
                        {"group_id": "g", "artifact_id": "a", "version": "1.0"}
                    ],
                    "dependency_management": {"g:a": {"version": "1.0"}},
                    "repositories": [{"id": "custom", "url": "https://custom.repo"}],
                    "plugins": [
                        {
                            "group_id": "org.apache.maven.plugins",
                            "artifact_id": "maven-compiler-plugin",
                        }
                    ],
                    "plugin_management": {
                        "org.apache.maven.plugins:maven-compiler-plugin": {
                            "version": "3.8.1"
                        }
                    },
                }
            },
        }
        result = client._apply_profiles(pom_data, ["test-profile"])
        assert result["properties"]["java.version"] == "11"
        assert len(result["dependencies"]) == 1
        assert result["dependencies"][0]["artifact_id"] == "a"
        assert result["dependency_management"]["g:a"]["version"] == "1.0"
        assert len(result["repositories"]) == 1
        assert result["repositories"][0]["id"] == "custom"
        assert len(result["plugins"]) == 1

    # === New test: _apply_profiles with non-existent profile has no effect
    def test_apply_profiles_non_existent(self, client):
        pom_data = {
            "properties": {},
            "dependencies": [],
            "dependency_management": {},
            "repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
        }
        original_props = dict(pom_data["properties"])
        result = client._apply_profiles(pom_data, ["nonexistent"])
        assert result["properties"] == original_props
        assert result["dependencies"] == []

    # === New test: _apply_default_profiles applies activeByDefault profiles
    def test_apply_default_profiles(self, client):
        pom_data = {
            "properties": {},
            "dependencies": [],
            "dependency_management": {},
            "repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {
                "default-profile": {
                    "activeByDefault": True,
                    "properties": {"java.version": "17"},
                    "dependencies": [
                        {"group_id": "g", "artifact_id": "a", "version": "1.0"}
                    ],
                    "dependency_management": {},
                    "repositories": [],
                    "plugins": [],
                    "plugin_management": {},
                }
            },
        }
        result = client._apply_default_profiles(pom_data, None)
        assert result["properties"]["java.version"] == "17"
        assert len(result["dependencies"]) == 1

    # === New test: _apply_default_profiles skipped when explicit active_profiles given
    def test_apply_default_profiles_skipped_when_active(self, client):
        pom_data = {
            "properties": {},
            "dependencies": [],
            "dependency_management": {},
            "repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {
                "default-profile": {
                    "activeByDefault": True,
                    "properties": {"java.version": "17"},
                    "dependencies": [
                        {"group_id": "g", "artifact_id": "a", "version": "1.0"}
                    ],
                    "dependency_management": {},
                    "repositories": [],
                    "plugins": [],
                    "plugin_management": {},
                }
            },
        }
        result = client._apply_default_profiles(pom_data, ["custom-profile"])
        assert "java.version" not in result["properties"]
        assert result["dependencies"] == []

    # === New test: _apply_default_profiles non-activeByDefault not applied
    def test_apply_default_profiles_non_active(self, client):
        pom_data = {
            "properties": {},
            "dependencies": [],
            "dependency_management": {},
            "repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {
                "inactive-profile": {
                    "activeByDefault": False,
                    "properties": {"java.version": "17"},
                    "dependencies": [],
                    "dependency_management": {},
                    "repositories": [],
                    "plugins": [],
                    "plugin_management": {},
                }
            },
        }
        result = client._apply_default_profiles(pom_data, None)
        assert "java.version" not in result["properties"]

    # === New test: resolve_version_from_range with open lower bound
    @pytest.mark.asyncio
    async def test_resolve_version_from_range_no_min(self, client):
        range_info = {
            "type": "range",
            "min_version": None,
            "max_version": "2.0.0",
            "min_inclusive": False,
            "max_inclusive": True,
        }
        with patch.object(
            client,
            "get_package_versions",
            new_callable=AsyncMock,
            return_value=[{"version": v} for v in ("1.0.0", "2.0.0", "3.0.0")],
        ):
            result = await client.resolve_version_from_range("g", "a", range_info)
        assert result == "2.0.0"

    # === New test: resolve_version_from_range with open upper bound
    @pytest.mark.asyncio
    async def test_resolve_version_from_range_no_max(self, client):
        range_info = {
            "type": "range",
            "min_version": "1.0.0",
            "max_version": None,
            "min_inclusive": True,
            "max_inclusive": False,
        }
        with patch.object(
            client,
            "get_package_versions",
            new_callable=AsyncMock,
            return_value=[{"version": v} for v in ("0.5.0", "1.0.0", "2.0.0")],
        ):
            result = await client.resolve_version_from_range("g", "a", range_info)
        assert result == "2.0.0"

    # === New test: resolve_version_from_range with no versions
    @pytest.mark.asyncio
    async def test_resolve_version_from_range_no_versions(self, client):
        range_info = {
            "type": "range",
            "min_version": "1.0.0",
            "max_version": "2.0.0",
            "min_inclusive": True,
            "max_inclusive": True,
        }
        with patch.object(
            client, "get_package_versions", new_callable=AsyncMock, return_value=[]
        ):
            result = await client.resolve_version_from_range("g", "a", range_info)
        assert result is None

    # === New test: _parse_version_range delegates correctly
    def test_parse_version_range(self, client):
        result = client._parse_version_range("")
        assert result == {"type": "unspecified"}

        result = client._parse_version_range(None)
        assert result == {"type": "unspecified"}

        result = client._parse_version_range("1.0.0")
        assert result == {"type": "fixed", "version": "1.0.0"}

        result = client._parse_version_range("[1.0.0,2.0.0]")
        assert result["type"] == "range"
        assert result["min_version"] == "1.0.0"
        assert result["max_version"] == "2.0.0"

        result = client._parse_version_range("(,1.0.0]")
        assert result["type"] == "range"
        assert result["min_version"] is None
        assert result["max_version"] == "1.0.0"

    # === New test: get_transitive_dependencies caches result on second call
    @pytest.mark.asyncio
    async def test_get_transitive_dependencies_caching(self, client):
        client._pom_cache = {}
        mock_pom_data = {
            "dependencies": [
                {
                    "group_id": "com.google.guava",
                    "artifact_id": "failureaccess",
                    "version": "unspecified",
                    "scope": "compile",
                }
            ],
            "properties": {},
            "dependency_management": {},
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        repos = [{"id": "central", "url": "https://repo1.maven.org/maven2"}]
        with patch.object(
            client,
            "_fetch_pom_from_repos",
            new_callable=AsyncMock,
            return_value="<project></project>",
        ) as mock_fetch:
            with patch.object(
                client, "_parse_pom_comprehensive", return_value=mock_pom_data
            ):
                result1 = await client.get_transitive_dependencies(
                    "com.google.guava", "guava", "32.1.3-jre", repositories=repos
                )
                result2 = await client.get_transitive_dependencies(
                    "com.google.guava", "guava", "32.1.3-jre", repositories=repos
                )
        assert len(result1) == 1
        assert len(result2) == 1
        assert mock_fetch.call_count == 1

    # === New test: check_compatibility with matching Java version
    @pytest.mark.asyncio
    async def test_check_compatibility_java_match(self, client):
        pom_xml = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <properties>
    <maven.compiler.source>11</maven.compiler.source>
  </properties>
</project>'''
        with patch.object(
            client, "_fetch_pom", new_callable=AsyncMock, return_value=pom_xml
        ):
            result = await client.check_compatibility(
                "g", "a", "1.0", {"java_version": "17"}
            )
        assert result["compatible"] is True
        assert "java_version" in result["details"]

    # === New test: check_compatibility with mismatched Java version
    @pytest.mark.asyncio
    async def test_check_compatibility_java_mismatch(self, client):
        pom_xml = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <properties>
    <maven.compiler.source>17</maven.compiler.source>
  </properties>
</project>'''
        with patch.object(
            client, "_fetch_pom", new_callable=AsyncMock, return_value=pom_xml
        ):
            result = await client.check_compatibility(
                "g", "a", "1.0", {"java_version": "11"}
            )
        assert result["compatible"] is False
        assert len(result["errors"]) > 0
        assert "Java" in result["errors"][0]

    # === New test: check_compatibility with no POM returns default
    @pytest.mark.asyncio
    async def test_check_compatibility_no_pom(self, client):
        with patch.object(
            client, "_fetch_pom", new_callable=AsyncMock, return_value=None
        ):
            result = await client.check_compatibility(
                "g", "a", "1.0", {"java_version": "11"}
            )
        assert result["compatible"] is True
        # When no POM, details dict stays empty (no xml to parse)
        assert result["details"] == {}

    # === New test: check_compatibility with OS-specific profile
    @pytest.mark.asyncio
    async def test_check_compatibility_os_profile(self, client):
        pom_xml = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <profiles>
    <profile>
      <id>windows-profile</id>
      <activation>
        <os>
          <name>Windows</name>
          <family>windows</family>
        </os>
      </activation>
    </profile>
  </profiles>
</project>'''
        with patch.object(
            client, "_fetch_pom", new_callable=AsyncMock, return_value=pom_xml
        ):
            result = await client.check_compatibility(
                "g", "a", "1.0", {"java_version": "11", "os_name": "Linux"}
            )
        assert result["compatible"] is True
        assert len(result["warnings"]) > 0
        assert "Windows" in result["warnings"][0]

    # === New test: check_compatibility with no java_version in system_info
    @pytest.mark.asyncio
    async def test_check_compatibility_no_java_version(self, client):
        pom_xml = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <properties>
    <maven.compiler.source>11</maven.compiler.source>
  </properties>
</project>'''
        with patch.object(
            client, "_fetch_pom", new_callable=AsyncMock, return_value=pom_xml
        ):
            result = await client.check_compatibility("g", "a", "1.0", {})
        assert result["compatible"] is True

    # === New test: check_compatibility with matching OS name (no warning)
    @pytest.mark.asyncio
    async def test_check_compatibility_os_match(self, client):
        pom_xml = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <profiles>
    <profile>
      <id>linux-profile</id>
      <activation>
        <os>
          <name>Linux</name>
        </os>
      </activation>
    </profile>
  </profiles>
</project>'''
        with patch.object(
            client, "_fetch_pom", new_callable=AsyncMock, return_value=pom_xml
        ):
            result = await client.check_compatibility(
                "g", "a", "1.0", {"java_version": "11", "os_name": "Linux"}
            )
        assert result["compatible"] is True
        warnings_about_os = [w for w in result["warnings"] if "Linux" in w]
        # OS name "linux" is contained in "Linux" so no mismatch warning
        assert len(warnings_about_os) == 0

    # === New test: check_compatibility exception returns fallback
    @pytest.mark.asyncio
    async def test_check_compatibility_exception(self, client):
        with patch.object(
            client,
            "_fetch_pom",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ):
            result = await client.check_compatibility("g", "a", "1.0", {})
        assert result["compatible"] is True
        assert any("Could not verify" in w for w in result["warnings"])

    # === New test: _clean_cache removes expired entries
    def test_clean_cache(self, client):
        old_timestamp = datetime.now() - timedelta(seconds=client._cache_ttl + 100)
        fresh_timestamp = datetime.now()
        client._pom_cache = {
            "old:key": ("old_data", old_timestamp),
            "fresh:key": ("fresh_data", fresh_timestamp),
        }
        client._clean_cache()
        assert "old:key" not in client._pom_cache
        assert "fresh:key" in client._pom_cache

    # === New test: _clean_cache when cache is None
    def test_clean_cache_none(self, client):
        client._pom_cache = None
        client._clean_cache()

    # === New test: _clean_cache when cache is empty
    def test_clean_cache_empty(self, client):
        client._pom_cache = {}
        client._clean_cache()
        assert client._pom_cache == {}

    # === New test: _substitute_properties simple replacement
    def test_substitute_properties_simple(self, client):
        result = client._substitute_properties(
            "${java.version}", {"java.version": "11"}
        )
        assert result == "11"

    # === New test: _substitute_properties no substitution needed
    def test_substitute_properties_no_substitution(self, client):
        result = client._substitute_properties(
            "plain string", {"java.version": "11"}
        )
        assert result == "plain string"

    # === New test: _substitute_properties unresolvable keeps original
    def test_substitute_properties_unresolved(self, client):
        result = client._substitute_properties(
            "${unknown.prop}", {"java.version": "11"}
        )
        assert result == "${unknown.prop}"

    # === New test: _substitute_properties recursive resolution
    def test_substitute_properties_recursive(self, client):
        result = client._substitute_properties(
            "${java.version}",
            {
                "java.version": "${real.java.version}",
                "real.java.version": "17",
            },
        )
        assert result == "17"

    # === New test: _substitute_properties with nested curly braces
    def test_substitute_properties_nested(self, client):
        result = client._substitute_properties(
            "${project.version}", {"project.version": "2.0.0"}
        )
        assert result == "2.0.0"

    # === New test: _substitute_properties with empty value
    def test_substitute_properties_empty_value(self, client):
        result = client._substitute_properties("", {"a": "b"})
        assert result == ""

        result = client._substitute_properties(None, {"a": "b"})
        assert result is None

    # === New test: _extract_parent_info from XML
    def test_extract_parent_info(self, client):
        import xml.etree.ElementTree as ET

        xml = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>2.7.0</version>
  </parent>
</project>'''
        root = ET.fromstring(xml)
        namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}
        parent_elem = root.find(".//maven:parent", namespaces)
        result = client._extract_parent_info(parent_elem, namespaces)
        assert result is not None
        assert result["group_id"] == "org.springframework.boot"
        assert result["artifact_id"] == "spring-boot-starter-parent"
        assert result["version"] == "2.7.0"
        assert result["type"] == "parent"

    # === New test: _extract_parent_info without group_id returns None
    def test_extract_parent_info_missing(self, client):
        import xml.etree.ElementTree as ET

        xml = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent>
    <artifactId>some-artifact</artifactId>
  </parent>
</project>'''
        root = ET.fromstring(xml)
        namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}
        parent_elem = root.find(".//maven:parent", namespaces)
        result = client._extract_parent_info(parent_elem, namespaces)
        assert result is None

    # === New test: _extract_parent_info without version defaults to "unspecified"
    def test_extract_parent_info_no_version(self, client):
        import xml.etree.ElementTree as ET

        xml = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
  </parent>
</project>'''
        root = ET.fromstring(xml)
        namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}
        parent_elem = root.find(".//maven:parent", namespaces)
        result = client._extract_parent_info(parent_elem, namespaces)
        assert result is not None
        assert result["version"] == "unspecified"

    # === New test: _parse_dependencies_section parses dependency elements
    def test_parse_dependencies_section(self, client):
        import xml.etree.ElementTree as ET

        xml = '''<dependencies xmlns="http://maven.apache.org/POM/4.0.0">
  <dependency>
    <groupId>com.google.guava</groupId>
    <artifactId>guava</artifactId>
    <version>32.1.3-jre</version>
    <scope>compile</scope>
  </dependency>
  <dependency>
    <groupId>junit</groupId>
    <artifactId>junit</artifactId>
    <version>4.13.2</version>
    <scope>test</scope>
  </dependency>
</dependencies>'''
        root = ET.fromstring(xml)
        namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}
        result = client._parse_dependencies_section(root, namespaces, {}, {})
        assert len(result) == 2
        assert result[0]["artifact_id"] == "guava"
        assert result[0]["version"] == "32.1.3-jre"
        assert result[0]["scope"] == "compile"
        assert result[1]["artifact_id"] == "junit"
        assert result[1]["scope"] == "test"

    # === New test: _apply_final_property_substitution resolves dep/plugin versions
    def test_apply_final_property_substitution(self, client):
        pom_data = {
            "properties": {"my.version": "1.2.3"},
            "dependencies": [
                {
                    "group_id": "com.example",
                    "artifact_id": "my-lib",
                    "version": "${my.version}",
                    "scope": "compile",
                }
            ],
            "plugins": [
                {
                    "group_id": "org.apache.maven.plugins",
                    "artifact_id": "maven-compiler-plugin",
                    "version": "${my.version}",
                }
            ],
        }
        result = client._apply_final_property_substitution(pom_data)
        assert result["dependencies"][0]["version"] == "1.2.3"
        assert result["plugins"][0]["version"] == "1.2.3"

    # === New test: should_include_transitive_dependency system scope (already tested basic, add edge)
    def test_should_include_transitive_dependency_extra(self, client):
        assert client._should_include_transitive_dependency("compile", "compile") is True
        assert client._should_include_transitive_dependency("compile", "system") is False
        assert client._should_include_transitive_dependency("provided", "provided") is False
        assert client._should_include_transitive_dependency("runtime", "provided") is False
        assert client._should_include_transitive_dependency("runtime", "test") is False

    # === New test: _version_matches_range with None min/max
    def test_version_matches_range_no_bounds(self, client):
        range_info = {
            "min_version": None,
            "max_version": None,
            "min_inclusive": False,
            "max_inclusive": False,
        }
        assert client._version_matches_range("1.0.0", range_info) is True

    # === New test: _version_matches_range with exclusive lower bound
    def test_version_matches_range_exclusive_min(self, client):
        range_info = {
            "min_version": "1.0.0",
            "max_version": "3.0.0",
            "min_inclusive": False,
            "max_inclusive": True,
        }
        assert client._version_matches_range("1.0.0", range_info) is False
        assert client._version_matches_range("1.0.1", range_info) is True

    # === New test: _version_matches_range with exclusive upper bound
    def test_version_matches_range_exclusive_max(self, client):
        range_info = {
            "min_version": "1.0.0",
            "max_version": "3.0.0",
            "min_inclusive": True,
            "max_inclusive": False,
        }
        assert client._version_matches_range("3.0.0", range_info) is False
        assert client._version_matches_range("2.9.9", range_info) is True

    # === New test: _version_matches_range with unparseable version
    def test_version_matches_range_invalid_version(self, client):
        range_info = {
            "min_version": "1.0.0",
            "max_version": "3.0.0",
            "min_inclusive": True,
            "max_inclusive": True,
        }
        assert client._version_matches_range("not-a-version", range_info) is False

    # === New test: _version_matches_range with unparseable bounds
    def test_version_matches_range_invalid_bounds(self, client):
        range_info = {
            "min_version": "not-a-version",
            "max_version": "3.0.0",
            "min_inclusive": True,
            "max_inclusive": True,
        }
        assert client._version_matches_range("1.0.0", range_info) is False

    # === New test: merge_poms parent dep with dependency management override
    def test_merge_poms_parent_dep_with_management(self, client):
        parent = {
            "properties": {},
            "dependency_management": {
                "g:a": {"version": "2.0", "scope": "runtime"}
            },
            "dependencies": [
                {
                    "group_id": "g",
                    "artifact_id": "a",
                    "version": "1.0",
                    "scope": "compile",
                }
            ],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        child = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        merged = client._merge_poms(parent, child)
        dep = merged["dependencies"][0]
        assert dep["version"] == "2.0"
        assert dep["scope"] == "runtime"

    # === New test: merge_poms child adds new dependency not in parent
    def test_merge_poms_child_new_dep(self, client):
        parent = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [
                {
                    "group_id": "g",
                    "artifact_id": "a",
                    "version": "1.0",
                    "scope": "compile",
                }
            ],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        child = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [
                {
                    "group_id": "g",
                    "artifact_id": "b",
                    "version": "2.0",
                    "scope": "runtime",
                }
            ],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        merged = client._merge_poms(parent, child)
        assert len(merged["dependencies"]) == 2

    # === New test: merge_poms plugin_repositories combine
    def test_merge_poms_plugin_repositories(self, client):
        parent = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [],
            "repositories": [],
            "plugin_repositories": [
                {"id": "central", "url": "https://repo1.maven.org"}
            ],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        child = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [],
            "repositories": [],
            "plugin_repositories": [
                {"id": "custom", "url": "https://custom.repo"}
            ],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        merged = client._merge_poms(parent, child)
        assert len(merged["plugin_repositories"]) == 2

    # === New test: merge_poms child plugin overrides parent plugin
    def test_merge_poms_plugin_override(self, client):
        parent = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [
                {
                    "group_id": "org.apache.maven.plugins",
                    "artifact_id": "maven-compiler-plugin",
                    "version": "3.8.1",
                }
            ],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        child = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [
                {
                    "group_id": "org.apache.maven.plugins",
                    "artifact_id": "maven-compiler-plugin",
                    "version": "3.9.0",
                }
            ],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        merged = client._merge_poms(parent, child)
        plugin = merged["plugins"][0]
        assert plugin["version"] == "3.9.0"

    # === New test: merge_poms child adds new plugin not in parent
    def test_merge_poms_plugin_new(self, client):
        parent = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [
                {
                    "group_id": "g",
                    "artifact_id": "p1",
                    "version": "1.0",
                }
            ],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        child = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [
                {
                    "group_id": "g",
                    "artifact_id": "p2",
                    "version": "2.0",
                }
            ],
            "plugin_management": {},
            "profiles": {},
            "modules": [],
        }
        merged = client._merge_poms(parent, child)
        assert len(merged["plugins"]) == 2

    # === New test: get_dependencies without version fetches latest
    @pytest.mark.asyncio
    async def test_get_dependencies_without_version(self, client):
        with patch.object(
            client,
            "get_package_versions",
            new_callable=AsyncMock,
            return_value=[{"version": "2.0.0"}, {"version": "1.0.0"}],
        ):
            with patch.object(
                client,
                "get_effective_pom",
                new_callable=AsyncMock,
                return_value={
                    "dependencies": [
                        {
                            "group_id": "g",
                            "artifact_id": "a",
                            "version": "1.0",
                            "scope": "compile",
                        }
                    ]
                },
            ):
                result = await client.get_dependencies("g", "a")
        assert len(result) == 1
        assert result[0]["artifact_id"] == "a"

    # === New test: get_dependencies without version and no versions
    @pytest.mark.asyncio
    async def test_get_dependencies_without_version_no_versions(self, client):
        with patch.object(
            client,
            "get_package_versions",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await client.get_dependencies("g", "a")
        assert result == []

    # === New test: _fetch_pom_content returns text for 200
    @pytest.mark.asyncio
    async def test_fetch_pom_content_success(self, client):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="<project></project>")
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._fetch_pom_content(
                "https://repo1.maven.org/maven2/g/a/1.0/a-1.0.pom"
            )
        assert result == "<project></project>"

    # === New test: _fetch_pom_content returns None for non-200
    @pytest.mark.asyncio
    async def test_fetch_pom_content_not_found(self, client):
        mock_response = MagicMock()
        mock_response.status = 404
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._fetch_pom_content(
                "https://repo1.maven.org/maven2/g/a/1.0/a-1.0.pom"
            )
        assert result is None

    # === New test: _fetch_pom_content returns None on exception
    @pytest.mark.asyncio
    async def test_fetch_pom_content_exception(self, client):
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Connection error")
        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._fetch_pom_content(
                "https://repo1.maven.org/maven2/g/a/1.0/a-1.0.pom"
            )
        assert result is None

    # === New test: _fetch_pom returns None on exception
    @pytest.mark.asyncio
    async def test_fetch_pom_exception(self, client):
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Connection error")
        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._fetch_pom("g", "a", "1.0")
        assert result is None

    # === New test: get_package_versions non-200 raises HTTPException
    @pytest.mark.asyncio
    async def test_get_package_versions_non_200(self, client):
        mock_response = MagicMock()
        mock_response.status = 500
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            with pytest.raises(HTTPException) as exc_info:
                await client.get_package_versions("g", "a")
        assert exc_info.value.status_code == 404

    # === New test: get_package_info non-200 raises HTTPException 404
    @pytest.mark.asyncio
    async def test_get_package_info_non_200(self, client):
        mock_response = MagicMock()
        mock_response.status = 500
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            with pytest.raises(HTTPException) as exc_info:
                await client.get_package_info("g", "a")
        assert exc_info.value.status_code == 404

    # === New test: get_package_info session error raises HTTPException 500
    @pytest.mark.asyncio
    async def test_get_package_info_session_error(self, client):
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Network error")
        with patch.object(client, "_get_session", return_value=mock_session):
            with pytest.raises(HTTPException) as exc_info:
                await client.get_package_info("g", "a")
        assert exc_info.value.status_code == 500

    # === New test: _parse_version_range_syntax with empty parts
    def test_parse_version_range_syntax_empty_parts(self, client):
        result = client._parse_version_range_syntax("(,1.0.0]")
        assert result["min_version"] is None
        assert result["max_version"] == "1.0.0"

        result = client._parse_version_range_syntax("[1.0.0,)")
        assert result["min_version"] == "1.0.0"
        assert result["max_version"] is None

        result = client._parse_version_range_syntax("(,)")
        assert result["min_version"] is None
        assert result["max_version"] is None
