"""Unit tests for cli/commands/auth.py."""

import base64
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest


class TestGenerateKey:
    def test_key_starts_with_udr(self):
        from backend.cli.commands.auth import _generate_key

        key = _generate_key()
        assert key.startswith("udr_")
        assert len(key) > 40

    def test_keys_are_unique(self):
        from backend.cli.commands.auth import _generate_key

        keys = {_generate_key() for _ in range(100)}
        assert len(keys) == 100


class TestGetDb:
    def test_returns_db_session(self):
        from backend.cli.commands.auth import _get_db

        with patch("backend.database.models.db_session") as mock_session:
            mock_session.return_value.__enter__.return_value = MagicMock()
            result = _get_db()
            assert result is not None


class TestCmdAuth:
    def test_create_action_calls_generate(self):
        args = MagicMock()
        args.auth_action = "create"
        args.name = "test-key"
        args.role = "read-only"
        args.description = "test"

        with patch("backend.cli.commands.auth._generate_key", return_value="udr_fake_key"):
            with patch("backend.database.models.APIKey"):
                with patch("backend.cli.commands.auth._get_db") as mock_get_db:
                    mock_session = MagicMock()
                    mock_get_db.return_value.__enter__.return_value = mock_session
                    from backend.cli.commands.auth import cmd_auth

                    result = cmd_auth(args)

        assert result is None or result == 0

    def test_unknown_action_returns_error(self):
        args = MagicMock()
        args.auth_action = "unknown"
        from backend.cli.commands.auth import cmd_auth

        result = cmd_auth(args)
        assert result == 1

    def test_list_action_prints_table(self):
        args = MagicMock()
        args.auth_action = "list"

        with patch("backend.database.models.APIKey"):
            with patch("backend.cli.commands.auth._get_db") as mock_get_db:
                mock_session = MagicMock()
                mock_session.query.return_value.order_by.return_value.all.return_value = []
                mock_get_db.return_value.__enter__.return_value = mock_session
                from backend.cli.commands.auth import cmd_auth

                result = cmd_auth(args)

        assert result is None or result == 0

    def test_revoke_action(self):
        args = MagicMock()
        args.auth_action = "revoke"
        args.key_id = 1

        with patch("backend.database.models.APIKey"):
            with patch("backend.cli.commands.auth._get_db") as mock_get_db:
                mock_session = MagicMock()
                mock_db_key = MagicMock()
                mock_session.query.return_value.filter.return_value.first.return_value = mock_db_key
                mock_get_db.return_value.__enter__.return_value = mock_session
                from backend.cli.commands.auth import cmd_auth

                result = cmd_auth(args)

        assert mock_db_key.is_active is False
        assert result is None or result == 0

    def test_revoke_nonexistent_key(self):
        args = MagicMock()
        args.auth_action = "revoke"
        args.key_id = 999

        with patch("backend.database.models.APIKey"):
            with patch("backend.cli.commands.auth._get_db") as mock_get_db:
                mock_session = MagicMock()
                mock_session.query.return_value.filter.return_value.first.return_value = None
                mock_get_db.return_value.__enter__.return_value = mock_session
                from backend.cli.commands.auth import cmd_auth

                result = cmd_auth(args)

        assert result == 1


class TestSigningKeyGeneration:
    def test_generate_signing_key_returns_private_and_public(self):
        from backend.cli.commands.auth import _generate_signing_key

        priv, pub_bytes = _generate_signing_key()
        assert priv is not None
        assert len(pub_bytes) == 32

    def test_generate_signing_key_unique(self):
        from backend.cli.commands.auth import _generate_signing_key

        pub_keys = {_generate_signing_key()[1] for _ in range(5)}
        assert len(pub_keys) == 5

    def test_save_signing_key_creates_files(self, tmp_path):
        from backend.cli.commands.auth import _generate_signing_key, _save_signing_key

        priv, pub_bytes = _generate_signing_key()
        sign_dir = tmp_path / ".config" / "udr"
        with patch("backend.cli.commands.auth._SIGNING_DIR", sign_dir):
            _save_signing_key(priv)

        assert (sign_dir / "signing.key").is_file()
        assert (sign_dir / "signing.pub").is_file()
        key_bytes = (sign_dir / "signing.key").read_bytes()
        assert b"PRIVATE KEY" in key_bytes
        stored_pub_b64 = (sign_dir / "signing.pub").read_text().strip()
        stored_pub = base64.b64decode(stored_pub_b64)
        assert stored_pub == pub_bytes

    def test_save_signing_key_sets_permissions(self, tmp_path):
        from backend.cli.commands.auth import _generate_signing_key, _save_signing_key

        priv, _ = _generate_signing_key()
        sign_dir = tmp_path / ".config" / "udr"
        with patch("backend.cli.commands.auth._SIGNING_DIR", sign_dir):
            _save_signing_key(priv)

        key_mode = (sign_dir / "signing.key").stat().st_mode
        pub_mode = (sign_dir / "signing.pub").stat().st_mode
        assert oct(key_mode & 0o777) == oct(0o600)
        assert oct(pub_mode & 0o777) == oct(0o644)


