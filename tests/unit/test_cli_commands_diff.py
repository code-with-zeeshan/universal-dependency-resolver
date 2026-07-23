from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.cli.commands.diff import _read_lock


class TestReadLock:
    @patch("backend.cli.commands.diff.Path.is_file", return_value=True)
    @patch(
        "backend.cli.commands.diff.Path.read_text",
        return_value='{"version": "2.1", "packages": {}}',
    )
    def test_valid_lock_v2_1(self, mock_read, mock_isfile):
        result = _read_lock("test.lock")
        assert result["version"] == "2.1"
        assert result["packages"] == {}

    @patch("backend.cli.commands.diff.Path.is_file", return_value=True)
    @patch(
        "backend.cli.commands.diff.Path.read_text",
        return_value='{"version": "1.0", "packages": {}}',
    )
    def test_valid_lock_v1_0(self, mock_read, mock_isfile):
        result = _read_lock("test.lock")
        assert result["version"] == "1.0"

    @patch("backend.cli.commands.diff.Path.is_file", return_value=True)
    @patch(
        "backend.cli.commands.diff.Path.read_text",
        return_value='{"version": "3.0", "packages": {}}',
    )
    def test_unsupported_version(self, mock_read, mock_isfile):
        with pytest.raises(SystemExit):
            _read_lock("test.lock")

    @patch("backend.cli.commands.diff.Path.is_file", return_value=True)
    @patch(
        "backend.cli.commands.diff.Path.read_text",
        return_value="not json",
    )
    def test_invalid_json(self, mock_read, mock_isfile):
        with pytest.raises(SystemExit):
            _read_lock("test.lock")

    @patch("backend.cli.commands.diff.Path.is_file", return_value=False)
    def test_file_not_found(self, mock_isfile):
        with pytest.raises(SystemExit):
            _read_lock("nonexistent.lock")
