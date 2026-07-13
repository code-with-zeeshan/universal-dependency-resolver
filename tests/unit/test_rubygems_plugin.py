"""Unit tests for RubyGemsPlugin — structure, no network."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestRubyGemsPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("rubygems")
        assert cls is not None, "RubyGemsPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "rubygems"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "RubyGems (Ruby)"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "Gemfile" in globs
        assert "Gemfile.lock" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_gemfile" in parsers
        assert "parse_gemfile_lock" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "rubygems"
        assert isinstance(inst, plugin_cls)
