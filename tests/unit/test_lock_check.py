"""Unit tests for udr lock --check (lock drift detection)."""

import base64
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestAddSigningAndProvenance:
    """Test the _add_signing_and_provenance function."""

    def test_no_sign_no_provenance_unchanged(self):
        from backend.cli.commands.lock import _add_signing_and_provenance

        lock_data = {"version": "2.1", "packages": {}}
        args = MagicMock()
        args.sign = False
        args.provenance = False
        result = _add_signing_and_provenance(lock_data, args, MagicMock(), [], {}, {})
        assert result == lock_data
        assert "signature" not in result
        assert "provenance" not in result

    def test_provenance_adds_section(self):
        from backend.cli.commands.lock import _add_signing_and_provenance

        lock_data = {"version": "2.1", "packages": {"foo": {}}}
        args = MagicMock()
        args.sign = False
        args.provenance = True
        manifests = [{"filename": "requirements.txt"}]
        result = _add_signing_and_provenance(lock_data, args, MagicMock(), manifests, {}, {})
        assert "provenance" in result
        assert result["provenance"]["builder"]["id"] == "universal-dependency-resolver"
        assert result["provenance"]["buildType"] == "https://opencode.ai/udr/lock/v1"
        assert result["provenance"]["buildConfig"]["package_count"] == 1
        assert len(result["provenance"]["materials"]) == 1

    def test_provenance_target_and_workspace(self):
        from backend.cli.commands.lock import _add_signing_and_provenance

        lock_data = {
            "version": "2.1",
            "packages": {},
            "target": {"os": "linux", "arch": "aarch64"},
            "workspace": "backend",
        }
        args = MagicMock()
        args.sign = False
        args.provenance = True
        result = _add_signing_and_provenance(lock_data, args, MagicMock(), [], {}, {})
        assert result["provenance"]["buildConfig"]["target"] == {"os": "linux", "arch": "aarch64"}
        assert result["provenance"]["buildConfig"]["workspace"] == "backend"

    def test_sign_adds_ed25519_signature(self, tmp_path):
        from backend.cli.commands.lock import _add_signing_and_provenance

        lock_data = {"version": "2.1", "packages": {"foo": {"version": "1.0.0"}}}
        args = MagicMock()
        args.sign = True
        args.provenance = False

        config_dir = tmp_path / ".config" / "udr"
        config_dir.mkdir(parents=True, exist_ok=True)

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _add_signing_and_provenance(lock_data, args, MagicMock(), [], {}, {})

        assert "signature" in result
        sig = result["signature"]
        assert sig["algorithm"] == "ed25519"
        assert "value" in sig
        assert "public_key" in sig
        assert len(base64.b64decode(sig["public_key"])) == 32

    def test_sign_verifies_with_generated_key(self, tmp_path):
        from backend.cli.commands.lock import _add_signing_and_provenance

        lock_data = {"version": "2.1", "packages": {"foo": {"version": "1.0.0"}}}
        args = MagicMock()
        args.sign = True
        args.provenance = False

        config_dir = tmp_path / ".config" / "udr"
        config_dir.mkdir(parents=True, exist_ok=True)

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _add_signing_and_provenance(lock_data, args, MagicMock(), [], {}, {})

        from cryptography.hazmat.primitives.asymmetric import ed25519

        sig = result["signature"]
        pub_bytes = base64.b64decode(sig["public_key"])
        sig_bytes = base64.b64decode(sig["value"])
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)

        exclude_keys = {"signature", "provenance"}
        canonical = json.dumps(
            {k: v for k, v in sorted(result.items()) if k not in exclude_keys},
            sort_keys=True,
            default=str,
            ensure_ascii=False,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).digest()

        public_key.verify(sig_bytes, digest)

    def test_sign_and_provenance_together(self, tmp_path):
        from backend.cli.commands.lock import _add_signing_and_provenance

        lock_data = {"version": "2.1", "packages": {"foo": {}}}
        args = MagicMock()
        args.sign = True
        args.provenance = True

        config_dir = tmp_path / ".config" / "udr"
        config_dir.mkdir(parents=True, exist_ok=True)

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _add_signing_and_provenance(
                lock_data, args, MagicMock(), [{"filename": "req.txt"}], {}, {}
            )

        assert "signature" in result
        assert "provenance" in result
        assert result["provenance"]["buildConfig"]["package_count"] == 1
        assert len(result["provenance"]["materials"]) == 1


