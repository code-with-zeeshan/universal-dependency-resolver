"""Unit tests for VcpkgPlugin."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestVcpkgPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("vcpkg")
        assert cls is not None, "VcpkgPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "vcpkg"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "Vcpkg (C/C++)"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "vcpkg.json" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_vcpkg_json" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "vcpkg"
        assert isinstance(inst, plugin_cls)

    def test_parse_simple_string_deps(self, plugin_cls):
        content = '{"dependencies": ["fmt", "spdlog"]}'
        result = plugin_cls.parse_vcpkg_json(content)
        names = {d["name"] for d in result}
        assert "fmt" in names
        assert "spdlog" in names
        for d in result:
            assert d["version"] == "*"
            assert d["_ecosystem"] == "vcpkg"

    def test_parse_versioned_object_deps(self, plugin_cls):
        content = '{"dependencies": [{"name": "fmt", "version>=": "7.1.3"}]}'
        result = plugin_cls.parse_vcpkg_json(content)
        assert len(result) == 1
        assert result[0]["name"] == "fmt"
        assert result[0]["version"] == "7.1.3"
        assert result[0]["_ecosystem"] == "vcpkg"

    def test_parse_empty_dependencies(self, plugin_cls):
        content = '{"dependencies": []}'
        result = plugin_cls.parse_vcpkg_json(content)
        assert result == []

    def test_parse_mixed_string_and_object_deps(self, plugin_cls):
        content = '{"dependencies": ["fmt", {"name": "boost", "version>=": "1.80.0"}]}'
        result = plugin_cls.parse_vcpkg_json(content)
        names = {(d["name"], d["version"]) for d in result}
        assert ("fmt", "*") in names
        assert ("boost", "1.80.0") in names

    def test_parse_invalid_json(self, plugin_cls):
        result = plugin_cls.parse_vcpkg_json("not-json")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_package_info(self, plugin_cls):
        inst = plugin_cls()
        result = await inst.get_package_info("fmt")
        assert result is not None
        assert result["ecosystem"] == "vcpkg"
        assert result["version"] == "latest"
