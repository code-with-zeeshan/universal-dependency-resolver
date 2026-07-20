"""Hypothesis property-based fuzz tests for manifest parsers.

Ensures every ``_parse_*`` method in ``ManifestDetector``:
  1. Never crashes on any input
  2. Returns a list of dicts
  3. Handles edge cases gracefully
"""

from hypothesis import given, settings, strategies as st

from backend.manifest_detector import ManifestDetector

# ── Shared strategies ─────────────────────────────────────────────────────────

# Any text (worst-case for parsers)
_any_text = st.text()
_line = st.text(max_size=500)
_lines = st.lists(_line, min_size=0, max_size=50).map("\n".join)

# Numbered lines (like DEPS lines)
_numbered_line = (
    st.integers(min_value=0, max_value=9999)
    .map(str)
    .flatmap(lambda n: st.text(max_size=200).map(lambda t: f"{n}:{t}"))
)
_mix_lines = st.lists(st.one_of(_line, _numbered_line), min_size=0, max_size=30).map("\n".join)

# ── Nix file strategies ───────────────────────────────────────────────────────

_nix_attr = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
    min_size=0,
    max_size=20,
)
_nix_bracket_line = st.builds(
    lambda inside: f"[{inside}]",
    st.text(max_size=30),
)

# ── Go mod strategies ─────────────────────────────────────────────────────────

_go_require_line = st.builds(
    lambda module, version, comment: f"\t{module} {version}{'  // ' + comment if comment else ''}",
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz/.-_@", min_size=1, max_size=30),
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789.-_", min_size=1, max_size=15),
    st.text(max_size=50),
)
_go_replace_line = st.builds(
    lambda old, new, ver: f"\t{old} => {new} {ver}",
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz/.-_@", min_size=1, max_size=20),
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz/.-_@", min_size=1, max_size=20),
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789.-_", min_size=1, max_size=15),
)

# ── Yarn lock strategies ──────────────────────────────────────────────────────

_yarn_key = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@/.-_",
    min_size=1,
    max_size=30,
)


# ── Detector instance (used by all tests) ─────────────────────────────────────


def _detector():
    return ManifestDetector()


# ==============================================================================
# Requirements parser
# ==============================================================================


class TestParseRequirementsFuzz:
    """Fuzz tests for ``_parse_requirements``."""

    @settings(max_examples=30)
    @given(content=_lines)
    def test_never_crashes(self, content):
        detector = _detector()
        result = detector._parse_requirements(content)
        assert isinstance(result, list)
        for pkg in result:
            assert isinstance(pkg, dict)

    @settings(max_examples=30)
    @given(content=_lines)
    def test_each_result_has_required_keys(self, content):
        detector = _detector()
        result = detector._parse_requirements(content)
        for pkg in result:
            assert "name" in pkg
            assert "version" in pkg


# ==============================================================================
# Cabal parser (state machine with continuation lines)
# ==============================================================================


class TestParseCabalFuzz:
    """Fuzz tests for ``_parse_cabal``."""

    @settings(max_examples=30)
    @given(content=_lines)
    def test_never_crashes(self, content):
        detector = _detector()
        result = detector._parse_cabal(content)
        assert isinstance(result, list)
        for pkg in result:
            assert isinstance(pkg, dict)

    @settings(max_examples=20)
    @given(
        before=st.text(max_size=100),
        deps_line=st.text(max_size=200),
        after=st.text(max_size=100),
    )
    def test_with_build_depends(self, before, deps_line, after):
        content = f"{before}\nbuild-depends: {deps_line}\n{after}"
        detector = _detector()
        result = detector._parse_cabal(content)
        assert isinstance(result, list)

    @settings(max_examples=20)
    @given(
        lines=st.lists(
            st.builds(
                lambda indent, dep: f"{' ' * indent}build-depends: {dep}",
                indent=st.integers(min_value=0, max_value=8),
                dep=st.text(max_size=100),
            ),
            min_size=0,
            max_size=20,
        )
    )
    def test_with_multi_line_build_depends(self, lines):
        content = "\n".join(lines)
        detector = _detector()
        result = detector._parse_cabal(content)
        assert isinstance(result, list)


# ==============================================================================
# Go mod parser (state machine with require/replace blocks)
# ==============================================================================


class TestParseGoModFuzz:
    """Fuzz tests for ``_parse_go_mod``."""

    @settings(max_examples=30)
    @given(content=_lines)
    def test_never_crashes(self, content):
        detector = _detector()
        result = detector._parse_go_mod(content)
        assert isinstance(result, list)
        for pkg in result:
            assert isinstance(pkg, dict)

    @settings(max_examples=15)
    @given(
        lines=st.lists(
            st.one_of(_go_require_line, _go_replace_line, _line),
            min_size=0,
            max_size=20,
        )
    )
    def test_with_require_and_replace(self, lines):
        content = "module example.com/test\n\ngo 1.21\n\nrequire (\n" + "\n".join(lines) + "\n)\n"
        content += "\nreplace (\n" + "\n".join(lines[:5]) + "\n)\n"
        detector = _detector()
        result = detector._parse_go_mod(content)
        assert isinstance(result, list)


