"""Unit tests for CustomDbPlugin — structure, no network."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestCustomDbPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("custom_db")
        assert cls is not None, "CustomDbPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "custom_db"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "Compatibility Database"

    def test_no_manifests(self, plugin_cls):
        assert len(plugin_cls.manifests) == 0

    def test_no_lock_files(self, plugin_cls):
        assert len(plugin_cls.lock_files) == 0

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "custom_db"
        assert isinstance(inst, plugin_cls)
