"""Unit tests for cli/commands/versions.py and cli/commands/dependencies.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestVersionsCommand:
    @pytest.mark.asyncio
    async def test_json_versions_sorted_newest_first(self, capsys):
        args = MagicMock()
        args.package = "click"
        args.ecosystem = "pypi"
        args.json = True
        data = {
            "name": "click",
            "versions": {
                "pypi": [{"version": "8.1.0"}, {"version": "8.4.2"}, {"version": "8.0.0"}]
            },
        }
        with patch("backend.core.DataAggregator") as mock_cls:
            mock_agg = MagicMock()
            mock_agg.get_package_info = AsyncMock(return_value=data)
            mock_agg.close = AsyncMock()
            mock_cls.return_value = mock_agg

            from backend.cli.commands.versions import _cmd_versions_async

            rc = await _cmd_versions_async(args)
            assert rc == 0
            import json as json_mod

            out = json_mod.loads(capsys.readouterr().out)
            assert out["versions"] == ["8.4.2", "8.1.0", "8.0.0"]
            assert out["package"] == "click"

    @pytest.mark.asyncio
    async def test_missing_package_json_exits_code_1(self, capsys):
        args = MagicMock()
        args.package = "nonexistent"
        args.ecosystem = "pypi"
        args.json = True
        with patch("backend.core.DataAggregator") as mock_cls:
            mock_agg = MagicMock()
            mock_agg.get_package_info = AsyncMock(
                return_value={"name": "nonexistent", "versions": {"pypi": []}}
            )
            mock_agg.close = AsyncMock()
            mock_cls.return_value = mock_agg

            from backend.cli.commands.versions import _cmd_versions_async

            rc = await _cmd_versions_async(args)
            assert rc == 1
            import json as json_mod

            out = json_mod.loads(capsys.readouterr().out)
            assert out["error"] == "No versions found"


class TestDependenciesCommand:
    @pytest.mark.asyncio
    async def test_json_flattens_categories(self, capsys):
        args = MagicMock()
        args.package = "flask"
        args.ecosystem = "pypi"
        args.json = True
        dep = MagicMock()
        dep.name = "jinja2"
        dep.version_spec = ">=3.1.2"
        dep2 = MagicMock()
        dep2.name = "markupsafe"
        dep2.version_spec = ">=2.1.1"
        data = {
            "name": "flask",
            "dependencies": {"pypi": {"all": [dep, dep2]}},
        }
        with patch("backend.core.DataAggregator") as mock_cls:
            mock_agg = MagicMock()
            mock_agg.get_package_info = AsyncMock(return_value=data)
            mock_agg.close = AsyncMock()
            mock_cls.return_value = mock_agg

            from backend.cli.commands.dependencies import _cmd_dependencies_async

            rc = await _cmd_dependencies_async(args)
            assert rc == 0
            import json as json_mod

            out = json_mod.loads(capsys.readouterr().out)
            assert out["dependencies"] == {"jinja2": ">=3.1.2", "markupsafe": ">=2.1.1"}

    @pytest.mark.asyncio
    async def test_no_deps_is_valid_exit_0(self):
        args = MagicMock()
        args.package = "click"
        args.ecosystem = "pypi"
        args.json = True
        data = {"name": "click", "dependencies": {"pypi": {}}}
        with patch("backend.core.DataAggregator") as mock_cls:
            mock_agg = MagicMock()
            mock_agg.get_package_info = AsyncMock(return_value=data)
            mock_agg.close = AsyncMock()
            mock_cls.return_value = mock_agg

            from backend.cli.commands.dependencies import _cmd_dependencies_async

            rc = await _cmd_dependencies_async(args)
            assert rc == 0
