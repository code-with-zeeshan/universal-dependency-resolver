"""Hypothesis property-based fuzz tests for ContentAddressedCache.

Ensures the cache:
  1. Never crashes on any input
  2. Is deterministic (same input → same hash)
  3. Preserves data through set/get round-trip
  4. Handles edge cases (None, empty, unicode, large)
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import assume, given, strategies as st

from backend.core.content_cache import (
    ContentAddressedCache,
    _content_hash,
    _to_json_bytes,
    _from_json_bytes,
)

# ── Data strategies ─────────────────────────────────────────────────────────

_json_compatible = st.recursive(
    base=st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-10_000, max_value=10_000),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(max_size=100),
    ),
    extend=lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(
            st.text(min_size=1, max_size=10),
            children,
            max_size=5,
        ),
    ),
    max_leaves=10,
)

_cache_keys = st.one_of(
    st.text(min_size=1, max_size=50),
    st.binary(min_size=1, max_size=50),
    st.integers(min_value=0, max_value=10_000).map(str),
    st.builds(lambda a, b: f"{a}:{b}", st.text(max_size=10), st.text(max_size=10)),
)


class TestCacheFuzz:
    """Property-based fuzz tests for ContentAddressedCache."""

    # ── _content_hash ───────────────────────────────────────────────────

    @given(st.binary())
    def test_content_hash_never_crashes(self, data: bytes):
        """SHA256 hash should never crash."""
        h = _content_hash(data)
        assert isinstance(h, str)
        assert len(h) == 64

    @given(st.binary(max_size=1000))
    def test_content_hash_deterministic(self, data: bytes):
        """Same input always produces the same hash."""
        assert _content_hash(data) == _content_hash(data)

    @given(st.binary(), st.binary())
    def test_content_hash_different_for_different_inputs(self, a: bytes, b: bytes):
        """Different inputs should produce different hashes."""
        assume(a != b)
        assert _content_hash(a) != _content_hash(b)

    @given(st.binary())
    def test_content_hash_is_hex(self, data: bytes):
        """Hash should be a valid hex string."""
        h = _content_hash(data)
        assert all(c in "0123456789abcdef" for c in h)

    # ── _to_json_bytes / _from_json_bytes ───────────────────────────────

    @given(_json_compatible)
    def test_json_roundtrip(self, value):
        """Serialization round-trip should preserve the value."""
        raw = _to_json_bytes(value)
        assert isinstance(raw, bytes)
        restored = _from_json_bytes(raw)
        assert restored == value

    # ── ContentAddressedCache set/get ───────────────────────────────────

    @given(key=_cache_keys, value=_json_compatible)
    async def test_set_get_roundtrip(self, key, value):
        """Setting and getting should preserve the value."""
        with tempfile.TemporaryDirectory(prefix="udr_cac_") as d:
            cac = ContentAddressedCache(cache_dir=Path(d), default_ttl=None)
            await cac.set(key, value)
            result = await cac.get(key)
            assert result == value

    @given(key=_cache_keys)
    async def test_get_missing(self, key):
        """Getting a non-existent key should return None."""
        with tempfile.TemporaryDirectory(prefix="udr_cac_") as d:
            cac = ContentAddressedCache(cache_dir=Path(d), default_ttl=None)
            assert await cac.get(key) is None

    @given(key=_cache_keys, value=_json_compatible)
    async def test_delete_removes_key(self, key, value):
        """Deleting a key should make it return None."""
        with tempfile.TemporaryDirectory(prefix="udr_cac_") as d:
            cac = ContentAddressedCache(cache_dir=Path(d), default_ttl=None)
            await cac.set(key, value)
            await cac.delete(key)
            assert await cac.get(key) is None

    @given(keys=st.lists(_cache_keys, min_size=1, max_size=5, unique=True))
    async def test_multiple_keys_independent(self, keys):
        """Multiple keys should be independently stored and retrievable."""
        with tempfile.TemporaryDirectory(prefix="udr_cac_") as d:
            cac = ContentAddressedCache(cache_dir=Path(d), default_ttl=None)
            for i, k in enumerate(keys):
                await cac.set(k, {"idx": i})
            for i, k in enumerate(keys):
                result = await cac.get(k)
                assert result == {"idx": i}

    # ── TTL properties ──────────────────────────────────────────────────

    @given(key=_cache_keys, value=_json_compatible)
    async def test_ttl_zero_expires_immediately(self, key, value):
        """Setting with ttl=0 should make the entry expire immediately."""
        with tempfile.TemporaryDirectory(prefix="udr_cac_") as d:
            cac = ContentAddressedCache(cache_dir=Path(d), default_ttl=None)
            await cac.set(key, value, ttl=0)
            # The entry may or may not be expired depending on timing

            import time

            time.sleep(0.01)
            result = await cac.get(key)
            assert result is None

    @given(key=_cache_keys, value=_json_compatible)
    async def test_no_ttl_persists(self, key, value):
        """Setting with no TTL should keep the entry."""
        with tempfile.TemporaryDirectory(prefix="udr_cac_") as d:
            cac = ContentAddressedCache(cache_dir=Path(d), default_ttl=None)
            await cac.set(key, value)
            assert await cac.get(key) == value


# ── Edge case strategies ────────────────────────────────────────────────────

_edge_case_values = st.one_of(
    st.none(),
    st.just(True),
    st.just(False),
    st.just(0),
    st.just(-1),
    st.just(""),
    st.just([]),
    st.just({}),
    st.just([None, True, False, 0, "", [], {}]),
    st.text(max_size=1000),
    # Unicode edge cases
    st.just("🚀"),
    st.just("café"),
    st.just("\u0000"),
    st.just("\uffff"),
)


class TestCacheEdgeCaseFuzz:
    """Property tests for edge case values."""

    @given(key=_cache_keys, value=_edge_case_values)
    async def test_edge_case_roundtrip(self, key, value):
        """Edge case values should survive set/get."""
        with tempfile.TemporaryDirectory(prefix="udr_cac_") as d:
            cac = ContentAddressedCache(cache_dir=Path(d), default_ttl=None)
            await cac.set(key, value)
            result = await cac.get(key)
            assert result == value

    @given(
        keys=st.lists(_cache_keys, min_size=2, max_size=5, unique=True),
        value=_edge_case_values,
    )
    async def test_dedup_edge_case(self, keys, value):
        """Multiple keys with the same value should share one blob."""
        with tempfile.TemporaryDirectory(prefix="udr_cac_") as d:
            cac = ContentAddressedCache(cache_dir=Path(d), default_ttl=None)
            for k in keys:
                await cac.set(k, value)
            hashes = {cac._index[k]["hash"] for k in keys}
            assert len(hashes) == 1  # single blob for all
