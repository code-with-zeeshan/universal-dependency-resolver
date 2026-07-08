"""Tests for udr why command."""

from .test_commands import _run


class TestWhyHelp:
    def test_help_exit_code(self):
        result = _run("why", "--help")
        assert result.returncode == 0

    def test_help_shows_usage(self):
        result = _run("why", "--help")
        assert (
            "usage: udr why" in result.stdout.lower() or "usage: udr why" in result.stderr.lower()
        )
