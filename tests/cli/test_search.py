"""Tests for udr search command."""
import pytest

from .test_commands import _run


class TestSearchHelp:
    def test_help_exit_code(self):
        result = _run("search", "--help")
        assert result.returncode == 0

    def test_help_shows_usage(self):
        result = _run("search", "--help")
        assert "usage: udr search" in result.stdout.lower() or "usage: udr search" in result.stderr.lower()
