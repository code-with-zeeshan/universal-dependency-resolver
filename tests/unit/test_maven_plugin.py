"""Unit tests for MavenPlugin — structure, no network."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestMavenPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("maven")
        assert cls is not None, "MavenPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "maven"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "Maven Central"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "pom.xml" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_maven" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "maven"
        assert isinstance(inst, plugin_cls)

    def test_no_lock_files(self, plugin_cls):
        assert len(plugin_cls.lock_files) == 0
