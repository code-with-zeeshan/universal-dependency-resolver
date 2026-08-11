"""Unit tests for cli/commands/check.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_lock_data():
    return {
        "version": "2.1",
        "packages": {
            "requests": {"ecosystem": "pypi", "resolved_version": "2.31.0"},
            "flask": {"ecosystem": "pypi", "resolved_version": "2.3.3"},
            "express": {"ecosystem": "npm", "resolved_version": "4.18.2"},
        },
    }


class TestCheckCve:
    @pytest.mark.asyncio
    async def test_no_lock_file(self):
        args = MagicMock()
        args.lock_path = "/fake/nonexistent/udr.lock"
        with patch("pathlib.Path.is_file", return_value=False):
            from backend.cli.commands.check import _check_cve

            with pytest.raises(SystemExit):
                await _check_cve(args)

    @pytest.mark.asyncio
    async def test_empty_lock_file(self):
        args = MagicMock()
        args.lock_path = "/fake/udr.lock"
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.check._read_lock_file", return_value={"packages": {}}):
                from backend.cli.commands.check import _check_cve

                result = await _check_cve(args)
                assert result[0] is True

    @pytest.mark.asyncio
    async def test_no_vulnerabilities_found(self, mock_lock_data):
        args = MagicMock()
        args.lock_path = "/fake/udr.lock"
        args.json = False
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.check._read_lock_file", return_value=mock_lock_data):
                with patch("backend.core.data_aggregator.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.check_vulnerabilities = AsyncMock(return_value=[])
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.check import _check_cve

                    result = await _check_cve(args)
                    assert result[0] is True
                    assert mock_agg.check_vulnerabilities.call_count == 3

    @pytest.mark.asyncio
    async def test_vulnerabilities_found(self, mock_lock_data):
        args = MagicMock()
        args.lock_path = "/fake/udr.lock"
        args.json = False
        mock_vuln = {
            "id": "GHSA-xxxx-xxxx-xxxx",
            "summary": "Test vulnerability in requests",
            "severity": [{"type": "CRITICAL", "score": "CRITICAL"}],
        }
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.check._read_lock_file", return_value=mock_lock_data):
                with patch("backend.core.data_aggregator.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.check_vulnerabilities = AsyncMock(
                        side_effect=[
                            [mock_vuln],
                            [],
                            [mock_vuln],
                        ]
                    )
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.check import _check_cve

                    result = await _check_cve(args)
                    assert result[0] is True
                    assert mock_agg.check_vulnerabilities.call_count == 3

    @pytest.mark.asyncio
    async def test_cve_with_severity_extraction(self, mock_lock_data):
        args = MagicMock()
        args.lock_path = "/fake/udr.lock"
        args.json = False
        vulns = [
            {
                "id": "CVE-2024-0001",
                "summary": "Critical issue",
                "severity": [{"type": "CRITICAL", "score": "CRITICAL"}],
            },
            {
                "id": "CVE-2024-0002",
                "summary": "Low severity issue",
                "severity": [{"type": "LOW", "score": "LOW"}],
            },
        ]
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.check._read_lock_file", return_value=mock_lock_data):
                with patch("backend.core.data_aggregator.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.check_vulnerabilities = AsyncMock(side_effect=[vulns, [], []])
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.check import _check_cve

                    result = await _check_cve(args)
                    assert result[0] is True

    @pytest.mark.asyncio
    async def test_osv_api_error_returns_empty(self, mock_lock_data):
        args = MagicMock()
        args.lock_path = "/fake/udr.lock"
        args.json = False
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.check._read_lock_file", return_value=mock_lock_data):
                with patch("backend.core.data_aggregator.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.check_vulnerabilities = AsyncMock(side_effect=Exception("API error"))
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.check import _check_cve

                    try:
                        result = await _check_cve(args)
                        assert result[0] is True
                    except Exception:
                        pytest.fail("API error should be caught internally")


class TestCheckLicenseJsonExitCode:
    @pytest.mark.asyncio
    async def test_denied_license_returns_ok_false_in_json_mode(self):
        args = MagicMock()
        args.directory = "/fake"
        args.workspace = None
        args.lock_file = None
        args.json = True
        lock_data = {
            "version": "2.1",
            "packages": {
                "foo": {
                    "ecosystem": "pypi",
                    "resolved_version": "1.0.0",
                    "license": "GPL-3.0-only",
                },
            },
        }
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.check._read_lock_file", return_value=lock_data):
                from backend.cli.commands.check import _check_license

                result = await _check_license(args)
                ok, payload = result
                assert ok is False
                assert payload["status"] == "violation"
                assert payload["denied"] == ["foo"]

    @pytest.mark.asyncio
    async def test_allowed_license_returns_ok_true(self):
        args = MagicMock()
        args.directory = "/fake"
        args.workspace = None
        args.lock_file = None
        args.json = True
        lock_data = {
            "version": "2.1",
            "packages": {
                "click": {"ecosystem": "pypi", "resolved_version": "8.1.7", "license": "MIT"},
            },
        }
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.check._read_lock_file", return_value=lock_data):
                from backend.cli.commands.check import _check_license

                ok, payload = await _check_license(args)
                assert ok is True
                assert payload["status"] == "ok"


class TestCheckDeprecatedJsonExitCode:
    @pytest.mark.asyncio
    async def test_yanked_returns_ok_false_in_json_mode(self):
        args = MagicMock()
        args.directory = "/fake"
        args.workspace = None
        args.lock_file = None
        args.json = True
        lock_data = {
            "version": "2.1",
            "packages": {
                "badpkg": {"ecosystem": "pypi", "resolved_version": "1.0.0", "yanked": True},
            },
        }
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.check._read_lock_file", return_value=lock_data):
                from backend.cli.commands.check import _check_deprecated

                ok, payload = await _check_deprecated(args)
                assert ok is False
                assert payload["status"] == "issues_found"

    @pytest.mark.asyncio
    async def test_deprecated_not_yanked_returns_ok_true(self):
        args = MagicMock()
        args.directory = "/fake"
        args.workspace = None
        args.lock_file = None
        args.json = True
        lock_data = {
            "version": "2.1",
            "packages": {
                "oldpkg": {"ecosystem": "pypi", "resolved_version": "1.0.0", "deprecated": True},
            },
        }
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.check._read_lock_file", return_value=lock_data):
                from backend.cli.commands.check import _check_deprecated

                ok, payload = await _check_deprecated(args)
                assert ok is True
                assert payload["status"] == "issues_found"


class TestOutputJsonExitCode:
    def test_output_json_ok_false_exits_1(self, capsys):
        from backend.cli._display import _output_json

        args = MagicMock()
        with pytest.raises(SystemExit) as excinfo:
            _output_json({"status": "violation"}, args, ok=False)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert '"status": "violation"' in out

    def test_output_json_ok_true_exits_0(self):
        from backend.cli._display import _output_json

        args = MagicMock()
        with pytest.raises(SystemExit) as excinfo:
            _output_json({"ok": True}, args, ok=True)
        assert excinfo.value.code == 0
