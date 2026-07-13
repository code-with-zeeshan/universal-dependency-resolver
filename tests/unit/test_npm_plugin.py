"""Unit tests for NpmPlugin — structure & delegation, no network."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestNpmPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("npm")
        assert cls is not None, "NpmPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "npm"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "NPM (Node.js)"

    def test_auth_prefix(self, plugin_cls):
        assert plugin_cls.auth_prefix == "NPM"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "package.json" in globs
        assert "package-lock.json" in globs
        assert "yarn.lock" in globs
        assert "pnpm-lock.yaml" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_package_json" in parsers
        assert "parse_package_lock" in parsers
        assert "parse_yarn_lock" in parsers
        assert "parse_pnpm_lock" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "npm"
        assert isinstance(inst, plugin_cls)

    @pytest.mark.asyncio
    async def test_get_package_info_unknown_package(self, plugin_cls):
        inst = plugin_cls()
        result = await inst.get_package_info(
            "this_package_definitely_does_not_exist_xyz",
            include_versions=True,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_versions_unknown_package(self, plugin_cls):
        inst = plugin_cls()
        result = await inst.get_package_versions("this_package_definitely_does_not_exist_xyz")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_artifact_hash_unknown(self, plugin_cls):
        inst = plugin_cls()
        result = await inst.get_artifact_hash("this_package_definitely_does_not_exist_xyz", "1.0.0")
        assert result is None
