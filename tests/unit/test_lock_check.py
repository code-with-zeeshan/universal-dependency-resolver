"""Unit tests for udr lock --check (lock drift detection)."""

import json

import pytest


@pytest.fixture
def lock_packages():
    """Fixture for a standard lock packages dict."""
    return {
        "requests": {
            "name": "requests",
            "ecosystem": "pypi",
            "resolved_version": "2.31.0",
            "direct": True,
            "depends_on": {"urllib3": ">=2.0"},
        },
        "urllib3": {
            "name": "urllib3",
            "ecosystem": "pypi",
            "resolved_version": "2.2.0",
            "direct": False,
            "depends_on": {},
        },
        "flask": {
            "name": "flask",
            "ecosystem": "pypi",
            "resolved_version": "2.3.3",
            "direct": True,
            "depends_on": {},
        },
    }


@pytest.fixture
def lock_data(lock_packages):
    return {
        "version": "2.1",
        "generated_at": "2026-07-13T12:00:00",
        "packages": lock_packages,
    }


@pytest.fixture
def tmp_lock_path(tmp_path):
    return tmp_path / "udr.lock"


class TestLockCheckFlag:
    """Test --check flag parsing."""

    def test_lock_check_flag(self):
        from backend.cli import _build_parser

        p = _build_parser()
        args = p.parse_args(["lock", "--check"])
        assert args.command == "lock"
        assert args.check

    def test_lock_check_shorthand(self):
        from backend.cli import _build_parser

        p = _build_parser()
        args = p.parse_args(["lock", "-c"])
        assert args.command == "lock"
        assert args.check

    def test_lock_check_with_other_flags(self):
        from backend.cli import _build_parser

        p = _build_parser()
        args = p.parse_args(["lock", "--check", "--dry-run", "--json"])
        assert args.command == "lock"
        assert args.check
        assert args.dry_run
        assert args.json


class TestRunLockCheck:
    """Test the _run_lock_check comparator function."""

    def test_no_lock_file_exists(self, lock_data, tmp_path):
        from backend.cli.commands.lock import _run_lock_check

        missing = tmp_path / "nonexistent.lock"
        result = _run_lock_check(lock_data, missing)
        assert result == 1

    def test_identical_packages(self, lock_data, tmp_lock_path):
        from backend.cli.commands.lock import _run_lock_check

        tmp_lock_path.write_text(json.dumps(lock_data, indent=2))
        result = _run_lock_check(lock_data, tmp_lock_path)
        assert result == 0

    def test_different_version_detected(self, lock_data, tmp_lock_path):
        from backend.cli.commands.lock import _run_lock_check

        old_data = json.loads(json.dumps(lock_data))
        old_data["packages"]["requests"]["resolved_version"] = "2.28.0"
        tmp_lock_path.write_text(json.dumps(old_data, indent=2))
        result = _run_lock_check(lock_data, tmp_lock_path)
        assert result == 1

    def test_added_package_detected(self, lock_data, tmp_lock_path):
        from backend.cli.commands.lock import _run_lock_check

        old_data = json.loads(json.dumps(lock_data))
        del old_data["packages"]["flask"]
        tmp_lock_path.write_text(json.dumps(old_data, indent=2))
        result = _run_lock_check(lock_data, tmp_lock_path)
        assert result == 1

    def test_removed_package_detected(self, lock_data, tmp_lock_path):
        from backend.cli.commands.lock import _run_lock_check

        new_data = json.loads(json.dumps(lock_data))
        del new_data["packages"]["flask"]
        tmp_lock_path.write_text(json.dumps(lock_data, indent=2))
        result = _run_lock_check(new_data, tmp_lock_path)
        assert result == 1

    def test_direct_flag_change_detected(self, lock_data, tmp_lock_path):
        from backend.cli.commands.lock import _run_lock_check

        old_data = json.loads(json.dumps(lock_data))
        old_data["packages"]["urllib3"]["direct"] = True
        tmp_lock_path.write_text(json.dumps(old_data, indent=2))
        result = _run_lock_check(lock_data, tmp_lock_path)
        assert result == 1

    def test_ignores_generated_at_and_signature(self, lock_data, tmp_lock_path):
        from backend.cli.commands.lock import _run_lock_check

        old_data = json.loads(json.dumps(lock_data))
        old_data["generated_at"] = "2024-01-01T00:00:00"
        old_data["signature"] = {"algorithm": "ed25519", "value": "abc123"}
        old_data["provenance"] = {"builder": {"id": "old"}}
        tmp_lock_path.write_text(json.dumps(old_data, indent=2))
        result = _run_lock_check(lock_data, tmp_lock_path)
        assert result == 0

    def test_empty_existing_lock_file(self, lock_data, tmp_lock_path):
        from backend.cli.commands.lock import _run_lock_check

        tmp_lock_path.write_text(json.dumps({"version": "2.1", "packages": {}}))
        result = _run_lock_check(lock_data, tmp_lock_path)
        assert result == 1

    def test_both_added_and_removed_and_changed(self, lock_data, tmp_lock_path):
        from backend.cli.commands.lock import _run_lock_check

        old_data = json.loads(json.dumps(lock_data))
        old_data["packages"]["requests"]["resolved_version"] = "2.28.0"
        old_data["packages"]["extra_pkg"] = {
            "name": "extra_pkg",
            "ecosystem": "pypi",
            "resolved_version": "1.0.0",
            "direct": False,
            "depends_on": {},
        }
        tmp_lock_path.write_text(json.dumps(old_data, indent=2))
        result = _run_lock_check(lock_data, tmp_lock_path)
        assert result == 1

    def test_unparseable_lock_file(self, lock_data, tmp_lock_path):
        from backend.cli.commands.lock import _run_lock_check

        tmp_lock_path.write_text("not valid json")
        result = _run_lock_check(lock_data, tmp_lock_path)
        assert result == 1
