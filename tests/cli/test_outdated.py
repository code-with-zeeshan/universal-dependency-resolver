"""Tests for udr outdated command."""

from .test_commands import _run


class TestOutdatedHelp:
    def test_help_exit_code(self):
        result = _run("outdated", "--help")
        assert result.returncode == 0

    def test_help_shows_usage(self):
        result = _run("outdated", "--help")
        assert "usage: udr outdated" in result.stdout.lower() or "usage: udr outdated" in result.stderr.lower()