# ==============================================================================
# Yarn lock parser
# ==============================================================================


class TestParseYarnLockFuzz:
    """Fuzz tests for ``_parse_yarn_lock``."""

    @settings(max_examples=30)
    @given(content=_lines)
    def test_never_crashes(self, content):
        detector = _detector()
        result = detector._parse_yarn_lock(content)
        assert isinstance(result, list)
        for pkg in result:
            assert isinstance(pkg, dict)

    @settings(max_examples=15)
    @given(
        keys=st.lists(_yarn_key, min_size=0, max_size=10, unique=True),
        versions=st.lists(st.text(max_size=20), min_size=0, max_size=10),
        resolution=st.text(max_size=50),
    )
    def test_with_yarn_entries(self, keys, versions, resolution):
        lines = []
        for key in keys:
            version = versions[len(versions) % (len(versions) or 1)] if versions else "1.0.0"
            lines.append(f'"{key}":')
            lines.append(f'  version "{version}"')
            lines.append(f'  resolved "{resolution}"')
        content = "\n".join(lines)
        detector = _detector()
        result = detector._parse_yarn_lock(content)
        assert isinstance(result, list)


# ==============================================================================
# Gradle parser (multi-pattern regex)
# ==============================================================================


class TestParseGradleFuzz:
    """Fuzz tests for ``_parse_gradle``."""

    @settings(max_examples=30)
    @given(content=_lines)
    def test_never_crashes(self, content):
        detector = _detector()
        result = detector._parse_gradle(content)
        assert isinstance(result, list)
        for pkg in result:
            assert isinstance(pkg, dict)

    @settings(max_examples=15)
    @given(
        config=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20),
        notation=st.text(max_size=100),
    )
    def test_with_groovy_notation(self, config, notation):
        content = f"{config} '{notation}'"
        detector = _detector()
        result = detector._parse_gradle(content)
        assert isinstance(result, list)


# ==============================================================================
# Nix parser (bracket-depth state machine)
# ==============================================================================


class TestParseNixFuzz:
    """Fuzz tests for ``_parse_nix``."""

    @settings(max_examples=30)
    @given(content=_lines)
    def test_never_crashes(self, content):
        detector = _detector()
        result = detector._parse_nix(content)
        assert isinstance(result, list)
        for pkg in result:
            assert isinstance(pkg, dict)


# ==============================================================================
# Pyproject parser (TOML + nested optional deps)
# ==============================================================================


class TestParsePyprojectFuzz:
    """Fuzz tests for ``_parse_pyproject``."""

    @settings(max_examples=30)
    @given(content=_lines)
    def test_never_crashes(self, content):
        detector = _detector()
        result = detector._parse_pyproject(content)
        assert isinstance(result, list)
        for pkg in result:
            assert isinstance(pkg, dict)


# ==============================================================================
# Go work parser
# ==============================================================================


class TestParseGoWorkFuzz:
    """Fuzz tests for ``_parse_go_work``."""

    @settings(max_examples=30)
    @given(content=_lines)
    def test_never_crashes(self, content):
        detector = _detector()
        result = detector._parse_go_work(content)
        assert isinstance(result, list)
        for pkg in result:
            assert isinstance(pkg, dict)


# ==============================================================================
# Gemfile lock parser (indentation-based)
# ==============================================================================


class TestParseGemfileLockFuzz:
    """Fuzz tests for ``_parse_gemfile_lock``."""

    @settings(max_examples=30)
    @given(content=_lines)
    def test_never_crashes(self, content):
        detector = _detector()
        result = detector._parse_gemfile_lock(content)
        assert isinstance(result, list)
        for pkg in result:
            assert isinstance(pkg, dict)


# ==============================================================================
# Simple parser (apt/apk)
# ==============================================================================


class TestParseSimpleFuzz:
    """Fuzz tests for ``_parse_simple``."""

    @settings(max_examples=30)
    @given(content=_lines)
    def test_never_crashes(self, content):
        detector = _detector()
        result = detector._parse_simple(content)
        assert isinstance(result, list)
        for pkg in result:
            assert isinstance(pkg, dict)


# ==============================================================================
# Mix lock parser (Elixir)
# ==============================================================================


class TestParseMixLockFuzz:
    """Fuzz tests for ``_parse_mix_lock``."""

    @settings(max_examples=30)
    @given(content=_mix_lines)
    def test_never_crashes(self, content):
        detector = _detector()
        result = detector._parse_mix_lock(content)
        assert isinstance(result, list)
        for pkg in result:
            assert isinstance(pkg, dict)


# ==============================================================================
# Guix SCM parser
# ==============================================================================


class TestParseGuixScmFuzz:
    """Fuzz tests for ``_parse_guix_scm``."""

    @settings(max_examples=30)
    @given(content=_lines)
    def test_never_crashes(self, content):
        detector = _detector()
        result = detector._parse_guix_scm(content)
        assert isinstance(result, list)
        for pkg in result:
            assert isinstance(pkg, dict)
