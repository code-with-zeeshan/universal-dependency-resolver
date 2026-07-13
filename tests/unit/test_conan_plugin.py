"""Unit tests for ConanPlugin."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestConanPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("conan")
        assert cls is not None, "ConanPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "conan"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "Conan (C/C++)"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "conanfile.txt" in globs
        assert "conanfile.py" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_conanfile_txt" in parsers
        assert "parse_conanfile_py" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "conan"
        assert isinstance(inst, plugin_cls)

    def test_parse_conanfile_txt_with_requires(self, plugin_cls):
        content = "[requires]\npkg/1.0.0\nother/2.0.0"
        result = plugin_cls.parse_conanfile_txt(content)
        names = {(d["name"], d["version"]) for d in result}
        assert ("pkg", "1.0.0") in names
        assert ("other", "2.0.0") in names
        for d in result:
            assert d["_ecosystem"] == "conan"

    def test_parse_conanfile_txt_no_requires(self, plugin_cls):
        content = "[build_requires]\ncmake/3.22.0"
        result = plugin_cls.parse_conanfile_txt(content)
        assert result == []

    def test_parse_conanfile_txt_with_channel(self, plugin_cls):
        content = "[requires]\npkg/1.0.0@user/stable"
        result = plugin_cls.parse_conanfile_txt(content)
        assert len(result) == 1
        assert result[0]["name"] == "pkg"
        assert result[0]["version"] == "1.0.0"

    def test_parse_conanfile_py_self_requires(self, plugin_cls):
        content = """from conans import ConanFile

class MyPkg(ConanFile):
    def requirements(self):
        self.requires("pkg/1.0.0")
        self.requires("other/2.0.0")
"""
        result = plugin_cls.parse_conanfile_py(content)
        names = {(d["name"], d["version"]) for d in result}
        assert ("pkg", "1.0.0") in names
        assert ("other", "2.0.0") in names
        for d in result:
            assert d["_ecosystem"] == "conan"

    def test_parse_conanfile_py_no_requires(self, plugin_cls):
        content = """from conans import ConanFile

class MyPkg(ConanFile):
    pass
"""
        result = plugin_cls.parse_conanfile_py(content)
        assert result == []

    def test_parse_empty_content(self, plugin_cls):
        assert plugin_cls.parse_conanfile_txt("") == []
        assert plugin_cls.parse_conanfile_py("") == []

    @pytest.mark.asyncio
    async def test_get_package_info(self, plugin_cls):
        inst = plugin_cls()
        result = await inst.get_package_info("pkg")
        assert result is not None
        assert result["ecosystem"] == "conan"
        assert result["version"] == "latest"

    def test_parse_conanfile_py_tuple_requires(self, plugin_cls):
        content = """from conans import ConanFile

class MyPkg(ConanFile):
    requires = ("pkg/1.0.0", "other/2.0.0")
"""
        result = plugin_cls.parse_conanfile_py(content)
        names = {(d["name"], d["version"]) for d in result}
        assert ("pkg", "1.0.0") in names
        assert ("other", "2.0.0") in names
