"""Unit tests for PackagistPlugin — structure, no network."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestPackagistPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("packagist")
        assert cls is not None, "PackagistPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "packagist"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "Packagist (PHP)"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "composer.json" in globs
        assert "composer.lock" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_composer_json" in parsers
        assert "parse_composer_lock" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "packagist"
        assert isinstance(inst, plugin_cls)
