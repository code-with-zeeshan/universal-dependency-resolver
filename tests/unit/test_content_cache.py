"""Unit tests for backend/core/content_cache.py."""

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from backend.core.content_cache import ContentAddressedCache, _content_hash


# ── Helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture
def cache_dir():
    with tempfile.TemporaryDirectory(prefix="udr_cac_") as d:
        yield Path(d)


@pytest.fixture
def cac(cache_dir):
    return ContentAddressedCache(cache_dir=cache_dir, default_ttl=None)


# ── Tests: content hash ─────────────────────────────────────────────────────


class TestContentHash:
    def test_deterministic(self):
        a = _content_hash(b"hello")
        b = _content_hash(b"hello")
        assert a == b

    def test_differs_for_diff_content(self):
        assert _content_hash(b"hello") != _content_hash(b"world")

    def test_hex_string(self):
        h = _content_hash(b"test")
        assert isinstance(h, str)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ── Tests: basic set / get ──────────────────────────────────────────────────


class TestSetGet:
    async def test_set_and_get(self, cac):
        await cac.set("key1", {"data": [1, 2, 3]})
        result = await cac.get("key1")
        assert result == {"data": [1, 2, 3]}

    async def test_get_missing(self, cac):
        assert await cac.get("nonexistent") is None

    async def test_get_expired(self, cac):
        await cac.set("key2", "value", ttl=0)  # expires immediately
        time.sleep(0.01)
        assert await cac.get("key2") is None

    async def test_overwrite_same_key(self, cac):
        await cac.set("k", "v1")
        await cac.set("k", "v2")
        assert await cac.get("k") == "v2"

    async def test_lists(self, cac):
        data = [1, "two", {"three": 3}]
        await cac.set("list", data)
        assert await cac.get("list") == data

    async def test_nested_dicts(self, cac):
        data = {"a": {"b": {"c": [1, 2, 3]}}}
        await cac.set("nested", data)
        assert await cac.get("nested") == data


# ── Tests: deduplication ────────────────────────────────────────────────────


class TestDedup:
    async def test_same_content_shares_blob(self, cac, cache_dir):
        await cac.set("key-a", {"x": 1})
        await cac.set("key-b", {"x": 1})
        # Both keys should point to the same blob
        entry_a = cac._index["key-a"]
        entry_b = cac._index["key-b"]
        assert entry_a["hash"] == entry_b["hash"]
        # Only one blob file
        blob_path = cac._blob_path(entry_a["hash"])
        assert blob_path.is_file()

    async def test_different_content_different_blobs(self, cac):
        await cac.set("a", {"x": 1})
        await cac.set("b", {"x": 2})
        assert cac._index["a"]["hash"] != cac._index["b"]["hash"]


# ── Tests: integrity ────────────────────────────────────────────────────────


class TestIntegrity:
    async def test_corrupted_blob_returns_none(self, cac, cache_dir):
        await cac.set("k", "data")
        entry = cac._index["k"]
        blob_path = cac._blob_path(entry["hash"])
        # Corrupt the blob
        blob_path.write_text("garbage")
        result = await cac.get("k")
        assert result is None
        # Corrupted entry should be removed from index
        assert "k" not in cac._index

    async def test_missing_blob_returns_none(self, cac):
        await cac.set("k", "data")
        entry = cac._index["k"]
        blob_path = cac._blob_path(entry["hash"])
        blob_path.unlink()
        result = await cac.get("k")
        assert result is None
        assert "k" not in cac._index

    async def test_missing_et_al(self):
        """Orphan safeguard: delete dangling index entry when blob is gone."""
        cac2 = ContentAddressedCache(cache_dir=tempfile.mkdtemp(), default_ttl=None)
        # Manually write a dangling index entry (no blob)
        cac2._index["ghost"] = {
            "hash": "aaaa" * 16,
            "created": time.time(),
            "ttl": None,
            "expiry": None,
        }
        assert await cac2.get("ghost") is None  # no crash
        assert "ghost" not in cac2._index


# ── Tests: delete ───────────────────────────────────────────────────────────


class TestDelete:
    async def test_delete_removes_index_entry(self, cac):
        await cac.set("k", "v")
        assert await cac.get("k") == "v"
        await cac.delete("k")
        assert await cac.get("k") is None

    async def test_delete_missing_no_error(self, cac):
        await cac.delete("nonexistent")  # should not raise

    async def test_delete_leaves_blob(self, cac):
        await cac.set("k", "v")
        entry = cac._index["k"]
        blob_path = cac._blob_path(entry["hash"])
        assert blob_path.is_file()
        await cac.delete("k")
        assert blob_path.is_file()  # blob stays until GC


# ── Tests: clear ────────────────────────────────────────────────────────────


class TestClear:
    async def test_clear_removes_all(self, cac):
        await cac.set("a", 1)
        await cac.set("b", 2)
        await cac.clear()
        assert await cac.get("a") is None
        assert await cac.get("b") is None

    async def test_clear_removes_blobs(self, cac):
        await cac.set("a", 1)
        await cac.clear()
        # Blob dir should be empty
        blobs = list(cac._blobs.iterdir()) if cac._blobs.is_dir() else []
        assert len(blobs) == 0


