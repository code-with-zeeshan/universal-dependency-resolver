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


class TestDiffFatal:
    def test_fatal_json_emits_error_json_and_exits_1(self, capsys):
        from backend.cli.commands.diff import _fatal

        args = MagicMock()
        args.json = True
        with pytest.raises(SystemExit) as excinfo:
            _fatal(args, "Some error")
        assert excinfo.value.code == 1
        import json as json_mod

        out = capsys.readouterr().out
        assert json_mod.loads(out) == {"error": "Some error"}

    def test_fatal_non_json_no_stdout(self, capsys):
        from backend.cli.commands.diff import _fatal

        args = MagicMock()
        args.json = False
        with pytest.raises(SystemExit) as excinfo:
            _fatal(args, "Some error")
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert out == ""

    @patch("backend.cli.commands.diff.Path.is_file", return_value=False)
    def test_read_lock_missing_with_args_emits_json(self, mock_isfile, capsys):
        from backend.cli.commands.diff import _read_lock

        args = MagicMock()
        args.json = True
        with pytest.raises(SystemExit) as excinfo:
            _read_lock("missing.lock", args)
        assert excinfo.value.code == 1
        import json as json_mod

        out = capsys.readouterr().out
        assert json_mod.loads(out)["error"] == "Lock file not found: missing.lock"
