# tests/unit/test_core/test_cache.py
import json
import os
import tempfile
import time

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from backend.core.cache import (
    DictCache,
    CacheManager,
    cache_key,
    cached,
    CacheKeys,
    cache_manager,
)


class TestDictCache:
    @pytest.fixture
    def cache(self):
        tmp = os.path.join(tempfile.gettempdir(), "udr_test_cache.json")
        if os.path.exists(tmp):
            os.remove(tmp)
        return DictCache(persist_path=tmp)

    @pytest.mark.asyncio
    async def test_get_missing_key(self, cache):
        assert await cache.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        await cache.set("foo", "bar")
        assert await cache.get("foo") == "bar"

    @pytest.mark.asyncio
    async def test_set_with_ttl(self, cache):
        await cache.set("baz", 42, ttl=3600)
        assert await cache.get("baz") == 42

    @pytest.mark.asyncio
    async def test_ttl_expiry(self, cache):
        await cache.set("expire_me", "gone", ttl=0)
        await cache.get("expire_me")
        assert await cache.get("expire_me") is None

    @pytest.mark.asyncio
    async def test_delete(self, cache):
        await cache.set("del_me", "value")
        await cache.delete("del_me")
        assert await cache.get("del_me") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, cache):
        await cache.delete("nothing")

    @pytest.mark.asyncio
    async def test_clear(self, cache):
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.clear()
        assert await cache.get("a") is None
        assert await cache.get("b") is None

    @pytest.mark.asyncio
    async def test_close(self, cache):
        await cache.set("persist", "data")
        await cache.close()
        assert await cache.get("persist") is None

    @pytest.mark.asyncio
    async def test_incr_new_key(self, cache):
        val = await cache.incr("counter")
        assert val == 1

    @pytest.mark.asyncio
    async def test_incr_existing_key(self, cache):
        await cache.set("counter", 5)
        val = await cache.incr("counter", 3)
        assert val == 8

    @pytest.mark.asyncio
    async def test_ping(self, cache):
        assert await cache.ping() is True

    @pytest.mark.asyncio
    async def test_persist_to_disk(self, cache):
        await cache.set("disk_key", "disk_val")
        assert os.path.exists(cache._persist_path)
        with open(cache._persist_path) as f:
            data = json.load(f)
        assert "disk_key" in data

    @pytest.mark.asyncio
    async def test_load_from_disk(self, cache):
        await cache.set("reload", "me")
        await cache.close()
        cache2 = DictCache(persist_path=cache._persist_path)
        val = await cache2.get("reload")
        assert val == "me"

    @pytest.mark.asyncio
    async def test_dirty_flag_resets_after_save(self, cache):
        await cache.set("x", 1)
        assert cache._dirty is False


