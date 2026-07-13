"""Unit tests for HomebrewPlugin — structure, no network."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestHomebrewPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("homebrew")
        assert cls is not None, "HomebrewPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "homebrew"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "Homebrew (macOS/Linux)"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "Brewfile" in globs
        assert "Brewfile.lock.json" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_homebrew" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "homebrew"
        assert isinstance(inst, plugin_cls)
