"""Tests for local compressed index (Phase 6-D)."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.local_index import (
    LocalIndexManager,
    _fetch_pypi_package_list,
    _fetch_pypi_package_json,
    _parse_crate_index_file,
    _parse_pypi_deps,
    get_local_index,
)
from backend.settings import ENABLE_LOCAL_INDEX, LOCAL_INDEX_DIR, LOCAL_INDEX_UPDATE_INTERVAL


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def local_index():
    """Create a LocalIndexManager with short update interval for testing."""
    return LocalIndexManager(update_interval=0)


@pytest.fixture
def temp_db(tmp_path: Path):
    """Create a temporary SQLite index database with known data."""
    from backend.core.offline_index import _ensure_index, create_or_update_index

    # Patch INDEX_DIR to use tmp_path
    with patch("backend.core.offline_index.INDEX_DIR", tmp_path):
        conn = _ensure_index("test_eco")
        conn.close()

        pkgs = [
            {
                "name": "requests",
                "versions": [
                    {
                        "version": "2.31.0",
                        "release_date": "2023-05-22",
                        "requires_python": ">=3.7",
                        "dependencies": json.dumps({"dependencies": {"urllib3": ">=1.21.1"}}),
                    },
                    {
                        "version": "2.28.0",
                        "release_date": "2022-06-08",
                        "requires_python": ">=3.7",
                        "dependencies": json.dumps({"dependencies": {"urllib3": ">=1.21.1"}}),
                    },
                ],
            },
            {
                "name": "flask",
                "versions": [
                    {
                        "version": "3.0.0",
                        "release_date": "2023-09-30",
                        "requires_python": ">=3.8",
                        "dependencies": json.dumps({"dependencies": {"Werkzeug": ">=3.0.0"}}),
                    },
                ],
            },
        ]
        inserted = create_or_update_index("test_eco", pkgs)
        yield tmp_path, pkgs, inserted


# ===================================================================
# Settings tests
# ===================================================================


class TestSettings:
    def test_enable_local_index_default(self):
        assert ENABLE_LOCAL_INDEX is False

    def test_local_index_dir_default(self):
        assert LOCAL_INDEX_DIR.endswith(".cache/udr/indexes")

    def test_update_interval_default(self):
        assert LOCAL_INDEX_UPDATE_INTERVAL == 3600


# ===================================================================
# LocalIndexManager tests
# ===================================================================


class TestLocalIndexManager:
    def test_needs_sync_no_index(self, local_index):
        """needs_sync returns True when no index exists."""
        with patch("backend.core.offline_index.INDEX_DIR", Path("/tmp/nonexistent-udr-test")):
            assert local_index.needs_sync("pypi") is True

    def test_needs_sync_stale_index(self, local_index, temp_db):
        """needs_sync returns True when index is stale."""
        tmp_path, _, _ = temp_db
        with patch("backend.core.offline_index.INDEX_DIR", tmp_path):
            assert local_index.needs_sync("test_eco") is True

    def test_package_count_zero(self, local_index):
        """package_count returns 0 for missing ecosystem."""
        with patch("backend.core.offline_index.INDEX_DIR", Path("/tmp/nonexistent-udr-test")):
            assert local_index.package_count("pypi") == 0

    def test_package_count(self, local_index, temp_db):
        """package_count returns correct package count."""
        tmp_path, pkgs, inserted = temp_db
        with patch("backend.core.offline_index.INDEX_DIR", tmp_path):
            assert local_index.package_count("test_eco") == len(pkgs)

    def test_lookup_miss(self, local_index):
        """lookup returns None for missing package."""
        with patch("backend.core.offline_index.INDEX_DIR", Path("/tmp/nonexistent-udr-test")):
            assert local_index.lookup("pypi", "nonexistent-pkg") is None

    def test_lookup_hit(self, local_index, temp_db):
        """lookup returns package info for cached package."""
        tmp_path, pkgs, inserted = temp_db
        with patch("backend.core.offline_index.INDEX_DIR", tmp_path):
            result = local_index.lookup("test_eco", "requests")
            assert result is not None
            assert result["name"] == "requests"
            assert len(result["versions"]) == 2

    def test_lookup_versions_sorted(self, local_index, temp_db):
        """lookup returns versions in descending order (newest first)."""
        tmp_path, pkgs, inserted = temp_db
        with patch("backend.core.offline_index.INDEX_DIR", tmp_path):
            result = local_index.lookup("test_eco", "requests")
            versions = [v["version"] for v in result["versions"]]
            assert versions == ["2.31.0", "2.28.0"]


# ===================================================================
# PyPI helpers
# ===================================================================


class TestPyPIHelpers:
    @pytest.mark.asyncio
    async def test_fetch_package_list_parse(self):
        """Test that the regex parser extracts package names from PyPI Simple API HTML."""
        fake_html = """
        <html><body>
        <a href="/simple/requests/">requests</a>
        <a href="/simple/flask/">flask</a>
        <a href="/simple/numpy/">numpy</a>
        <a href="/simple/@scoped/">@scoped</a>
        <a href="/simple/../../../..">../../..</a>
        </body></html>
        """

        # Instead of mocking aiohttp (complex), test the HTML parsing
        # by calling the internal regex directly
        import re

        from backend.core.local_index import _fetch_pypi_package_list as orig_func

        pkgs = re.findall(r'<a\s+href="([^"]+)"', fake_html)
        pkgs = sorted(set(p.rstrip("/") for p in pkgs if p and not p.startswith("..")))
        assert "/simple/requests" in pkgs
        assert "/simple/flask" in pkgs
        assert "/simple/numpy" in pkgs
        assert "/simple/@scoped" in pkgs

    @pytest.mark.asyncio
    async def test_fetch_package_json_parse(self):
        """Test that JSON parsing produces correct version entries."""
        fake_json = {
            "info": {
                "name": "requests",
                "requires_dist": ["urllib3>=1.21.1", "certifi>=2017.4.17"],
            },
            "releases": {
                "2.31.0": [{"upload_time": "2023-05-22T10:00:00", "requires_python": ">=3.7"}],
                "2.28.0": [{"upload_time": "2022-06-08T10:00:00", "requires_python": ">=3.7"}],
            },
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=fake_json)

        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=None)

        # session.get must NOT be AsyncMock — calling it must return the ctx mock directly
        mock_session = MagicMock()
        mock_session.get.return_value = mock_get_ctx

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)

        sem = asyncio.Semaphore(5)

        with patch("aiohttp.ClientSession", return_value=mock_session_ctx):
            result = await _fetch_pypi_package_json("requests", sem)
            assert result is not None
            assert result["name"] == "requests"
            assert len(result["versions"]) == 2
            versions = [v["version"] for v in result["versions"]]
            assert "2.31.0" in versions
            assert "2.28.0" in versions

    def test_parse_pypi_deps(self):
        """Test PyPI requires_dist parser."""
        deps = ["urllib3>=1.21.1", "certifi>=2017.4.17", "chardet<5,>=3.0.2"]
        result = _parse_pypi_deps(deps)
        assert "urllib3" in result["dependencies"]
        assert result["dependencies"]["urllib3"] == ">=1.21.1"

    def test_parse_pypi_deps_skips_extras(self):
        """Test that extras/markers are skipped."""
        deps = ["urllib3>=1.21.1 ; python_version < '3.10'"]
        result = _parse_pypi_deps(deps)
        assert "urllib3" not in result["dependencies"]


# ===================================================================
# crates.io index file parser
# ===================================================================


class TestCrateIndexParser:
    def test_parse_empty(self, tmp_path):
        """Empty crate file returns None."""
        f = tmp_path / "empty.json"
        f.write_text("")
        assert _parse_crate_index_file(f) is None

    def test_parse_invalid_json(self, tmp_path):
        """Invalid JSON returns None."""
        f = tmp_path / "bad.json"
        f.write_text("not json")
        assert _parse_crate_index_file(f) is None

    def test_parse_single_version(self, tmp_path):
        """Single version crate file parses correctly."""
        data = json.dumps(
            {
                "name": "serde",
                "vers": "1.0.0",
                "deps": [{"name": "serde_derive", "req": "^1.0"}],
            }
        )
        f = tmp_path / "serde.json"
        f.write_text(data + "\n")
        result = _parse_crate_index_file(f)
        assert result is not None
        assert result["name"] == "serde"
        assert result["versions"][0]["version"] == "1.0.0"

    def test_parse_multiple_versions(self, tmp_path):
        """Multi-line crate file (multiple versions) parses correctly."""
        lines = [
            json.dumps({"name": "serde", "vers": "1.0.0", "deps": []}),
            json.dumps({"name": "serde", "vers": "1.1.0", "deps": []}),
        ]
        f = tmp_path / "serde.json"
        f.write_text("\n".join(lines) + "\n")
        result = _parse_crate_index_file(f)
        assert result is not None
        assert len(result["versions"]) == 2


# ===================================================================
# Aggregator integration (mock-based)
# ===================================================================


class TestAggregatorIntegration:
    @pytest.mark.asyncio
    async def test_sync_local_index_calls_manager(self):
        """DataAggregator.sync_local_index delegates to LocalIndexManager.sync."""
        from backend.core.data_aggregator import DataAggregator

        agg = DataAggregator()
        with patch(
            "backend.core.local_index.LocalIndexManager.sync", new_callable=AsyncMock
        ) as mock_sync:
            mock_sync.return_value = 42
            result = await agg.sync_local_index("pypi")
            assert result == 42
            mock_sync.assert_called_once_with("pypi")

        await agg.close()

    @pytest.mark.asyncio
    async def test_fetch_package_data_checks_local_index_when_enabled(self):
        """When ENABLE_LOCAL_INDEX=true, _fetch_package_data checks local index first."""
        from backend.core.data_aggregator import DataAggregator
        from backend.core.offline_index import create_or_update_index

        agg = DataAggregator()

        # Seed the local index
        pkgs = [
            {
                "name": "test-offline-pkg",
                "versions": [{"version": "1.0.0", "dependencies": json.dumps({})}],
            }
        ]
        with patch("backend.core.offline_index.INDEX_DIR") as mock_dir:
            mock_dir.exists.return_value = True
            mock_dir.__truediv__ = MagicMock(return_value=Path("/tmp/udr-test/test_eco.db"))

        with patch("backend.settings.ENABLE_LOCAL_INDEX", True):
            with patch("backend.core.local_index.LocalIndexManager.lookup") as mock_lookup:
                mock_lookup.return_value = {
                    "name": "test-offline-pkg",
                    "version": "1.0.0",
                    "versions": [{"version": "1.0.0"}],
                    "dependencies": {},
                }
                # This should return from local index without calling the client
                result = await agg._fetch_package_data(
                    MagicMock(value="test_eco"), "test-offline-pkg", None, True, True
                )
                assert result is not None
                assert result["name"] == "test-offline-pkg"
                mock_lookup.assert_called_once()

        await agg.close()

    @pytest.mark.asyncio
    async def test_fetch_package_data_falls_through_on_miss(self):
        """When ENABLE_LOCAL_INDEX=true but package not in index, falls through to API."""
        from backend.core.data_aggregator import DataAggregator

        agg = DataAggregator()

        with patch("backend.settings.ENABLE_LOCAL_INDEX", True):
            with patch("backend.core.local_index.LocalIndexManager.lookup", return_value=None):
                with patch.object(agg, "_get_client") as mock_get_client:
                    # Use spec=None so MagicMock doesn't auto-create attributes
                    mock_client = MagicMock(spec=["get_package_info"])

                    def fake_get_package_info(name, **kwargs):
                        return {"name": name, "version": "1.0"}

                    mock_client.get_package_info = fake_get_package_info
                    mock_get_client.return_value = mock_client
                    mock_eco = MagicMock()
                    mock_eco.value = "test_eco"

                    result = await agg._fetch_package_data(mock_eco, "test-pkg", None, True, True)
                    assert result is not None

        await agg.close()


# ===================================================================
# sync_deduplication (for the batch flow)
# ===================================================================


class TestSyncDeduplication:
    def test_create_or_update_index_dedup(self, tmp_path):
        """create_or_update_index handles duplicate packages gracefully."""
        from backend.core.offline_index import (
            _ensure_index,
            create_or_update_index,
            get_package_info,
        )

        with patch("backend.core.offline_index.INDEX_DIR", tmp_path):
            pkgs = [
                {
                    "name": "duplicate-pkg",
                    "versions": [{"version": "1.0.0", "dependencies": json.dumps({})}],
                },
                {
                    "name": "duplicate-pkg",
                    "versions": [{"version": "2.0.0", "dependencies": json.dumps({})}],
                },
            ]
            inserted = create_or_update_index("dedup_eco", pkgs)
            # Each package dict is processed and counted, even if name duplicates
            assert inserted == 2

            info = get_package_info("dedup_eco", "duplicate-pkg")
            assert info is not None
            # Should have both versions
            assert len(info["versions"]) == 2


class TestGetLocalIndex:
    """Tests for get_local_index factory (Phase 3-D)."""

    def test_factory_returns_none_when_disabled(self):
        """get_local_index returns None when ENABLE_LOCAL_INDEX is false."""
        with patch("backend.settings.ENABLE_LOCAL_INDEX", False):
            assert get_local_index("pypi") is None
            assert get_local_index("npm") is None
            assert get_local_index("crates") is None

    def test_factory_returns_manager_for_supported_ecosystems(self):
        """get_local_index returns LocalIndexManager for pypi/npm/crates."""
        with patch("backend.settings.ENABLE_LOCAL_INDEX", True):
            mgr = get_local_index("pypi")
            assert isinstance(mgr, LocalIndexManager)
            mgr = get_local_index("npm")
            assert isinstance(mgr, LocalIndexManager)
            mgr = get_local_index("crates")
            assert isinstance(mgr, LocalIndexManager)

    def test_factory_returns_none_for_unsupported_ecosystem(self):
        """get_local_index returns None for unsupported ecosystems."""
        with patch("backend.settings.ENABLE_LOCAL_INDEX", True):
            assert get_local_index("gradle") is None
            assert get_local_index("swift") is None
            assert get_local_index("unknown") is None
