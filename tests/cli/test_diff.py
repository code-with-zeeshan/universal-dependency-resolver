"""Tests for udr diff command."""

from .test_commands import _run


class TestDiffHelp:
    def test_help_exit_code(self):
        result = _run("diff", "--help")
        assert result.returncode == 0

    def test_help_shows_usage(self):
        result = _run("diff", "--help")
        assert (
            "usage: udr diff" in result.stdout.lower() or "usage: udr diff" in result.stderr.lower()
        )


class TestDiffBasic:
    def test_diff_needs_two_files(self):
        result = _run("diff")
        assert result.returncode != 0
        assert (
            "2" in result.stderr
            or "two" in result.stderr.lower()
            or "argument" in result.stderr.lower()
        )
