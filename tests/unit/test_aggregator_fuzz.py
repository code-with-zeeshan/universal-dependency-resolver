"""Hypothesis property-based fuzz tests for DataAggregator normalisation.

Ensures ``_normalize_dependencies``:
  1. Never crashes on any input
  2. Always returns a dict with ``"all"`` key containing a list of ``Dependency``
  3. Preserves required fields (name, version_spec, ecosystem)
  4. Handles edge cases (empty, malformed, mixed formats)
"""

import pytest
from hypothesis import given, strategies as st

from backend.core.data_aggregator import DataAggregator, Dependency, Ecosystem

# ── Helpers ─────────────────────────────────────────────────────────────────

_ecosystems = list(Ecosystem)
_eco_strategy = st.sampled_from(_ecosystems)

# Dependency name strategies
_pkg_name = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_."),
    min_size=1,
    max_size=30,
)

# Version spec strategies
_version_spec = st.one_of(
    st.just("*"),
    st.just(">=1.0"),
    st.just("==1.2.3"),
    st.just(">=1.0,<2.0"),
    st.just("^1.2.3"),
    st.just("~1.2.3"),
    st.text(max_size=10),
)

# Dict-format dep entry
_dict_dep = st.builds(
    lambda name, vs, marker: (
        {"version_spec": vs, "marker": marker} if marker is not None else {"version_spec": vs}
    ),
    name=_pkg_name,
    vs=_version_spec,
    marker=st.one_of(st.none(), st.just('sys_platform == "linux"'), st.text(max_size=20)),
)

# Dict-category deps (e.g. {"dependencies": {"pkg": ">=1.0"}})
_dict_category = st.builds(
    lambda names, vs: {n: vs for n in names},
    names=st.lists(_pkg_name, min_size=0, max_size=3, unique=True),
    vs=_version_spec,
)

# List-format deps (e.g. ["pkg>=1.0", "other>=2.0"])
_list_str_deps = st.lists(
    st.builds(lambda n, vs: f"{n}{vs}" if vs != "*" else n, n=_pkg_name, vs=_version_spec),
    min_size=0,
    max_size=5,
)

# List-format dict deps
_list_dict_deps = st.lists(
    st.builds(
        lambda name, vs, marker: (
            {"name": name, "version": vs, "marker": marker}
            if marker is not None
            else {"name": name, "version": vs}
        ),
        name=_pkg_name,
        vs=_version_spec,
        marker=st.one_of(st.none(), st.just('sys_platform == "linux"'), st.text(max_size=20)),
    ),
    min_size=0,
    max_size=5,
)

# Full dependency dict with categories
_full_deps_dict = st.builds(
    lambda deps, dev, opt, test, docs: {
        k: v
        for k, v in [
            ("dependencies", deps),
            ("dev_dependencies", dev),
            ("optional_dependencies", opt),
            ("test_dependencies", test),
            ("docs", docs),
        ]
        if len(v or {}) > 0
    },
    deps=_dict_category,
    dev=_dict_category,
    opt=_dict_category,
    test=_dict_category,
    docs=_dict_category,
)

# Any dependency input
_any_deps = st.one_of(
    st.none(),
    st.just({}),
    st.just([]),
    _full_deps_dict,
    _list_str_deps,
    _list_dict_deps,
    st.just({"dependencies": "not-a-dict"}),
    st.just({"dependencies": 42}),
    st.just([1, 2, 3]),  # non-string, non-dict list
)

# ── Tests ───────────────────────────────────────────────────────────────────


