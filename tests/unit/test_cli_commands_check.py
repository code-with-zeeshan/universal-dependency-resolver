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
        args.lock_path = "/tmp/nonexistent/udr.lock"
        with patch("pathlib.Path.is_file", return_value=False):
            from backend.cli.commands.check import _check_cve

            with pytest.raises(SystemExit):
                await _check_cve(args)

    @pytest.mark.asyncio
    async def test_empty_lock_file(self):
        args = MagicMock()
        args.lock_path = "/tmp/udr.lock"
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.check._read_lock_file", return_value={"packages": {}}):
                from backend.cli.commands.check import _check_cve

                result = await _check_cve(args)
                assert result is True

    @pytest.mark.asyncio
    async def test_no_vulnerabilities_found(self, mock_lock_data):
        args = MagicMock()
        args.lock_path = "/tmp/udr.lock"
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.check._read_lock_file", return_value=mock_lock_data):
                with patch("backend.core.data_aggregator.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.check_vulnerabilities = AsyncMock(return_value=[])
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.check import _check_cve

                    result = await _check_cve(args)
                    assert result is True
                    assert mock_agg.check_vulnerabilities.call_count == 3

    @pytest.mark.asyncio
    async def test_vulnerabilities_found(self, mock_lock_data):
        args = MagicMock()
        args.lock_path = "/tmp/udr.lock"
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
                    assert result is True
                    assert mock_agg.check_vulnerabilities.call_count == 3

    @pytest.mark.asyncio
    async def test_cve_with_severity_extraction(self, mock_lock_data):
        args = MagicMock()
        args.lock_path = "/tmp/udr.lock"
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
                    assert result is True

    @pytest.mark.asyncio
    async def test_osv_api_error_returns_empty(self, mock_lock_data):
        args = MagicMock()
        args.lock_path = "/tmp/udr.lock"
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.check._read_lock_file", return_value=mock_lock_data):
                with patch("backend.core.data_aggregator.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.check_vulnerabilities = AsyncMock(side_effect=Exception("API error"))
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.check import _check_cve

                    try:
                        result = await _check_cve(args)
                        assert result is True
                    except Exception:
                        pytest.fail("API error should be caught internally")
