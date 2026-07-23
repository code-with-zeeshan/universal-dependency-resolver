import pytest

from backend.api.helpers.packages import (
    _count_dependencies,
    _extract_version_compatibility,
    _filter_comparison_aspects,
    _filter_by_python_version,
    _generate_compatibility_summary,
    _generate_comparison_summary,
    _sort_search_results,
    _validate_system_info,
    validate_ecosystem,
)


class TestValidateEcosystem:
    def test_valid_ecosystem(self):
        assert validate_ecosystem("pypi") == "pypi"
        assert validate_ecosystem(" npm ") == "npm"

    def test_empty_string(self):
        assert validate_ecosystem("") is None

    def test_url_rejected(self):
        assert validate_ecosystem("http://evil.com") is None
        assert validate_ecosystem("file:///etc/passwd") is None

    def test_path_traversal_rejected(self):
        assert validate_ecosystem("../etc") is None

    def test_unknown_ecosystem(self):
        assert validate_ecosystem("nonexistent") is None

    def test_case_insensitive(self):
        assert validate_ecosystem("PyPI") == "pypi"


class TestFilterByPython:
    def test_no_python_requires(self):
        results = [{"name": "pkg"}]
        assert _filter_by_python_version(results, "3.10") == results

    def test_compatible_python(self):
        results = [{"name": "pkg", "python_requires": ">=3.8"}]
        assert len(_filter_by_python_version(results, "3.10")) == 1

    def test_incompatible_python(self):
        results = [{"name": "pkg", "python_requires": ">=3.8"}]
        assert len(_filter_by_python_version(results, "3.7")) == 0

    def test_python_versions_list_compatible(self):
        results = [{"name": "pkg", "python_versions": ["3.10", "3.11"]}]
        assert len(_filter_by_python_version(results, "3.10")) == 1

    def test_python_versions_list_incompatible(self):
        results = [{"name": "pkg", "python_versions": ["3.10", "3.11"]}]
        assert len(_filter_by_python_version(results, "3.9")) == 0

    def test_empty_results(self):
        assert _filter_by_python_version([], "3.10") == []


class TestSortSearchResults:
    def test_empty(self):
        assert _sort_search_results([], "name") == []

    def test_sort_by_downloads(self):
        results = [{"name": "b", "downloads": 100}, {"name": "a", "downloads": 200}]
        sorted_results = _sort_search_results(results, "downloads")
        assert sorted_results[0]["name"] == "a"

    def test_sort_by_name(self):
        results = [{"name": "b"}, {"name": "a"}]
        sorted_results = _sort_search_results(results, "name")
        assert sorted_results[0]["name"] == "a"

    def test_sort_by_updated(self):
        results = [
            {"name": "b", "last_updated": "2020-01-01"},
            {"name": "a", "last_updated": "2024-01-01"},
        ]
        sorted_results = _sort_search_results(results, "updated")
        assert sorted_results[0]["name"] == "a"

    def test_unknown_sort_returns_original(self):
        results = [{"name": "b"}, {"name": "a"}]
        assert _sort_search_results(results, "unknown") == results


class TestCountDependencies:
    def test_empty(self):
        assert _count_dependencies({"dependencies": {}}) == {
            "direct": 0,
            "transitive": 0,
            "total": 0,
        }

    def test_no_dependencies_key(self):
        assert _count_dependencies({}) == {"direct": 0, "transitive": 0, "total": 0}

    def test_with_direct_only(self):
        tree = {
            "dependencies": {
                "required": {
                    "dep1": {"dependencies": {}},
                    "dep2": {"dependencies": {}},
                }
            }
        }
        assert _count_dependencies(tree) == {"direct": 2, "transitive": 0, "total": 2}

    def test_with_nested_deps(self):
        tree = {
            "dependencies": {
                "required": {
                    "dep1": {"dependencies": {"required": {"subdep": {"dependencies": {}}}}}
                }
            }
        }
        result = _count_dependencies(tree)
        assert result["direct"] >= 1
        assert isinstance(result["total"], int)


class TestExtractVersionCompatibility:
    def test_version_found(self):
        info = {"versions": [{"version": "1.0", "python_requires": ">=3.8", "yanked": False}]}
        result = _extract_version_compatibility(info, "1.0")
        assert result["compatible"] is True
        assert result["python_requires"] == ">=3.8"

    def test_version_not_found(self):
        info = {"versions": [{"version": "2.0"}]}
        result = _extract_version_compatibility(info, "1.0")
        assert result["compatible"] is False

    def test_yanked_version(self):
        info = {"versions": [{"version": "1.0", "yanked": True}]}
        result = _extract_version_compatibility(info, "1.0")
        assert result["is_yanked"] is True

    def test_no_versions(self):
        info = {}
        result = _extract_version_compatibility(info, "1.0")
        assert result["compatible"] is False


class TestGenerateCompatibilitySummary:
    def test_basic(self):
        info = {"python_requires": ">=3.8", "platforms": ["linux"], "gpu_required": False}
        summary = _generate_compatibility_summary(info)
        assert summary["python_versions"] == ">=3.8"
        assert summary["platforms"] == ["linux"]
        assert summary["gpu_required"] is False

    def test_defaults(self):
        summary = _generate_compatibility_summary({})
        assert summary["min_python_version"] == "3.6"
        assert summary["max_python_version"] == "4.0"


class TestValidateSystemInfo:
    def test_valid(self):
        assert _validate_system_info({"os": "linux", "python_version": "3.10"}) is True

    def test_missing_os(self):
        assert _validate_system_info({"python_version": "3.10"}) is False

    def test_missing_python(self):
        assert _validate_system_info({"os": "linux"}) is False

    def test_empty(self):
        assert _validate_system_info({}) is False


class TestFilterComparisonAspects:
    def test_all_aspects(self):
        info = {
            "dependencies": {"a": "1.0"},
            "python_requires": ">=3.8",
            "platforms": ["linux"],
            "versions": ["1.0", "2.0"],
            "latest_version": "2.0",
        }
        filtered = _filter_comparison_aspects(info, None)
        assert "dependencies" in filtered
        assert "python_requires" in filtered

    def test_specific_aspect(self):
        info = {"dependencies": {"a": "1.0"}, "versions": ["1.0"]}
        filtered = _filter_comparison_aspects(info, "dependencies")
        assert "dependencies" in filtered
        assert "versions" not in filtered

    def test_empty_info(self):
        assert _filter_comparison_aspects({}, "") == {}

    def test_aspect_key_not_in_info(self):
        filtered = _filter_comparison_aspects({}, "dependencies")
        assert filtered == {}


class TestGenerateComparisonSummary:
    def test_single_package(self):
        data = {"pkg1": {"dependencies": {"a": "1.0", "b": "2.0"}}}
        summary = _generate_comparison_summary(data)
        assert "a" in summary["common_dependencies"]
        assert "b" in summary["common_dependencies"]

    def test_two_packages_common(self):
        data = {
            "pkg1": {"dependencies": {"a": "1.0", "b": "2.0"}},
            "pkg2": {"dependencies": {"a": "1.0", "c": "3.0"}},
        }
        summary = _generate_comparison_summary(data)
        assert "a" in summary["common_dependencies"]
        assert "b" not in summary["common_dependencies"]
        assert "c" not in summary["common_dependencies"]

    def test_empty_data(self):
        summary = _generate_comparison_summary({})
        assert summary["common_dependencies"] == []
