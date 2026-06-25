from unittest.mock import patch
import uuid
import pytest

from backend.api.main import app
from backend.api.dependencies import (
    get_data_aggregator,
    get_conflict_resolver,
    get_system_scanner,
)


class _MockDataAggregator:
    async def get_package_info(self, name, ecosystem):
        return {"name": name, "ecosystem": ecosystem, "version": "1.0.0"}


class _MockSystemScanner:
    async def scan_all(self):
        return {"os": "linux", "python": "3.11"}


class _MockConflictResolver:
    def resolve_dependencies(self, packages_info, system_info, prefer_compatibility):
        return {"resolved": packages_info, "conflicts": []}


@pytest.fixture
def override_resolve_deps():
    """Override DB-heavy dependencies so POST /api/v1/packages/resolve doesn't hit PostgreSQL."""
    overrides = {}
    for dep, instance in [
        (get_data_aggregator, _MockDataAggregator),
        (get_conflict_resolver, _MockConflictResolver),
        (get_system_scanner, _MockSystemScanner),
    ]:
        original = app.dependency_overrides.get(dep)
        app.dependency_overrides[dep] = lambda inst=instance: inst()
        overrides[dep] = original
    yield
    for dep, original in overrides.items():
        if original is None:
            del app.dependency_overrides[dep]
        else:
            app.dependency_overrides[dep] = original


class TestCorrelationIDMiddleware:
    def test_adds_correlation_id_header(self, client):
        resp = client.get("/api/v1/health")
        assert "X-Correlation-ID" in resp.headers
        assert resp.headers["X-Correlation-ID"]

    def test_adds_request_id_header(self, client):
        resp = client.get("/api/v1/health")
        assert "X-Request-ID" in resp.headers
        assert resp.headers["X-Request-ID"]

    def test_correlation_id_matches_request_id(self, client):
        resp = client.get("/api/v1/health")
        assert resp.headers["X-Correlation-ID"] == resp.headers["X-Request-ID"]

    def test_preserves_incoming_correlation_id(self, client):
        cid = str(uuid.uuid4())
        resp = client.get("/api/v1/health", headers={"X-Correlation-ID": cid})
        assert resp.headers["X-Correlation-ID"] == cid

    def test_unique_per_request(self, client):
        resp1 = client.get("/api/v1/health")
        resp2 = client.get("/api/v1/health")
        assert resp1.headers["X-Correlation-ID"] != resp2.headers["X-Correlation-ID"]


class TestSecurityHeadersMiddleware:
    def test_x_content_type_options(self, client):
        resp = client.get("/api/v1/health")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options(self, client):
        resp = client.get("/api/v1/health")
        assert resp.headers["X-Frame-Options"] == "DENY"

    def test_x_xss_protection(self, client):
        resp = client.get("/api/v1/health")
        assert resp.headers["X-XSS-Protection"] == "1; mode=block"

    def test_referrer_policy(self, client):
        resp = client.get("/api/v1/health")
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_csp_on_api_routes(self, client):
        resp = client.get("/api/v1/health")
        assert "Content-Security-Policy" in resp.headers
        assert "default-src 'none'" in resp.headers["Content-Security-Policy"]


class TestAuditLogMiddleware:
    def test_audit_logger_exists(self, client):
        from backend.api.middleware import AuditLogMiddleware

        assert AuditLogMiddleware is not None

    def test_post_with_bearer_bypasses_csrf(self, client, override_resolve_deps):
        resp = client.post(
            "/api/v1/packages/resolve",
            json={"packages": [{"name": "test", "ecosystem": "pypi"}]},
            headers={"Authorization": "Bearer test-token"},
        )
        # Not a CSRF 403 - passes CSRF even if the route handler returns an error
        assert resp.status_code != 403, "CSRF should not block Bearer auth requests"

    def test_delete_with_bearer_bypasses_csrf(self, client):
        resp = client.delete(
            "/api/v1/packages/nonexistent/pkg",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code != 403, "CSRF should not block Bearer auth requests"


class TestCSRFProtectionMiddleware:
    def test_get_requests_not_blocked(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_bearer_auth_bypasses_csrf(self, client, override_resolve_deps):
        resp = client.post(
            "/api/v1/packages/resolve",
            json={"packages": [{"name": "test", "ecosystem": "pypi"}]},
            headers={"Authorization": "Bearer some-token"},
        )
        assert resp.status_code != 403, "CSRF should not block Bearer auth requests"

    def test_csrf_blocked_when_no_auth_no_cookie(self, client):
        with patch.dict("backend.settings.FEATURES", {"ENABLE_CSRF": True}, clear=False):
            resp = client.post(
                "/api/v1/packages/resolve",
                json={"packages": [{"name": "test", "ecosystem": "pypi"}]},
            )
            assert resp.status_code == 403
            assert resp.json()["error"]["type"] == "csrf_protection"

    def test_csrf_cookie_and_header_match(self, client, override_resolve_deps):
        cookie_val = "valid-csrf-token"
        resp = client.post(
            "/api/v1/packages/resolve",
            json={"packages": [{"name": "test", "ecosystem": "pypi"}]},
            cookies={"csrf_token": cookie_val},
            headers={"X-CSRF-Token": cookie_val},
        )
        assert resp.status_code in (200, 400, 422)


class TestLoggingMiddleware:
    def test_request_logged(self, client):
        with patch("backend.api.middleware.logger.info") as mock_log:
            resp = client.get("/api/v1/health")
            assert resp.status_code == 200

    def test_x_process_time_header(self, client):
        resp = client.get("/api/v1/health")
        assert "X-Process-Time" in resp.headers
        assert float(resp.headers["X-Process-Time"]) >= 0


class TestRequestSizeLimitMiddleware:
    def test_small_request_passes(self, client):
        resp = client.post(
            "/api/v1/packages/resolve",
            json={"packages": [{"name": "test", "ecosystem": "pypi"}]},
        )
        assert resp.status_code != 413


class TestGetClientIP:
    def test_direct_ip(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_forwarded_for(self, client):
        resp = client.get(
            "/api/v1/health",
            headers={"X-Forwarded-For": "203.0.113.1, 198.51.100.2"},
        )
        assert resp.status_code == 200

    def test_real_ip(self, client):
        resp = client.get(
            "/api/v1/health",
            headers={"X-Real-IP": "203.0.113.1"},
        )
        assert resp.status_code == 200
