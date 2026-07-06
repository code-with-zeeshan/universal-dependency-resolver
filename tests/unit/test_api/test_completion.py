"""Tests for GET /api/v1/completion/{shell} endpoint."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    app = pytest.importorskip("backend.api.main").app
    with TestClient(app) as c:
        yield c


class TestCompletionShell:
    """GET /api/v1/completion/{shell}"""

    def test_bash(self, client):
        resp = client.get("/api/v1/completion/bash")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/plain; charset=utf-8"
        assert "complete" in resp.text
        assert "udr" in resp.text

    def test_zsh(self, client):
        resp = client.get("/api/v1/completion/zsh")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/plain; charset=utf-8"
        assert "#compdef" in resp.text

    def test_fish(self, client):
        resp = client.get("/api/v1/completion/fish")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/plain; charset=utf-8"
        assert "complete -c udr" in resp.text or "complete -c " in resp.text

    def test_unsupported_shell(self, client):
        resp = client.get("/api/v1/completion/tcsh")
        assert resp.status_code == 400
        assert "Unsupported shell" in resp.text

    def test_bash_contains_commands(self, client):
        resp = client.get("/api/v1/completion/bash")
        # Should contain common subcommands
        for cmd in ["serve", "check", "resolve", "lock", "index", "auth"]:
            assert cmd in resp.text, f"bash completion missing '{cmd}'"

    def test_zsh_contains_commands(self, client):
        resp = client.get("/api/v1/completion/zsh")
        for cmd in ["serve", "check", "resolve", "lock", "index", "auth"]:
            assert cmd in resp.text, f"zsh completion missing '{cmd}'"

    def test_fish_contains_commands(self, client):
        resp = client.get("/api/v1/completion/fish")
        for cmd in ["serve", "check", "resolve", "lock", "index", "auth"]:
            assert cmd in resp.text, f"fish completion missing '{cmd}'"

    def test_ecosystem_completions_present(self, client):
        resp = client.get("/api/v1/completion/bash")
        for eco in ["pypi", "npm", "crates", "maven"]:
            assert eco in resp.text, f"bash completion missing ecosystem '{eco}'"
