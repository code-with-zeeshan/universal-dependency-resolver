"""Unit tests for cli/commands/verify.py."""

import base64
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import pytest


class TestCmdVerify:
    @pytest.mark.asyncio
    async def test_empty_lock_file(self):
        args = MagicMock()
        args.lock_file = "/tmp/nonexistent/udr.lock"
        args.json = False

        with patch("backend.cli.commands.verify._read_lock_file", return_value={"packages": {}}):
            with patch("pathlib.Path.is_file", return_value=True):
                from backend.cli.commands.verify import _cmd_verify_async

                result = await _cmd_verify_async(args)
                assert result == 0

    @pytest.mark.asyncio
    async def test_verify_all_packages_ok(self):
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = False

        mock_data = {
            "packages": {
                "requests": {"ecosystem": "pypi", "resolved_version": "2.31.0"},
                "flask": {"ecosystem": "pypi", "resolved_version": "2.3.3"},
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.core.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.get_package_info = AsyncMock(
                        side_effect=[
                            {"versions": {"pypi": [{"version": "2.31.0"}]}},
                            {"versions": {"pypi": [{"version": "2.3.3"}]}},
                        ]
                    )
                    mock_agg.close = AsyncMock()
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.verify import _cmd_verify_async

                    result = await _cmd_verify_async(args)
                    assert result == 0

    @pytest.mark.asyncio
    async def test_verify_version_not_found(self):
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = False

        mock_data = {
            "packages": {
                "gone": {"ecosystem": "pypi", "resolved_version": "999.0.0"},
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.core.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.get_package_info = AsyncMock(
                        return_value={"versions": {"pypi": [{"version": "1.0.0"}]}}
                    )
                    mock_agg.close = AsyncMock()
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.verify import _cmd_verify_async

                    result = await _cmd_verify_async(args)
                    assert result == 1

    @pytest.mark.asyncio
    async def test_verify_package_not_found(self):
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = False

        mock_data = {
            "packages": {
                "missing": {"ecosystem": "pypi", "resolved_version": "1.0.0"},
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.core.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.get_package_info = AsyncMock(return_value=None)
                    mock_agg.close = AsyncMock()
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.verify import _cmd_verify_async

                    result = await _cmd_verify_async(args)
                    assert result == 1

    @pytest.mark.asyncio
    async def test_verify_with_missing_version_field(self):
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = False

        mock_data = {
            "packages": {
                "noversion": {"ecosystem": "pypi"},
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.core.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.close = AsyncMock()
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.verify import _cmd_verify_async

                    result = await _cmd_verify_async(args)
                    assert result is None or result == 0

    @pytest.mark.asyncio
    async def test_verify_json_output(self):
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = True

        mock_data = {
            "packages": {
                "requests": {"ecosystem": "pypi", "resolved_version": "2.31.0"},
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.core.DataAggregator") as mock_agg_cls:
                    mock_agg = MagicMock()
                    mock_agg.get_package_info = AsyncMock(
                        return_value={"versions": {"pypi": [{"version": "2.31.0"}]}}
                    )
                    mock_agg.close = AsyncMock()
                    mock_agg_cls.return_value = mock_agg

                    from backend.cli.commands.verify import _cmd_verify_async

                    result = await _cmd_verify_async(args)
                    assert result == 0

    @pytest.mark.asyncio
    async def test_verify_integrity_match(self):
        """Integrity check passes when stored hash matches registry."""
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = False

        mock_data = {
            "packages": {
                "requests": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.31.0",
                    "integrity": {"algorithm": "sha256", "hash": "abc123"},
                },
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.cli.commands.verify._pin_integrity", True):
                    with patch("backend.core.DataAggregator") as mock_agg_cls:
                        mock_agg = MagicMock()
                        mock_agg.get_package_info = AsyncMock(
                            return_value={"versions": {"pypi": [{"version": "2.31.0"}]}}
                        )
                        mock_agg.get_artifact_hash = AsyncMock(
                            return_value={"algorithm": "sha256", "hash": "abc123"}
                        )
                        mock_agg.close = AsyncMock()
                        mock_agg_cls.return_value = mock_agg

                        from backend.cli.commands.verify import _cmd_verify_async

                        result = await _cmd_verify_async(args)
                        assert result == 0

    @pytest.mark.asyncio
    async def test_verify_integrity_mismatch(self):
        """Integrity check fails when stored hash differs from registry."""
        args = MagicMock()
        args.lock_file = "/tmp/udr.lock"
        args.json = False

        mock_data = {
            "packages": {
                "requests": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.31.0",
                    "integrity": {"algorithm": "sha256", "hash": "stored_hash"},
                },
            }
        }

        with patch("backend.cli.commands.verify._read_lock_file", return_value=mock_data):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("backend.cli.commands.verify._pin_integrity", True):
                    with patch("backend.core.DataAggregator") as mock_agg_cls:
                        mock_agg = MagicMock()
                        mock_agg.get_package_info = AsyncMock(
                            return_value={"versions": {"pypi": [{"version": "2.31.0"}]}}
                        )
                        mock_agg.get_artifact_hash = AsyncMock(
                            return_value={"algorithm": "sha256", "hash": "registry_hash"}
                        )
                        mock_agg.close = AsyncMock()
                        mock_agg_cls.return_value = mock_agg

                        from backend.cli.commands.verify import _cmd_verify_async

                        result = await _cmd_verify_async(args)
                        assert result == 1


class TestVerifySignature:
    def test_no_signature_field(self):
        from backend.cli.commands.verify import _verify_signature

        passed, msg = _verify_signature({})
        assert passed is False
        assert "No signature" in msg

    def test_unsupported_algorithm(self):
        from backend.cli.commands.verify import _verify_signature

        lock_data = {"signature": {"algorithm": "rsa", "value": ""}}
        passed, msg = _verify_signature(lock_data)
        assert passed is False
        assert "Unsupported" in msg

    def test_valid_ed25519_signature(self, tmp_path):
        from cryptography.hazmat.primitives.asymmetric import ed25519

        from backend.cli.commands.verify import _verify_signature

        private_key = ed25519.Ed25519PrivateKey.generate()
        pub_bytes = private_key.public_key().public_bytes_raw()

        lock_data = {"version": "2.1", "packages": {"foo": {"version": "1.0.0"}}}
        canonical = json.dumps(
            {k: v for k, v in sorted(lock_data.items()) if k not in {"signature", "provenance"}},
            sort_keys=True,
            default=str,
            ensure_ascii=False,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).digest()
        sig_value = private_key.sign(digest)

        lock_data["signature"] = {
            "algorithm": "ed25519",
            "value": base64.b64encode(sig_value).decode(),
            "public_key": base64.b64encode(pub_bytes).decode(),
        }

        stored_pub_dir = tmp_path / ".config" / "udr"
        stored_pub_dir.mkdir(parents=True, exist_ok=True)
        stored_pub_file = stored_pub_dir / "signing.pub"
        stored_pub_file.write_text(base64.b64encode(pub_bytes).decode() + "\n")

        with patch("pathlib.Path.home", return_value=tmp_path):
            passed, msg = _verify_signature(lock_data)
            assert passed is True
            assert "verified" in msg

    def test_tampered_lock_data_fails(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519

        from backend.cli.commands.verify import _verify_signature

        private_key = ed25519.Ed25519PrivateKey.generate()
        pub_bytes = private_key.public_key().public_bytes_raw()

        lock_data = {"version": "2.1", "packages": {"foo": {"version": "1.0.0"}}}
        canonical = json.dumps(
            {k: v for k, v in sorted(lock_data.items()) if k not in {"signature", "provenance"}},
            sort_keys=True,
            default=str,
            ensure_ascii=False,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).digest()
        sig_value = private_key.sign(digest)

        lock_data["signature"] = {
            "algorithm": "ed25519",
            "value": base64.b64encode(sig_value).decode(),
            "public_key": base64.b64encode(pub_bytes).decode(),
        }

        lock_data["packages"]["foo"]["version"] = "2.0.0"

        with patch("pathlib.Path.is_file", return_value=False):
            passed, msg = _verify_signature(lock_data)
            assert passed is False
            assert "does not match" in msg

    def test_different_public_key_shows_warning(self, tmp_path):
        from cryptography.hazmat.primitives.asymmetric import ed25519

        from backend.cli.commands.verify import _verify_signature

        sign_key = ed25519.Ed25519PrivateKey.generate()
        pub_bytes = sign_key.public_key().public_bytes_raw()

        lock_data = {"version": "2.1", "packages": {"foo": {"version": "1.0.0"}}}
        canonical = json.dumps(
            {k: v for k, v in sorted(lock_data.items()) if k not in {"signature", "provenance"}},
            sort_keys=True,
            default=str,
            ensure_ascii=False,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).digest()
        sig_value = sign_key.sign(digest)

        lock_data["signature"] = {
            "algorithm": "ed25519",
            "value": base64.b64encode(sig_value).decode(),
            "public_key": base64.b64encode(pub_bytes).decode(),
        }

        different_key = ed25519.Ed25519PrivateKey.generate()
        different_pub = different_key.public_key().public_bytes_raw()

        stored_pub_dir = tmp_path / ".config" / "udr"
        stored_pub_dir.mkdir(parents=True, exist_ok=True)
        stored_pub_file = stored_pub_dir / "signing.pub"
        stored_pub_file.write_text(base64.b64encode(different_pub).decode() + "\n")

        with patch("pathlib.Path.home", return_value=tmp_path):
            passed, msg = _verify_signature(lock_data)
            assert passed is True
            assert "key rotation" in msg
