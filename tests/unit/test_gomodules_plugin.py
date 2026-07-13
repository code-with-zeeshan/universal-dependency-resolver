"""Unit tests for GoModulesPlugin — structure, no network."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestGoModulesPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("gomodules")
        assert cls is not None, "GoModulesPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "gomodules"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "Go Modules"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "go.mod" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_go_mod" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "gomodules"
        assert isinstance(inst, plugin_cls)
