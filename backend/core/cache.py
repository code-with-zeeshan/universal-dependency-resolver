# backend/core/cache.py
import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
import time
from collections.abc import Callable
from functools import wraps
from typing import Any
from urllib.parse import urlparse

from ._json import dumps, loads

try:
    from aiocache import Cache
    from aiocache.serializers import JsonSerializer

    AIOCACHE_AVAILABLE = True
except ImportError:
    AIOCACHE_AVAILABLE = False

from backend.settings import (
    CACHE_TTL,
    FEATURES,
    REDIS_URL,
)

logger = logging.getLogger(__name__)


class DictCache:
    """Pure-Python in-memory + file-backed cache with TTL support.

    Persists to a JSON file so cached data survives process restarts.
    """

    def __init__(self, persist_path: str | None = None):
        """Initialize."""
        self._store: dict[str, tuple[Any, float | None]] = {}
        self._lock = asyncio.Lock()
        self._persist_path = persist_path or os.path.join(tempfile.gettempdir(), "udr_cache.json")
        self._dirty = False
        self._load_from_disk()

    def _load_from_disk(self):
        """Load from disk."""
        try:
            if os.path.exists(self._persist_path):
                with open(self._persist_path) as f:
                    raw = loads(f.read())
                now = time.time()
                for key, (value, expiry) in raw.items():
                    if expiry is None or expiry > now:
                        self._store[key] = (value, expiry)
        except Exception as exc:
            logger.debug(f"Cache load from disk skipped: {exc}")

    def _save_to_disk(self):
        """Save to disk."""
        if not self._dirty:
            return
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            tmp_path = self._persist_path + ".tmp"
            with open(tmp_path, "w") as f:
                f.write(dumps(self._store, default=str))
            shutil.move(tmp_path, self._persist_path)
            self._dirty = False
        except Exception as exc:
            logger.debug(f"Cache save to disk failed: {exc}")

    async def get(self, key: str) -> Any | None:
        """Get."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if expiry is not None and time.time() > expiry:
                del self._store[key]
                self._dirty = True
                return None
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set."""
        async with self._lock:
            expiry = (time.time() + ttl) if ttl is not None else None
            self._store[key] = (value, expiry)
            self._dirty = True
            self._save_to_disk()

    async def delete(self, key: str) -> None:
        """Delete."""
        async with self._lock:
            self._store.pop(key, None)
            self._dirty = True
            self._save_to_disk()

    async def clear(self) -> None:
        """Clear."""
        async with self._lock:
            self._store.clear()
            self._dirty = True
            self._save_to_disk()

    async def close(self) -> None:
        """Close."""
        async with self._lock:
            self._save_to_disk()
            self._store.clear()

    async def incr(self, key: str, delta: int = 1) -> int:
        """Incr."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._store[key] = (delta, None)
                self._dirty = True
                return delta
            value, expiry = entry
            value = (value or 0) + delta
            self._store[key] = (value, expiry)
            self._dirty = True
            return value

    async def ping(self) -> bool:
        """Ping."""
        return True


class CacheManager:
    """Manages caching operations with aiocache."""

    def __init__(self, redis_url: str = REDIS_URL):
        """Initialize."""
        self.redis_url = redis_url
        self._cache: DictCache | Cache | None = None
        self._cache_stats: dict[str, int] = {"hits": 0, "misses": 0, "errors": 0}

    async def connect(self):
        """Initialize cache backend."""
        if not FEATURES.get("ENABLE_CACHE", True):
            logger.info("Caching is disabled")
            return

        if not AIOCACHE_AVAILABLE:
            self._cache = DictCache()
            logger.info("Using DictCache fallback (aiocache not installed)")
            return

        try:
            if self.redis_url:
                parsed = urlparse(self.redis_url)
                self._cache = Cache(
                    Cache.REDIS,
                    endpoint=parsed.hostname or "localhost",
                    port=parsed.port or 6379,
                    password=parsed.password,
                    db=int(parsed.path.lstrip("/") or "0"),
                    serializer=JsonSerializer(),
                )
                await self._cache.client.ping()
                logger.info("Redis cache connected successfully")
            else:
                self._cache = Cache(Cache.MEMORY)
                logger.info("Using in-memory cache (no Redis URL configured)")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Using DictCache fallback.")
            self._cache = DictCache()

    async def disconnect(self):
        """Close cache connection."""
        if self._cache:
            await self._cache.close()

    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate a cache key from prefix and arguments."""
        key_parts = [prefix]

        for arg in args:
            if isinstance(arg, (dict, list)):
                key_parts.append(hashlib.md5(dumps(arg, sort_keys=True).encode()).hexdigest())
            else:
                key_parts.append(str(arg))

        if kwargs:
            sorted_kwargs = sorted(kwargs.items())
            kwargs_str = dumps(sorted_kwargs)
            key_parts.append(hashlib.md5(kwargs_str.encode()).hexdigest())

        return ":".join(key_parts)

    async def get(self, key: str) -> Any | None:
        """Get value from cache."""
        if not FEATURES.get("ENABLE_CACHE", True) or not self._cache:
            return None

        try:
            value = await self._cache.get(key)
            if value is not None:
                self._cache_stats["hits"] += 1
            else:
                self._cache_stats["misses"] += 1
            return value
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            self._cache_stats["errors"] += 1
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set value in cache with optional TTL."""
        if not FEATURES.get("ENABLE_CACHE", True) or not self._cache:
            return False

        if ttl is None:
            ttl = CACHE_TTL

        try:
            await self._cache.set(key, value, ttl=ttl)
            return True
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            self._cache_stats["errors"] += 1
            return False

    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if not self._cache:
            return False

        try:
            await self._cache.delete(key)
            return True
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern."""
        count = 0
        cache = self._cache
        if cache is None:
            return 0
        try:
            if hasattr(cache, "client") and cache.client is not None:
                cursor = 0
                while True:
                    cursor, keys = await cache.client.scan(cursor, match=pattern, count=100)
                    if keys and hasattr(cache, "client") and cache.client is not None:
                        await cache.client.delete(*keys)
                        count += len(keys)
                    if cursor == 0:
                        break
            else:
                await cache.clear()
                count = 1
            return count
        except Exception as e:
            logger.error(f"Cache clear pattern error: {e}")
            return 0

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from cache."""
        result: dict[str, Any] = {}

        if not FEATURES.get("ENABLE_CACHE", True) or not self._cache:
            return result

        try:
            values = await asyncio.gather(*[self._cache.get(k) for k in keys])
            for key, value in zip(keys, values):
                if value is not None:
                    result[key] = value
                    self._cache_stats["hits"] += 1
                else:
                    self._cache_stats["misses"] += 1
            return result
        except Exception as e:
            logger.error(f"Cache get_many error: {e}")
            return {}

    async def set_many(self, mapping: dict[str, Any], ttl: int | None = None) -> bool:
        """Set multiple values in cache."""
        if not FEATURES.get("ENABLE_CACHE", True) or not self._cache:
            return False

        if ttl is None:
            ttl = CACHE_TTL

        try:
            await asyncio.gather(*[self._cache.set(k, v, ttl=ttl) for k, v in mapping.items()])
            return True
        except Exception as e:
            logger.error(f"Cache set_many error: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._cache_stats["hits"] + self._cache_stats["misses"]
        hit_rate = (self._cache_stats["hits"] / total * 100) if total > 0 else 0

        return {
            **self._cache_stats,
            "total_requests": total,
            "hit_rate": round(hit_rate, 2),
            "local_cache_size": 0,
        }

    async def increment(self, key: str, amount: int = 1) -> int | None:
        """Increment a counter in cache."""
        if not self._cache:
            return None

        try:
            return await self._cache.incr(key, delta=amount)
        except Exception as e:
            logger.error(f"Cache increment error for key {key}: {e}")
            return None

    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration time for a key."""
        if not self._cache:
            return False

        try:
            if hasattr(self._cache, "client") and self._cache.client is not None:
                return await self._cache.client.expire(key, ttl)
            value = await self._cache.get(key)
            if value is not None:
                await self._cache.set(key, value, ttl=ttl)
                return True
            return False
        except Exception as e:
            logger.error(f"Cache expire error for key {key}: {e}")
            return False


