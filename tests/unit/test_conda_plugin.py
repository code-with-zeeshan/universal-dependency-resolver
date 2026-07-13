"""Unit tests for CondaPlugin — structure, no network."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestCondaPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("conda")
        assert cls is not None, "CondaPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "conda"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "Conda (Anaconda)"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "environment.yml" in globs
        assert "environment.yaml" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_conda_env" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "conda"
        assert isinstance(inst, plugin_cls)
