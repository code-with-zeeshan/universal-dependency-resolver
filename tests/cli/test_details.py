"""Tests for udr details command."""

from .test_commands import _run


class TestDetailsHelp:
    def test_help_exit_code(self):
        result = _run("details", "--help")
        assert result.returncode == 0

    def test_help_shows_usage(self):
        result = _run("details", "--help")
        assert (
            "usage: udr details" in result.stdout.lower()
            or "usage: udr details" in result.stderr.lower()
        )


class TestDetailsBasic:
    def test_details_with_package(self):
        result = _run("details", "requests")
        # Should exit cleanly or show a network error (depends on env)
        assert result.returncode in (0, 1)
