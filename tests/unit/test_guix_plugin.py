"""Unit tests for GuixPlugin."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestGuixPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("guix")
        assert cls is not None, "GuixPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "guix"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "GNU Guix"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "guix.scm" in globs
        assert "manifest.scm" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_guix_scm" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "guix"
        assert isinstance(inst, plugin_cls)

    def test_parse_guix_scm_list(self, plugin_cls):
        content = """(use-modules (gnu packages))
(manifest
  (list (specification->package "python")
        (specification->package "curl")
        "gcc"
        "make"))
"""
        result = plugin_cls.parse_guix_scm(content)
        names = {d["name"] for d in result}
        assert "python" in names
        assert "curl" in names
        assert "gcc" in names
        assert "make" in names

    def test_parse_guix_scm_empty(self, plugin_cls):
        result = plugin_cls.parse_guix_scm("")
        assert result == []

    def test_parse_guix_scm_no_matches(self, plugin_cls):
        content = "(define foo 42)\n"
        result = plugin_cls.parse_guix_scm(content)
        assert result == []

    def test_parse_guix_scm_skips_paths(self, plugin_cls):
        content = """(list "/usr/bin/python" ".local/bin" "python")"""
        result = plugin_cls.parse_guix_scm(content)
        names = {d["name"] for d in result}
        assert "python" in names
        assert "/usr/bin/python" not in names
        assert ".local/bin" not in names

    def test_parse_guix_scm_skips_numbers(self, plugin_cls):
        content = """(list "1.0" "2.3.4" "python")"""
        result = plugin_cls.parse_guix_scm(content)
        names = {d["name"] for d in result}
        assert "python" in names
        assert "1.0" not in names
        assert "2.3.4" not in names

    @pytest.mark.asyncio
    async def test_get_package_info(self, plugin_cls):
        inst = plugin_cls()
        result = await inst.get_package_info("hello")
        # Guix has no remote API — returns None with a warning
        assert result is None
