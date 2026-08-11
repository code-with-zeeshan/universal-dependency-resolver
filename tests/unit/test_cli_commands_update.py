import pytest

from backend.cli.commands.update import _extract_fixed_version


class TestExtractFixedVersion:
    def test_no_affected(self):
        assert _extract_fixed_version({}) is None

    def test_no_ranges(self):
        vuln = {"affected": [{"ranges": []}]}
        assert _extract_fixed_version(vuln) is None

    def test_no_ecosystem_range(self):
        vuln = {"affected": [{"ranges": [{"type": "GIT", "events": [{"fixed": "abc123"}]}]}]}
        assert _extract_fixed_version(vuln) is None

    def test_ecosystem_with_fixed(self):
        vuln = {
            "affected": [
                {
                    "ranges": [
                        {
                            "type": "ECOSYSTEM",
                            "events": [{"introduced": "0"}, {"fixed": "1.2.3"}],
                        }
                    ]
                }
            ]
        }
        assert _extract_fixed_version(vuln) == "1.2.3"

    def test_multiple_affected_first_wins(self):
        vuln = {
            "affected": [
                {
                    "ranges": [
                        {
                            "type": "ECOSYSTEM",
                            "events": [{"introduced": "0"}, {"fixed": "2.0.0"}],
                        }
                    ]
                },
                {
                    "ranges": [
                        {
                            "type": "ECOSYSTEM",
                            "events": [{"fixed": "3.0.0"}],
                        }
                    ]
                },
            ]
        }
        assert _extract_fixed_version(vuln) == "2.0.0"

    def test_multiple_events_skips_non_fixed(self):
        vuln = {
            "affected": [
                {
                    "ranges": [
                        {
                            "type": "ECOSYSTEM",
                            "events": [
                                {"introduced": "0"},
                                {"last_affected": "1.0.0"},
                                {"fixed": "1.1.0"},
                            ],
                        }
                    ]
                }
            ]
        }
        assert _extract_fixed_version(vuln) == "1.1.0"


class TestUpdateAllGuard:
    def test_all_conflicts_with_package_exits_1(self):
        from unittest.mock import MagicMock, patch

        args = MagicMock()
        args.fix_cve = False
        args.all = True
        args.package = "flask"
        with pytest.raises(SystemExit) as excinfo:
            with patch("backend.cli.commands.update.asyncio.run") as mock_run:
                from backend.cli.commands.update import cmd_update

                cmd_update(args)
        assert excinfo.value.code == 1
        mock_run.assert_not_called()

    def test_all_dispatches_update_all(self):
        from unittest.mock import MagicMock, patch

        args = MagicMock()
        args.fix_cve = False
        args.all = True
        args.package = None
        with patch("backend.cli.commands.update._update_all", return_value=MagicMock()) as mock_all:
            mock_all.return_value = 0
            with patch("backend.cli.commands.update.asyncio.run", return_value=0) as mock_run:
                with pytest.raises(SystemExit) as excinfo:
                    from backend.cli.commands.update import cmd_update

                    cmd_update(args)
        assert excinfo.value.code == 0
        mock_run.assert_called_once()