class TestNormalizeDependenciesFuzz:
    """Property-based fuzz tests for _normalize_dependencies."""

    @given(deps=_any_deps, eco=_eco_strategy)
    def test_never_crashes(self, deps, eco):
        """Should never crash on any input."""
        aggregator = DataAggregator()
        result = aggregator._normalize_dependencies(deps, eco)
        assert isinstance(result, dict)

    @given(deps=_any_deps, eco=_eco_strategy)
    def test_all_values_are_lists(self, deps, eco):
        """Every value in the result should be a list."""
        aggregator = DataAggregator()
        result = aggregator._normalize_dependencies(deps, eco)
        for key, val in result.items():
            assert isinstance(val, list), f"Key '{key}' has non-list value: {type(val)}"

    @given(deps=_any_deps, eco=_eco_strategy)
    def test_all_items_are_dependency_objects(self, deps, eco):
        """Every item in every list should be a Dependency."""
        aggregator = DataAggregator()
        result = aggregator._normalize_dependencies(deps, eco)
        for key, lst in result.items():
            for item in lst:
                assert isinstance(item, Dependency), (
                    f"Key '{key}' contains {type(item)} instead of Dependency"
                )

    @given(deps=_any_deps, eco=_eco_strategy)
    def test_every_dep_has_required_fields(self, deps, eco):
        """Every Dependency must have name, version_spec, and ecosystem set."""
        aggregator = DataAggregator()
        result = aggregator._normalize_dependencies(deps, eco)
        for key, lst in result.items():
            for dep in lst:
                assert dep.name is not None
                assert dep.version_spec is not None
                assert dep.ecosystem is not None

    @given(deps=_any_deps, eco=_eco_strategy)
    def test_eco_preserved(self, deps, eco):
        """The ecosystem passed in should match the Dependency.ecosystem."""
        aggregator = DataAggregator()
        result = aggregator._normalize_dependencies(deps, eco)
        for lst in result.values():
            for dep in lst:
                assert dep.ecosystem == eco

    @given(
        names=st.lists(_pkg_name, min_size=0, max_size=5, unique=True),
        vs=_version_spec,
        eco=_eco_strategy,
    )
    def test_flat_dict_preserved(self, names, vs, eco):
        """Flat dict deps like {'deps': {'pkg': '>=1.0'}} should preserve names."""
        deps = {"dependencies": {n: vs for n in names}}
        aggregator = DataAggregator()
        result = aggregator._normalize_dependencies(deps, eco)
        dep_names = {d.name for d in result.get("all", [])}
        assert dep_names == set(names)

    @given(eco=_eco_strategy)
    def test_empty_inputs(self, eco):
        """Empty inputs should produce empty results."""
        aggregator = DataAggregator()
        assert aggregator._normalize_dependencies(None, eco) == {}
        assert aggregator._normalize_dependencies({}, eco) == {}
        assert aggregator._normalize_dependencies([], eco) == {}

    @given(
        names=st.lists(_pkg_name, min_size=1, max_size=3, unique=True),
        vs=_version_spec,
        eco=_eco_strategy,
    )
    def test_all_deps_have_version_spec(self, names, vs, eco):
        """All deps should have a version_spec string."""
        deps = {"dependencies": {n: vs for n in names}}
        aggregator = DataAggregator()
        result = aggregator._normalize_dependencies(deps, eco)
        for dep in result.get("all", []):
            assert isinstance(dep.version_spec, str)
            assert len(dep.version_spec) > 0


class TestNormalizeDependenciesDictEntry:
    """Tests for the dict entry format with version_spec and marker."""

    @given(
        name=_pkg_name,
        version_spec=_version_spec,
        marker=st.one_of(st.none(), st.text(max_size=30)),
        eco=_eco_strategy,
    )
    def test_dict_entry_with_marker(self, name, version_spec, marker, eco):
        """Dict entries with version_spec+marker should create valid Dependency."""
        entry = {"version_spec": version_spec}
        if marker:
            entry["marker"] = marker
        deps = {"dependencies": {name: entry}}
        aggregator = DataAggregator()
        result = aggregator._normalize_dependencies(deps, eco)
        assert len(result.get("all", [])) == 1
        dep = result["all"][0]
        assert dep.name == name
        assert dep.version_spec == (str(version_spec) if version_spec else "*")
        if marker:
            assert dep.marker == marker
        else:
            assert dep.marker is None

    @given(
        name=_pkg_name,
        version_spec=_version_spec,
        eco=_eco_strategy,
    )
    def test_dict_entry_with_optional(self, name, version_spec, eco):
        """Dict entries with optional=True should set dep.optional."""
        entry = {"version_spec": version_spec, "optional": True}
        deps = {"optional_dependencies": {name: entry}}
        aggregator = DataAggregator()
        result = aggregator._normalize_dependencies(deps, eco)
        if "all" in result:
            for dep in result["all"]:
                if dep.name == name:
                    assert dep.optional is True


class TestNormalizeDependenciesMarkers:
    """Tests that markers are preserved through normalization."""

    def test_marker_in_dict_dep(self):
        """A dict dep with marker should preserve it."""
        deps = {
            "dependencies": {"foo": {"version_spec": ">=1.0", "marker": 'sys_platform == "win32"'}}
        }
        aggregator = DataAggregator()
        result = aggregator._normalize_dependencies(deps, Ecosystem("pypi"))
        dep = result["all"][0]
        assert dep.marker == 'sys_platform == "win32"'

    def test_marker_in_list_dep(self):
        """A list dep dict with marker should preserve it."""
        deps = {
            "dependencies": [
                {"name": "foo", "version": ">=1.0", "marker": 'sys_platform == "win32"'}
            ]
        }
        aggregator = DataAggregator()
        result = aggregator._normalize_dependencies(deps, Ecosystem("pypi"))
        dep = result["all"][0]
        assert dep.marker == 'sys_platform == "win32"'

    def test_no_marker_when_absent(self):
        """Deps without a marker should have marker=None."""
        deps = {"dependencies": {"foo": ">=1.0"}}
        aggregator = DataAggregator()
        result = aggregator._normalize_dependencies(deps, Ecosystem("pypi"))
        dep = result["all"][0]
        assert dep.marker is None
