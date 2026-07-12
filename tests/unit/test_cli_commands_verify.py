"""Unit tests for cli/commands/verify.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCmdVerify:
    @pytest.mark.asyncio
    async def test_empty_lock_file(self):
        args = MagicMock()
        args.lock_file = "/tmp/nonexistent/udr.lock"
        args.json = False

        with patch("backend.cli.commands.verify._read_lock_file", return_value={"packages": {}}):
            with patch("pathlib.Path.is_file", return_value=True):
                from backend.cli.commands.verify import _cmd_verify_async

                result = await _cmd_verify_async(args)
                assert result == 0

    @pytest.mark.asyncio
    async def test_verify_all_packages_ok(self):
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = False

        mock_data = {
            "packages": {
                "requests": {"ecosystem": "pypi", "resolved_version": "2.31.0"},
                "flask": {"ecosystem": "pypi", "resolved_version": "2.3.3"},
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.core.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.get_package_info = AsyncMock(
                        side_effect=[
                            {"versions": {"pypi": [{"version": "2.31.0"}]}},
                            {"versions": {"pypi": [{"version": "2.3.3"}]}},
                        ]
                    )
                    mock_agg.close = AsyncMock()
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.verify import _cmd_verify_async

                    result = await _cmd_verify_async(args)
                    assert result == 0

    @pytest.mark.asyncio
    async def test_verify_version_not_found(self):
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = False

        mock_data = {
            "packages": {
                "gone": {"ecosystem": "pypi", "resolved_version": "999.0.0"},
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.core.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.get_package_info = AsyncMock(
                        return_value={"versions": {"pypi": [{"version": "1.0.0"}]}}
                    )
                    mock_agg.close = AsyncMock()
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.verify import _cmd_verify_async

                    result = await _cmd_verify_async(args)
                    assert result == 1

    @pytest.mark.asyncio
    async def test_verify_package_not_found(self):
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = False

        mock_data = {
            "packages": {
                "missing": {"ecosystem": "pypi", "resolved_version": "1.0.0"},
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.core.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.get_package_info = AsyncMock(return_value=None)
                    mock_agg.close = AsyncMock()
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.verify import _cmd_verify_async

                    result = await _cmd_verify_async(args)
                    assert result == 1

    @pytest.mark.asyncio
    async def test_verify_with_missing_version_field(self):
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = False

        mock_data = {
            "packages": {
                "noversion": {"ecosystem": "pypi"},
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.core.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.close = AsyncMock()
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.verify import _cmd_verify_async

                    result = await _cmd_verify_async(args)
                    assert result is None or result == 0

    @pytest.mark.asyncio
    async def test_verify_json_output(self):
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = True

        mock_data = {
            "packages": {
                "requests": {"ecosystem": "pypi", "resolved_version": "2.31.0"},
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.core.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.get_package_info = AsyncMock(
                        return_value={"versions": {"pypi": [{"version": "2.31.0"}]}}
                    )
                    mock_agg.close = AsyncMock()
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.verify import _cmd_verify_async

                    result = await _cmd_verify_async(args)
                    assert result == 0

    @pytest.mark.asyncio
    async def test_verify_integrity_match(self):
        """Integrity check passes when stored hash matches registry."""
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = False

        mock_data = {
            "packages": {
                "requests": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.31.0",
                    "integrity": {"algorithm": "sha256", "value": "abc123"},
                },
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.cli.commands.verify._pin_integrity", True):
                    with patch("backend.core.DataAggregator") as mock_agg_cls:
                        mock_agg = MagicMock()
                        mock_agg.get_package_info = AsyncMock(
                            return_value={"versions": {"pypi": [{"version": "2.31.0"}]}}
                        )
                        mock_agg.get_artifact_hash = AsyncMock(
                            return_value={"algorithm": "sha256", "value": "abc123"}
                        )
                        mock_agg.close = AsyncMock()
                        mock_agg_cls.return_value = mock_agg

                        from backend.cli.commands.verify import _cmd_verify_async

                        result = await _cmd_verify_async(args)
                        assert result == 0

    @pytest.mark.asyncio
    async def test_verify_integrity_mismatch(self):
        """Integrity check fails when stored hash differs from registry."""
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = False

        mock_data = {
            "packages": {
                "requests": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.31.0",
                    "integrity": {"algorithm": "sha256", "value": "stored_hash"},
                },
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.cli.commands.verify._pin_integrity", True):
                    with patch("backend.core.DataAggregator") as mock_agg_cls:
                        mock_agg = MagicMock()
                        mock_agg.get_package_info = AsyncMock(
                            return_value={"versions": {"pypi": [{"version": "2.31.0"}]}}
                        )
                        mock_agg.get_artifact_hash = AsyncMock(
                            return_value={"algorithm": "sha256", "value": "registry_hash"}
                        )
                        mock_agg.close = AsyncMock()
                        mock_agg_cls.return_value = mock_agg

                        from backend.cli.commands.verify import _cmd_verify_async

                        result = await _cmd_verify_async(args)
                        assert result == 1
