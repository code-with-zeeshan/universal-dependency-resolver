"""Unit tests for PypiPlugin — structure & delegation, no network."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestPypiPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("pypi")
        assert cls is not None, "PypiPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "pypi"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "PyPI (Python)"

    def test_auth_prefix(self, plugin_cls):
        assert plugin_cls.auth_prefix == "PYPI"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "requirements.txt" in globs
        assert "pyproject.toml" in globs
        assert "Pipfile" in globs
        assert "Pipfile.lock" in globs
        assert "poetry.lock" in globs
        assert "uv.lock" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_requirements" in parsers
        assert "parse_pyproject" in parsers
        assert "parse_pipfile" in parsers
        assert "parse_pipfile_lock" in parsers
        assert "parse_poetry_lock" in parsers
        assert "parse_uv_lock" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "pypi"
        assert isinstance(inst, plugin_cls)

    def test_has_lock_files(self, plugin_cls):
        """PyPI lock files (poetry.lock, uv.lock) are registered as manifests,
        not as PluginLockFile entries, since they're parsed inline."""
        assert len(plugin_cls.lock_files) == 0

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
