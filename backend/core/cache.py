# backend/core/cache.py
import json
import pickle
import hashlib
from typing import Any, Optional, Union, List, Dict, Callable
from datetime import timedelta
import asyncio
from functools import wraps
import redis.asyncio as redis
from redis.exceptions import RedisError
import logging

from backend.settings import (
    REDIS_URL, 
    CACHE_TTL, 
    CACHE_TTL_SHORT,
    CACHE_TTL_LONG,
    CACHE_MAX_SIZE,
    CACHE_EVICTION_POLICY,
    FEATURES
)

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages caching operations with Redis"""
    
    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self._redis_client = None
        self._local_cache = {}  # Fallback in-memory cache
        self._cache_stats = {
            'hits': 0,
            'misses': 0,
            'errors': 0
        }
    
    async def connect(self):
        """Initialize Redis connection"""
        if not FEATURES.get('ENABLE_CACHE', True):
            logger.info("Caching is disabled")
            return
        
        try:
            self._redis_client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50
            )
            await self._redis_client.ping()
            logger.info("Redis cache connected successfully")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Using in-memory cache.")
            self._redis_client = None
    
    async def disconnect(self):
        """Close Redis connection"""
        if self._redis_client:
            await self._redis_client.close()
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate a cache key from prefix and arguments"""
        key_parts = [prefix]
        
        # Add positional arguments
        for arg in args:
            if isinstance(arg, (dict, list)):
                key_parts.append(hashlib.md5(json.dumps(arg, sort_keys=True).encode()).hexdigest())
            else:
                key_parts.append(str(arg))
        
        # Add keyword arguments
        if kwargs:
            sorted_kwargs = sorted(kwargs.items())
            kwargs_str = json.dumps(sorted_kwargs)
            key_parts.append(hashlib.md5(kwargs_str.encode()).hexdigest())
        
        return ":".join(key_parts)
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not FEATURES.get('ENABLE_CACHE', True):
            return None
        
        try:
            if self._redis_client:
                value = await self._redis_client.get(key)
                if value:
                    self._cache_stats['hits'] += 1
                    # Try to deserialize JSON first, then pickle
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        return pickle.loads(value.encode('latin-1'))
                else:
                    self._cache_stats['misses'] += 1
                    return None
            else:
                # Fallback to local cache
                if key in self._local_cache:
                    value, expiry = self._local_cache[key]
                    if expiry is None or expiry > asyncio.get_event_loop().time():
                        self._cache_stats['hits'] += 1
                        return value
                    else:
                        del self._local_cache[key]
                
                self._cache_stats['misses'] += 1
                return None
                
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            self._cache_stats['errors'] += 1
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL"""
        if not FEATURES.get('ENABLE_CACHE', True):
            return False
        
        if ttl is None:
            ttl = CACHE_TTL
        
        try:
            if self._redis_client:
                # Try JSON serialization first, fall back to pickle
                try:
                    serialized = json.dumps(value)
                except (TypeError, ValueError):
                    serialized = pickle.dumps(value).decode('latin-1')
                
                await self._redis_client.setex(key, ttl, serialized)
                return True
            else:
                # Fallback to local cache with size limit
                if len(self._local_cache) >= CACHE_MAX_SIZE:
                    # Simple LRU eviction
                    oldest_key = next(iter(self._local_cache))
                    del self._local_cache[oldest_key]
                
                expiry = asyncio.get_event_loop().time() + ttl if ttl > 0 else None
                self._local_cache[key] = (value, expiry)
                return True
                
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            self._cache_stats['errors'] += 1
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete value from cache"""
        try:
            if self._redis_client:
                await self._redis_client.delete(key)
            else:
                self._local_cache.pop(key, None)
            return True
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern"""
        count = 0
        try:
            if self._redis_client:
                cursor = 0
                while True:
                    cursor, keys = await self._redis_client.scan(
                        cursor, match=pattern, count=100
                    )
                    if keys:
                        await self._redis_client.delete(*keys)
                        count += len(keys)
                    if cursor == 0:
                        break
            else:
                # Local cache pattern matching
                keys_to_delete = [k for k in self._local_cache if pattern.replace('*', '') in k]
                for key in keys_to_delete:
                    del self._local_cache[key]
                    count += 1
            
            return count
        except Exception as e:
            logger.error(f"Cache clear pattern error: {e}")
            return 0
    
    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values from cache"""
        result = {}
        
        if not FEATURES.get('ENABLE_CACHE', True):
            return result
        
        try:
            if self._redis_client:
                values = await self._redis_client.mget(keys)
                for key, value in zip(keys, values):
                    if value:
                        try:
                            result[key] = json.loads(value)
                        except json.JSONDecodeError:
                            result[key] = pickle.loads(value.encode('latin-1'))
            else:
                # Local cache
                for key in keys:
                    value = await self.get(key)
                    if value is not None:
                        result[key] = value
            
            return result
        except Exception as e:
            logger.error(f"Cache get_many error: {e}")
            return {}
    
    async def set_many(self, mapping: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set multiple values in cache"""
        if not FEATURES.get('ENABLE_CACHE', True):
            return False
        
        if ttl is None:
            ttl = CACHE_TTL
        
        try:
            if self._redis_client:
                pipe = self._redis_client.pipeline()
                for key, value in mapping.items():
                    try:
                        serialized = json.dumps(value)
                    except (TypeError, ValueError):
                        serialized = pickle.dumps(value).decode('latin-1')
                    pipe.setex(key, ttl, serialized)
                await pipe.execute()
                return True
            else:
                # Local cache
                for key, value in mapping.items():
                    await self.set(key, value, ttl)
                return True
                
        except Exception as e:
            logger.error(f"Cache set_many error: {e}")
            return False
    
    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        total = self._cache_stats['hits'] + self._cache_stats['misses']
        hit_rate = (self._cache_stats['hits'] / total * 100) if total > 0 else 0
        
        return {
            **self._cache_stats,
            'total_requests': total,
            'hit_rate': round(hit_rate, 2),
            'local_cache_size': len(self._local_cache)
        }
    
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a counter in cache"""
        try:
            if self._redis_client:
                return await self._redis_client.incrby(key, amount)
            else:
                # Local cache increment
                current = self._local_cache.get(key, (0, None))[0]
                new_value = current + amount
                self._local_cache[key] = (new_value, None)
                return new_value
        except Exception as e:
            logger.error(f"Cache increment error for key {key}: {e}")
            return None
    
    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration time for a key"""
        try:
            if self._redis_client:
                return await self._redis_client.expire(key, ttl)
            else:
                # Update local cache expiry
                if key in self._local_cache:
                    value, _ = self._local_cache[key]
                    expiry = asyncio.get_event_loop().time() + ttl
                    self._local_cache[key] = (value, expiry)
                    return True
                return False
        except Exception as e:
            logger.error(f"Cache expire error for key {key}: {e}")
            return False


# Global cache instance
cache_manager = CacheManager()


def cache_key(*args, **kwargs) -> Callable:
    """Decorator to generate cache keys for methods"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *method_args, **method_kwargs):
            # Generate cache key
            prefix = f"{self.__class__.__name__}:{func.__name__}"
            key = cache_manager._generate_key(prefix, *method_args, **method_kwargs)
            
            # Try to get from cache
            cached_value = await cache_manager.get(key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {key}")
                return cached_value
            
            # Call the actual function
            result = await func(self, *method_args, **method_kwargs)
            
            # Cache the result
            ttl = kwargs.get('ttl', CACHE_TTL)
            await cache_manager.set(key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


def cached(ttl: Optional[int] = None, key_prefix: Optional[str] = None):
    """Decorator for caching function results"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate cache key
            prefix = key_prefix or f"{func.__module__}:{func.__name__}"
            cache_key = cache_manager._generate_key(prefix, *args, **kwargs)
            
            # Try to get from cache
            cached_value = await cache_manager.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Call the actual function
            result = await func(*args, **kwargs)
            
            # Cache the result
            cache_ttl = ttl or CACHE_TTL
            await cache_manager.set(cache_key, result, cache_ttl)
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, run in event loop
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(async_wrapper(*args, **kwargs))
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Cache key generators for specific use cases
class CacheKeys:
    """Standardized cache key generators"""
    
    @staticmethod
    def package_info(ecosystem: str, package_name: str, version: Optional[str] = None) -> str:
        """Generate cache key for package information"""
        if version:
            return f"package:{ecosystem}:{package_name}:{version}"
        return f"package:{ecosystem}:{package_name}"
    
    @staticmethod
    def search_results(query: str, ecosystems: Optional[List[str]] = None, **filters) -> str:
        """Generate cache key for search results"""
        eco_str = ",".join(sorted(ecosystems)) if ecosystems else "all"
        filter_str = hashlib.md5(json.dumps(filters, sort_keys=True).encode()).hexdigest()
        return f"search:{query}:{eco_str}:{filter_str}"
    
    @staticmethod
    def dependency_tree(ecosystem: str, package_name: str, version: str) -> str:
        """Generate cache key for dependency tree"""
        return f"deps:{ecosystem}:{package_name}:{version}"
    
    @staticmethod
    def system_info() -> str:
        """Generate cache key for system information"""
        return "system:info:current"
    
    @staticmethod
    def compatibility_check(package_id: str, system_hash: str) -> str:
        """Generate cache key for compatibility check"""
        return f"compat:{package_id}:{system_hash}"