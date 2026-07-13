"""Unit tests for AptPlugin — structure, no network."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestAptPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("apt")
        assert cls is not None, "AptPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "apt"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "APT (Debian/Ubuntu)"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "apt-packages.txt" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_simple" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "apt"
        assert isinstance(inst, plugin_cls)