# ── Tests: GC ───────────────────────────────────────────────────────────────


class TestGC:
    async def test_gc_removes_orphaned_blobs(self, cac, cache_dir):
        await cac.set("a", "value1")
        await cac.set("b", "value2")
        entry_a = cac._index["a"]
        entry_b = cac._index["b"]
        blob_a = cac._blob_path(entry_a["hash"])
        blob_b = cac._blob_path(entry_b["hash"])
        # Create an orphan blob (write to blob dir without index entry)
        orphan_hash = "ff" * 32
        orphan_path = cac._blob_path(orphan_hash)
        orphan_path.parent.mkdir(parents=True, exist_ok=True)
        orphan_path.write_text(json.dumps("orphan"))
        assert orphan_path.is_file()
        # GC should remove the orphan
        removed = await cac.gc()
        assert removed == 1
        assert not orphan_path.is_file()
        # Referenced blobs should still exist
        assert blob_a.is_file()
        assert blob_b.is_file()

    async def test_gc_no_orphans(self, cac):
        await cac.set("a", 1)
        removed = await cac.gc()
        assert removed == 0

    async def test_gc_empty_cache(self, cac):
        removed = await cac.gc()
        assert removed == 0

    async def test_gc_after_delete(self, cac):
        await cac.set("a", "val")
        entry = cac._index["a"]
        blob_path = cac._blob_path(entry["hash"])
        await cac.delete("a")
        removed = await cac.gc()
        assert removed == 1
        assert not blob_path.is_file()


# ── Tests: persistence across instance restarts ─────────────────────────────


class TestPersistence:
    async def test_survives_reinit(self, cache_dir):
        cac1 = ContentAddressedCache(cache_dir=cache_dir, default_ttl=None)
        await cac1.set("persist", {"keep": True})
        # Re-create with same dir
        cac2 = ContentAddressedCache(cache_dir=cache_dir, default_ttl=None)
        assert await cac2.get("persist") == {"keep": True}

    async def test_expired_cleared_on_reinit(self, cache_dir):
        cac1 = ContentAddressedCache(cache_dir=cache_dir, default_ttl=0)
        await cac1.set("gone", "bye")
        time.sleep(0.01)
        cac2 = ContentAddressedCache(cache_dir=cache_dir, default_ttl=0)
        assert await cac2.get("gone") is None

    async def test_no_crosstalk(self):
        d1 = Path(tempfile.mkdtemp())
        d2 = Path(tempfile.mkdtemp())
        cac1 = ContentAddressedCache(cache_dir=d1, default_ttl=None)
        cac2 = ContentAddressedCache(cache_dir=d2, default_ttl=None)
        await cac1.set("shared", "v1")
        await cac2.set("shared", "v2")
        assert await cac1.get("shared") == "v1"
        assert await cac2.get("shared") == "v2"


# ── Tests: edge cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    async def test_none_value(self, cac):
        await cac.set("null", None)
        assert await cac.get("null") is None

    async def test_bool_value(self, cac):
        await cac.set("t", True)
        await cac.set("f", False)
        assert await cac.get("t") is True
        assert await cac.get("f") is False

    async def test_empty_dict(self, cac):
        await cac.set("empty", {})
        assert await cac.get("empty") == {}

    async def test_empty_list(self, cac):
        await cac.set("empty", [])
        assert await cac.get("empty") == []

    async def test_string_value(self, cac):
        await cac.set("s", "hello world")
        assert await cac.get("s") == "hello world"

    async def test_int_key(self, cac):
        await cac.set(42, "value")
        assert await cac.get(42) == "value"

    async def test_unicode_content(self, cac):
        await cac.set("unicode", {"emoji": "🚀", "text": "café"})
        assert await cac.get("unicode") == {"emoji": "🚀", "text": "café"}

    async def test_large_data(self, cac):
        large = {"numbers": list(range(10_000))}
        await cac.set("large", large)
        result = await cac.get("large")
        assert result["numbers"] == list(range(10_000))


# ── Tests: TTL ──────────────────────────────────────────────────────────────


class TestTTL:
    async def test_default_ttl(self, cache_dir):
        cac = ContentAddressedCache(cache_dir=cache_dir, default_ttl=3600)
        await cac.set("k", "v")
        entry = cac._index["k"]
        assert entry["ttl"] == 3600
        assert entry["expiry"] is not None

    async def test_no_default_ttl(self, cache_dir):
        cac = ContentAddressedCache(cache_dir=cache_dir, default_ttl=None)
        await cac.set("k", "v")
        entry = cac._index["k"]
        assert entry["ttl"] is None
        assert entry["expiry"] is None

    async def test_explicit_ttl_overrides_default(self, cac):
        await cac.set("k", "v", ttl=7200)
        entry = cac._index["k"]
        assert entry["ttl"] == 7200

    async def test_expired_entry_not_returned(self, cac):
        await cac.set("k", "v", ttl=0.001)
        time.sleep(0.01)
        assert await cac.get("k") is None