# Global cache instance
cache_manager = CacheManager()


def cache_key(*args, **kwargs) -> Callable:
    """Decorator to generate cache keys for methods."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *method_args, **method_kwargs):
            """Wrapper."""
            prefix = f"{self.__class__.__name__}:{func.__name__}"
            key = cache_manager._generate_key(prefix, *method_args, **method_kwargs)

            cached_value = await cache_manager.get(key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {key}")
                return cached_value

            result = await func(self, *method_args, **method_kwargs)

            ttl = kwargs.get("ttl", CACHE_TTL)
            await cache_manager.set(key, result, ttl)

            return result

        return wrapper

    return decorator


def cached(ttl: int | None = None, key_prefix: str | None = None):
    """Decorator for caching function results."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            """Async wrapper."""
            prefix = key_prefix or f"{func.__module__}:{func.__name__}"
            cache_key = cache_manager._generate_key(prefix, *args, **kwargs)

            cached_value = await cache_manager.get(cache_key)
            if cached_value is not None:
                return cached_value

            result = await func(*args, **kwargs)

            cache_ttl = ttl or CACHE_TTL
            await cache_manager.set(cache_key, result, cache_ttl)

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            """Sync wrapper."""
            return asyncio.run(async_wrapper(*args, **kwargs))

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Cache key generators for specific use cases
class CacheKeys:
    """Standardized cache key generators."""

    @staticmethod
    def package_info(ecosystem: str, package_name: str, version: str | None = None) -> str:
        """Generate cache key for package information."""
        if version:
            return f"package:{ecosystem}:{package_name}:{version}"
        return f"package:{ecosystem}:{package_name}"

    @staticmethod
    def search_results(query: str, ecosystems: list[str] | None = None, **filters) -> str:
        """Generate cache key for search results."""
        eco_str = ",".join(sorted(ecosystems)) if ecosystems else "all"
        filter_str = hashlib.md5(dumps(filters, sort_keys=True).encode()).hexdigest()
        return f"search:{query}:{eco_str}:{filter_str}"

    @staticmethod
    def dependency_tree(ecosystem: str, package_name: str, version: str) -> str:
        """Generate cache key for dependency tree."""
        return f"deps:{ecosystem}:{package_name}:{version}"

    @staticmethod
    def system_info() -> str:
        """Generate cache key for system information."""
        return "system:info:current"

    @staticmethod
    def compatibility_check(package_id: str, system_hash: str) -> str:
        """Generate cache key for compatibility check."""
        return f"compat:{package_id}:{system_hash}"