class TestCacheManager:
    @pytest.fixture
    def manager(self):
        m = CacheManager(redis_url="")
        m._cache = None
        return m

    @pytest.mark.asyncio
    async def test_connect_dictcache_fallback(self, manager):
        with patch("backend.core.cache.AIOCACHE_AVAILABLE", False):
            await manager.connect()
            assert isinstance(manager._cache, DictCache)

    @pytest.mark.asyncio
    async def test_connect_disabled_cache(self, manager):
        with patch.dict("backend.core.cache.FEATURES", {"ENABLE_CACHE": False}):
            await manager.connect()
            assert manager._cache is None

    @pytest.mark.asyncio
    async def test_get_returns_none_when_disabled(self, manager):
        with patch.dict("backend.core.cache.FEATURES", {"ENABLE_CACHE": False}):
            result = await manager.get("key")
            assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self, manager):
        manager._cache = DictCache()
        await manager.set("hello", "world")
        result = await manager.get("hello")
        assert result == "world"

    @pytest.mark.asyncio
    async def test_set_returns_false_without_cache(self, manager):
        result = await manager.set("k", "v")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_returns_false_without_cache(self, manager):
        result = await manager.delete("k")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_returns_true(self, manager):
        manager._cache = DictCache()
        await manager._cache.set("k", "v")
        result = await manager.delete("k")
        assert result is True
        assert await manager._cache.get("k") is None

    @pytest.mark.asyncio
    async def test_clear_pattern_without_redis(self, manager):
        manager._cache = DictCache()
        await manager._cache.set("a", 1)
        await manager._cache.set("b", 2)
        count = await manager.clear_pattern("*")
        assert count == 1

    @pytest.mark.asyncio
    async def test_get_many(self, manager):
        manager._cache = DictCache()
        await manager._cache.set("k1", "v1")
        await manager._cache.set("k2", "v2")
        result = await manager.get_many(["k1", "k2", "k3"])
        assert result == {"k1": "v1", "k2": "v2"}

    @pytest.mark.asyncio
    async def test_set_many(self, manager):
        manager._cache = DictCache()
        result = await manager.set_many({"a": 1, "b": 2})
        assert result is True
        assert await manager._cache.get("a") == 1
        assert await manager._cache.get("b") == 2

    def test_get_stats_empty(self, manager):
        stats = manager.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["errors"] == 0
        assert stats["total_requests"] == 0
        assert stats["hit_rate"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_with_data(self, manager):
        manager._cache = DictCache()
        await manager._cache.set("k", "v")
        await manager.get("k")
        await manager.get("k")
        await manager.get("missing")
        stats = manager.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["total_requests"] == 3
        assert stats["hit_rate"] == 66.67

    @pytest.mark.asyncio
    async def test_increment(self, manager):
        manager._cache = DictCache()
        val = await manager.increment("cnt")
        assert val == 1
        val = await manager.increment("cnt", 5)
        assert val == 6

    @pytest.mark.asyncio
    async def test_increment_without_cache(self, manager):
        val = await manager.increment("cnt")
        assert val is None

    @pytest.mark.asyncio
    async def test_expire_with_dictcache(self, manager):
        manager._cache = DictCache()
        await manager._cache.set("k", "v", ttl=3600)
        result = await manager.expire("k", 0)
        assert result is True
        await manager._cache.get("k")
        assert await manager._cache.get("k") is None

    @pytest.mark.asyncio
    async def test_expire_without_cache(self, manager):
        result = await manager.expire("k", 3600)
        assert result is False

    def test_generate_key_simple(self, manager):
        key = manager._generate_key("prefix", "arg1", "arg2")
        assert key.startswith("prefix:arg1:arg2")

    def test_generate_key_with_dict_arg(self, manager):
        key = manager._generate_key("p", {"a": 1})
        parts = key.split(":")
        assert parts[0] == "p"
        assert len(parts[1]) == 32

    def test_generate_key_with_kwargs(self, manager):
        key = manager._generate_key("p", foo="bar")
        parts = key.split(":")
        assert parts[0] == "p"
        assert len(parts[1]) == 32

    @pytest.mark.asyncio
    async def test_disconnect_closes_cache(self, manager):
        mock_cache = AsyncMock()
        manager._cache = mock_cache
        await manager.disconnect()
        mock_cache.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_error_safe(self, manager):
        bad_cache = MagicMock()
        bad_cache.get = AsyncMock(side_effect=ValueError("fail"))
        manager._cache = bad_cache
        result = await manager.get("key")
        assert result is None
        assert manager._cache_stats["errors"] == 1

    @pytest.mark.asyncio
    async def test_set_error_safe(self, manager):
        bad_cache = MagicMock()
        bad_cache.set = AsyncMock(side_effect=ValueError("fail"))
        manager._cache = bad_cache
        result = await manager.set("k", "v")
        assert result is False
        assert manager._cache_stats["errors"] == 1


class TestCacheKeyDecorator:
    @pytest.mark.asyncio
    async def test_cache_key_hit_and_miss(self):
        class FakeService:
            async def fetch(self, x):
                return x * 2

        svc = FakeService()
        deco = cache_key(ttl=300)
        wrapped = deco(FakeService.fetch)

        with patch.object(cache_manager, "_generate_key", return_value="test_key"), \
             patch.object(cache_manager, "get", return_value=None), \
             patch.object(cache_manager, "set", AsyncMock()) as mock_set:
            result = await wrapped(svc, 5)
            assert result == 10
            mock_set.assert_awaited_once()

        with patch.object(cache_manager, "_generate_key", return_value="test_key2"), \
             patch.object(cache_manager, "get", return_value="cached_val"):
            result = await wrapped(svc, 5)
            assert result == "cached_val"


class TestCachedDecorator:
    @pytest.mark.asyncio
    async def test_cached_async_miss_and_hit(self):
        call_count = 0

        @cached(ttl=300)
        async def compute(n):
            nonlocal call_count
            call_count += 1
            return n * 2

        with patch.object(cache_manager, "_generate_key", return_value="ck"), \
             patch.object(cache_manager, "get", return_value=None), \
             patch.object(cache_manager, "set", AsyncMock()) as mock_set:
            result = await compute(3)
            assert result == 6
            assert call_count == 1
            mock_set.assert_awaited_once_with("ck", 6, 300)

        with patch.object(cache_manager, "_generate_key", return_value="ck2"), \
             patch.object(cache_manager, "get", return_value="cached"):
            result = await compute(3)
            assert result == "cached"
            assert call_count == 1

    def test_cached_sync_function_xfail(self):
        # cached decorator has a known limitation: sync_wrapper->async_wrapper
        # awaits the wrapped function, which fails for non-async functions.
        call_count = 0

        @cached(ttl=60, key_prefix="sync_test")
        def sync_func():
            nonlocal call_count
            call_count += 1
            return "sync_result"

        with pytest.raises(TypeError, match="can't be used in 'await'"):
            sync_func()


class TestCacheKeys:
    def test_package_info_without_version(self):
        key = CacheKeys.package_info("pypi", "requests")
        assert key == "package:pypi:requests"

    def test_package_info_with_version(self):
        key = CacheKeys.package_info("npm", "react", "18.2.0")
        assert key == "package:npm:react:18.2.0"

    def test_search_results_all(self):
        key = CacheKeys.search_results("numpy", ecosystems=None)
        assert key.startswith("search:numpy:all:")

    def test_search_results_specific(self):
        key = CacheKeys.search_results("test", ecosystems=["pypi", "npm"])
        assert key.startswith("search:test:")
        assert "pypi" in key
        assert "npm" in key

    def test_dependency_tree(self):
        key = CacheKeys.dependency_tree("crates", "serde", "1.0.0")
        assert key == "deps:crates:serde:1.0.0"

    def test_system_info(self):
        key = CacheKeys.system_info()
        assert key == "system:info:current"

    def test_compatibility_check(self):
        key = CacheKeys.compatibility_check("pkg123", "hash456")
        assert key == "compat:pkg123:hash456"
