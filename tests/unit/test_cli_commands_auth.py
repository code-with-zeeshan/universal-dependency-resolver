"""Unit tests for cli/commands/auth.py."""

from unittest.mock import MagicMock, patch


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
