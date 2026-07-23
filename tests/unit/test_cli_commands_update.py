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
