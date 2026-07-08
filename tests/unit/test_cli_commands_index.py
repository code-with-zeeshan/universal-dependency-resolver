"""Unit tests for cli/commands/index.py."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestResolveLockPath:
    def test_returns_lock_path_in_directory(self):
        from backend.cli.commands.index import _resolve_lock_path

        with patch("pathlib.Path.cwd", return_value=Path("/home/user")):
            result = _resolve_lock_path("/some/dir")
            assert result == Path("/some/dir/udr.lock")

    def test_default_to_cwd(self):
        from backend.cli.commands.index import _resolve_lock_path

        with patch("pathlib.Path.cwd", return_value=Path("/home/user")):
            result = _resolve_lock_path(None)
            assert result == Path("/home/user/udr.lock")


class TestFmtSize:
    def test_bytes(self):
        from backend.cli.commands.index import _fmt_size

        assert _fmt_size(500) == "500 B"

    def test_kilobytes(self):
        from backend.cli.commands.index import _fmt_size

        result = _fmt_size(2048)
        assert "KB" in result

    def test_megabytes(self):
        from backend.cli.commands.index import _fmt_size

        result = _fmt_size(2 * 1024 * 1024)
        assert "MB" in result


class TestCmdIndexStatus:
    def test_no_indexes(self):
        args = MagicMock()
        args.json = False

        with patch("backend.core.offline_index.list_indexes", return_value=[]):
            from backend.cli.commands.index import cmd_index_status

            result = cmd_index_status(args)
            assert result is None

    def test_json_output(self):
        args = MagicMock()
        args.json = True

        with patch("backend.core.offline_index.list_indexes", return_value=["pypi"]):
            with patch("backend.core.offline_index.index_status") as mock_status:
                mock_status.return_value = {
                    "packages": 100,
                    "versions": 500,
                    "size_bytes": 10240,
                    "metadata": {"updated_at": "2026-01-01"},
                }
                from backend.cli.commands.index import cmd_index_status

                result = cmd_index_status(args)
                assert result is None

    def test_table_output(self):
        args = MagicMock()
        args.json = False

        with patch("backend.core.offline_index.list_indexes", return_value=["pypi", "npm"]):
            with patch("backend.core.offline_index.index_status") as mock_status:
                mock_status.return_value = {
                    "packages": 100,
                    "versions": 500,
                    "size_bytes": 10240,
                    "metadata": {"updated_at": "2026-01-01"},
                }
                from backend.cli.commands.index import cmd_index_status

                result = cmd_index_status(args)
                assert result is None


class TestFetchAndStorePackage:
    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        from backend.cli.commands.index import _fetch_and_store_package

        mock_agg = MagicMock()
        mock_agg.get_package_info = AsyncMock(
            return_value={
                "versions": {
                    "pypi": [
                        {
                            "version": "2.31.0",
                            "release_date": "2023-01-01",
                            "requires_python": ">=3.7",
                        }
                    ],
                },
                "dependencies": {"pypi": {"urllib3": ">=1.21.1"}},
            }
        )
        sem = AsyncMock()
        sem.__aenter__ = AsyncMock()
        sem.__aenter__.return_value = None
        sem.__aexit__ = AsyncMock()
        sem.__aexit__.return_value = None

        result = await _fetch_and_store_package(mock_agg, "pypi", "requests", sem)
        assert result is not None
        assert result["name"] == "requests"
        assert "versions" in result
        assert result["versions"][0]["version"] == "2.31.0"

    @pytest.mark.asyncio
    async def test_fetch_error_returns_none(self):
        from backend.cli.commands.index import _fetch_and_store_package

        mock_agg = MagicMock()
        mock_agg.get_package_info = AsyncMock(side_effect=Exception("API error"))
        sem = AsyncMock()
        sem.__aenter__ = AsyncMock()
        sem.__aenter__.return_value = None
        sem.__aexit__ = AsyncMock()
        sem.__aexit__.return_value = None

        result = await _fetch_and_store_package(mock_agg, "pypi", "bad-pkg", sem)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_response_returns_none(self):
        from backend.cli.commands.index import _fetch_and_store_package

        mock_agg = MagicMock()
        mock_agg.get_package_info = AsyncMock(return_value=None)
        sem = AsyncMock()
        sem.__aenter__ = AsyncMock()
        sem.__aenter__.return_value = None
        sem.__aexit__ = AsyncMock()
        sem.__aexit__.return_value = None

        result = await _fetch_and_store_package(mock_agg, "pypi", "missing", sem)
        assert result is None


class TestCmdIndexPull:
    def test_pull_without_manifest(self):
        args = MagicMock()
        args.url = "https://example.com/indexes"
        args.ecosystem = None

        with patch(
            "backend.cli.commands.index._pull_index_async", new_callable=AsyncMock
        ) as mock_pull:
            mock_pull.return_value = 0
            from backend.cli.commands.index import cmd_index_pull

            with pytest.raises(SystemExit):
                cmd_index_pull(args)

    def test_pull_with_ecosystem(self):
        args = MagicMock()
        args.url = "https://example.com/indexes"
        args.ecosystem = "pypi"

        with patch(
            "backend.cli.commands.index._pull_index_async", new_callable=AsyncMock
        ) as mock_pull:
            mock_pull.return_value = 0
            from backend.cli.commands.index import cmd_index_pull

            with pytest.raises(SystemExit):
                cmd_index_pull(args)


class TestCmdIndexBuild:
    def test_build_with_packages(self):
        args = MagicMock()
        args.packages = "requests,flask"
        args.ecosystem = "pypi"
        args.directory = None

        with patch(
            "backend.cli.commands.index._build_from_names_async", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = 0
            from backend.cli.commands.index import cmd_index_build

            with pytest.raises(SystemExit):
                cmd_index_build(args)

    def test_build_without_packages_uses_lock_file(self):
        args = MagicMock()
        args.packages = None
        args.directory = "/tmp"

        with patch(
            "backend.cli.commands.index._build_from_lock_async", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = 0
            from backend.cli.commands.index import cmd_index_build

            with pytest.raises(SystemExit):
                cmd_index_build(args)
