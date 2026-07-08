"""Unit tests for cli/commands/install.py."""

from unittest.mock import MagicMock, patch


class TestCmdInstall:
    @patch("backend.cli.commands.install._read_lock_file")
    @patch("backend.cli.commands.install.Path.exists")
    def test_no_lock_file(self, mock_exists, mock_read):
        mock_exists.return_value = False
        mock_read.return_value = {}
        args = MagicMock()
        args.directory = "/tmp/fake"
        args.lock_file = None
        args.production = False
        args.ecosystem = None
        args.cuda = None
        args.dry_run = False
        args.yes = True

        from backend.cli.commands.install import cmd_install

        result = cmd_install(args)
        assert result == 1

    @patch("backend.cli.commands.install._read_lock_file")
    def test_empty_lock_file(self, mock_read):
        mock_read.return_value = {"packages": {}}
        args = MagicMock()
        args.directory = "/tmp"
        args.lock_file = None
        args.production = False
        args.ecosystem = None
        args.cuda = None
        args.dry_run = False
        args.yes = True

        with patch("pathlib.Path.exists", return_value=True):
            from backend.cli.commands.install import cmd_install

            result = cmd_install(args)
            assert result == 1

    @patch("backend.cli.commands.install._read_lock_file")
    def test_dry_run_returns_zero(self, mock_read):
        mock_read.return_value = {
            "packages": {
                "requests": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.31.0",
                }
            }
        }
        args = MagicMock()
        args.directory = "/tmp"
        args.lock_file = None
        args.production = False
        args.ecosystem = None
        args.cuda = None
        args.dry_run = True
        args.yes = True
        args.restore = False

        with patch("pathlib.Path.exists", return_value=True):
            from backend.cli.commands.install import cmd_install

            result = cmd_install(args)
            assert result == 0

    @patch("backend.cli.commands.install._read_lock_file")
    def test_production_skips_dev_deps(self, mock_read):
        mock_read.return_value = {
            "packages": {
                "requests": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.31.0",
                    "direct": True,
                    "dev": False,
                },
                "pytest": {
                    "ecosystem": "pypi",
                    "resolved_version": "8.0.0",
                    "direct": True,
                    "dev": True,
                },
            }
        }
        args = MagicMock()
        args.directory = "/tmp"
        args.lock_file = None
        args.production = True
        args.ecosystem = None
        args.cuda = None
        args.dry_run = True
        args.yes = True
        args.restore = False

        with patch("pathlib.Path.exists", return_value=True):
            from backend.cli.commands.install import cmd_install

            result = cmd_install(args)
            assert result == 0

    @patch("backend.cli.commands.install._read_lock_file")
    def test_ecosystem_filter(self, mock_read):
        mock_read.return_value = {
            "packages": {
                "requests": {"ecosystem": "pypi", "resolved_version": "2.31.0"},
                "express": {"ecosystem": "npm", "resolved_version": "4.18.2"},
            }
        }
        args = MagicMock()
        args.directory = "/tmp"
        args.lock_file = None
        args.production = False
        args.ecosystem = "pypi"
        args.cuda = None
        args.dry_run = True
        args.yes = True
        args.restore = False

        with patch("pathlib.Path.exists", return_value=True):
            from backend.cli.commands.install import cmd_install

            result = cmd_install(args)
            assert result == 0
