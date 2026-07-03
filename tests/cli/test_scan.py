"""Tests for udr scan command."""

from .test_commands import _run


class TestScanHelp:
    def test_help_exit_code(self):
        result = _run("scan", "--help")
        assert result.returncode == 0

    def test_help_shows_usage(self):
        result = _run("scan", "--help")
        assert "usage: udr scan" in result.stdout.lower() or "usage: udr scan" in result.stderr.lower()

    def test_help_shows_subcommands(self):
        result = _run("scan", "--help")
        assert "github" in result.stdout.lower() or "github" in result.stderr.lower()