class TestCrossCompileIntegration:
    """Integration tests verifying target info flows through lock data assembly."""

    def test_no_target_when_not_cross_compiling(self):
        """_build_lock_data omits target when system_info has no target key."""
        from backend.cli.commands.lock import _build_lock_data

        lock_data = _build_lock_data(
            lock_path=MagicMock(),
            existing_lock={},
            system_info={"platform": {"system": "linux"}},
            manifests=[],
            resolved={"packages": {}, "solver": "sat"},
            resolver_inputs={},
            package_details={},
            packages=[],
            workspace=None,
            args=MagicMock(),
        )
        assert "target" not in lock_data

    def test_target_present_when_cross_compiling_to_linux_aarch64(self):
        """_build_lock_data includes target when system_info has target key."""
        from backend.cli.commands.lock import _build_lock_data

        lock_data = _build_lock_data(
            lock_path=MagicMock(),
            existing_lock={},
            system_info={
                "platform": {"system": "linux"},
                "target": {"os": "linux", "architecture": "aarch64"},
            },
            manifests=[],
            resolved={"packages": {}, "solver": "sat"},
            resolver_inputs={},
            package_details={},
            packages=[],
            workspace=None,
            args=MagicMock(),
        )
        assert lock_data["target"] == {"os": "linux", "architecture": "aarch64"}

    def test_target_with_cuda_in_lock(self):
        """_build_lock_data includes CUDA in target when cross-compiling."""
        from backend.cli.commands.lock import _build_lock_data

        lock_data = _build_lock_data(
            lock_path=MagicMock(),
            existing_lock={},
            system_info={
                "platform": {"system": "linux"},
                "target": {"os": "windows", "architecture": "x86_64", "cuda": "12.1"},
            },
            manifests=[],
            resolved={"packages": {}, "solver": "sat"},
            resolver_inputs={},
            package_details={},
            packages=[],
            workspace=None,
            args=MagicMock(),
        )
        assert lock_data["target"] == {"os": "windows", "architecture": "x86_64", "cuda": "12.1"}

    def test_target_does_not_affect_system_section(self):
        """_build_lock_data preserves host system info, target is separate."""
        from backend.cli.commands.lock import _build_lock_data

        lock_data = _build_lock_data(
            lock_path=MagicMock(),
            existing_lock={},
            system_info={
                "platform": {"system": "Darwin", "release": "23.0.0"},
                "runtime_versions": {"python": {"version": "3.12.0"}},
                "cpu": {"brand": "Apple M3"},
                "target": {"os": "linux", "architecture": "aarch64"},
            },
            manifests=[],
            resolved={"packages": {}, "solver": "sat"},
            resolver_inputs={},
            package_details={},
            packages=[],
            workspace=None,
            args=MagicMock(),
        )
        assert lock_data["system"]["os"] == "Darwin 23.0.0"
        assert lock_data["target"] == {"os": "linux", "architecture": "aarch64"}

    def test_cross_compile_flow_via_scan_and_build_info(self):
        """End-to-end: _scan_system_and_build_info with --target --platform produces target.

        This exercises the full flow from args → _build_target_system_info → system_info["target"].
        """
        from backend.cli.commands.lock import _scan_system_and_build_info

        scanner = MagicMock()
        scanner.scan_all = AsyncMock(return_value={"platform": {"system": "linux"}})

        async def run():
            args = MagicMock()
            args.cuda = None
            args.device = None
            args.target = "linux"
            args.platform = "arm64"
            return await _scan_system_and_build_info(scanner, args)

        import asyncio

        system_info = asyncio.run(run())
        assert "target" in system_info
        assert system_info["target"]["os"] == "linux"
        assert system_info["target"]["architecture"] == "aarch64"
