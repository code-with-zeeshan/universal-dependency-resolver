"""Unit tests for ApkPlugin — structure, no network."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestApkPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("apk")
        assert cls is not None, "ApkPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "apk"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "APK (Alpine Linux)"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "apk-packages.txt" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_simple" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "apk"
        assert isinstance(inst, plugin_cls)
