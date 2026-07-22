"""Tests for backend/api/main.py — Sentry before_send, health check utilities."""

from unittest.mock import MagicMock, patch

import pytest

from backend.api.main import _sentry_before_send


class TestSentryBeforeSend:
    """Tests for the _sentry_before_send callback that strips sensitive fields."""

    def test_strips_request_data(self):
        event = {"request": {"data": {"password": "secret", "token": "abc123"}, "headers": {}}}
        result = _sentry_before_send(event, {})
        assert "data" not in result["request"]

    def test_strips_sensitive_headers(self):
        event = {"request": {"headers": {"authorization": "Bearer token", "cookie": "session=abc", "x-api-key": "key123", "accept": "application/json"}}}
        result = _sentry_before_send(event, {})
        assert "authorization" not in result["request"]["headers"]
        assert "cookie" not in result["request"]["headers"]
        assert "x-api-key" not in result["request"]["headers"]
        assert result["request"]["headers"]["accept"] == "application/json"

    def test_handles_missing_request_key(self):
        event = {"message": "no request data"}
        result = _sentry_before_send(event, {})
        assert result["message"] == "no request data"

    def test_handles_missing_headers(self):
        event = {"request": {"data": {"foo": "bar"}}}
        result = _sentry_before_send(event, {})
        assert "data" not in result["request"]

    def test_handles_empty_event(self):
        result = _sentry_before_send({}, {})
        assert result == {}

    def test_preserves_nonsensitive_fields(self):
        event = {"request": {"data": None, "headers": {"accept": "application/json", "user-agent": "test"}}}
        result = _sentry_before_send(event, {})
        assert result["request"]["headers"]["accept"] == "application/json"
        assert result["request"]["headers"]["user-agent"] == "test"