class TestLoadSigningKey:
    def test_load_nonexistent_returns_none(self, tmp_path):
        from backend.cli.commands.auth import _load_signing_key

        sign_dir = tmp_path / ".config" / "udr"
        with patch("backend.cli.commands.auth._SIGNING_DIR", sign_dir):
            result = _load_signing_key()
            assert result is None

    def test_load_existing_key_returns_private_and_public(self, tmp_path):
        from backend.cli.commands.auth import (
            _generate_signing_key,
            _load_signing_key,
            _save_signing_key,
        )

        priv, pub_bytes = _generate_signing_key()
        sign_dir = tmp_path / ".config" / "udr"
        with patch("backend.cli.commands.auth._SIGNING_DIR", sign_dir):
            _save_signing_key(priv)
            loaded = _load_signing_key()

        assert loaded is not None
        loaded_priv, loaded_pub = loaded
        assert loaded_pub == pub_bytes


class TestComputeFingerprint:
    def test_fingerprint_returns_16_hex_chars(self):
        from backend.cli.commands.auth import _compute_fingerprint

        fp = _compute_fingerprint(b"x" * 32)
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)

    def test_fingerprint_deterministic(self):
        from backend.cli.commands.auth import _compute_fingerprint

        data = b"test_public_key_bytes_1234567890abcdef"
        assert _compute_fingerprint(data) == _compute_fingerprint(data)

    def test_fingerprint_different_for_different_keys(self):
        from backend.cli.commands.auth import _compute_fingerprint

        assert _compute_fingerprint(b"a" * 32) != _compute_fingerprint(b"b" * 32)


class TestCmdGenKey:
    def test_cmd_gen_key_success(self):
        from backend.cli.commands.auth import cmd_gen_key

        args = MagicMock()
        with patch("backend.cli.commands.auth._generate_signing_key") as mock_gen:
            mock_gen.return_value = (MagicMock(), b"x" * 32)
            with patch("backend.cli.commands.auth._save_signing_key") as mock_save:
                result = cmd_gen_key(args)
                assert result == 0
                mock_save.assert_called_once()


class TestCmdShowKey:
    def test_show_key_no_key_returns_1(self):
        from backend.cli.commands.auth import cmd_show_key

        args = MagicMock()
        with patch("backend.cli.commands.auth._load_signing_key", return_value=None):
            result = cmd_show_key(args)
            assert result == 1

    def test_show_key_with_key_returns_0(self):
        from backend.cli.commands.auth import cmd_show_key

        args = MagicMock()
        with patch("backend.cli.commands.auth._load_signing_key") as mock_load:
            mock_load.return_value = (MagicMock(), b"x" * 32)
            result = cmd_show_key(args)
            assert result == 0


class TestCmdAuthSigning:
    def test_auth_gen_key_dispatches(self):
        args = MagicMock()
        args.auth_action = "gen-key"
        with patch("backend.cli.commands.auth.cmd_gen_key", return_value=0):
            from backend.cli.commands.auth import cmd_auth

            result = cmd_auth(args)
            assert result == 0

    def test_auth_show_key_dispatches(self):
        args = MagicMock()
        args.auth_action = "show-key"
        with patch("backend.cli.commands.auth.cmd_show_key", return_value=0):
            from backend.cli.commands.auth import cmd_auth

            result = cmd_auth(args)
            assert result == 0
