"""Module docstring."""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from backend.core.cache import DictCache
from backend.core.registry_auth import resolve_auth_headers
from backend.settings import (
    CACHE_TTL,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_OPEN_TIME,
    MAX_RETRIES,
    RATE_LIMITS,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF_FACTOR,
    RETRY_MAX_DELAY,
    USER_AGENTS,
)

logger = logging.getLogger(__name__)


# Registry of all active sessions for clean shutdown
_sessions_registry: list[aiohttp.ClientSession] = []


async def close_all_sessions() -> None:
    """Close all tracked aiohttp sessions (call on application shutdown)."""
    """Close all tracked aiohttp sessions (call on application shutdown)."""
    for sess in _sessions_registry:
        if not sess.closed:
            await sess.close()
    _sessions_registry.clear()


class BaseDataSourceClient:
    """Shared HTTP client + caching + rate limiting for all data sources."""

    """Shared HTTP client + caching + rate limiting for all data sources."""

    def __init__(
        self,
        ecosystem: str,
        base_url: str,
        cache_ttl: int = CACHE_TTL,
        user_agent: str | None = None,
        rate_limit: int | None = None,
        timeout: int = REQUEST_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        auth_headers: dict[str, str] | None = None,
    ):
        """Initialize."""
        self.ecosystem = ecosystem
        self.base_url = base_url
        self.session: aiohttp.ClientSession | None = None
        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "udr", ecosystem)
        self._cache: DictCache = DictCache(persist_path=os.path.join(cache_dir, "cache.json"))
        self._cache_ttl = cache_ttl
        self.user_agent = user_agent or USER_AGENTS.get(ecosystem, USER_AGENTS["default"])
        self.rate_limit = rate_limit or RATE_LIMITS.get(ecosystem, 600)
        self.timeout = timeout
        self.max_retries = max_retries
        self._auth_headers: dict[str, str] = resolve_auth_headers(
            ecosystem=ecosystem,
            registry_url=base_url,
            explicit_headers=auth_headers,
        )
        self._auth_explicit = bool(auth_headers)
        self._auth_env_prefix = ecosystem.upper()
        self._auth_last_check = time.monotonic()
        self._auth_refresh_interval = 60  # seconds
        self._request_timestamps: list = []
        self._throttle_lock = asyncio.Lock()
        self._circuit_state = "CLOSED"
        self._circuit_failure_count = 0
        self._circuit_failure_threshold = CIRCUIT_BREAKER_FAILURE_THRESHOLD
        self._circuit_open_time = CIRCUIT_BREAKER_OPEN_TIME
        self._circuit_last_open_time: datetime | None = None
        self._circuit_half_open_successes = 0
        self._circuit_half_open_max_successes = 2
        self._circuit_lock = asyncio.Lock()

    async def __aenter__(self):
        """Async   aenter."""
        self.session = aiohttp.ClientSession()
        _sessions_registry.append(self.session)
        return self

    async def __aexit__(self, *args):
        """Async   aexit."""
        if self.session and not self.session.closed:
            await self.session.close()
            if self.session in _sessions_registry:
                _sessions_registry.remove(self.session)
            self.session = None

    def refresh_auth(self) -> None:
        """Re-read authentication from env vars and .netrc.

        Use after environment variable changes or SIGHUP to pick up new
        credentials without restarting the process.

        Explicit constructor-level ``auth_headers`` take priority and are
        *not* overwritten by environment variables.
        """
        if self._auth_explicit:
            return
        old = self._auth_headers.copy()
        self._auth_headers = resolve_auth_headers(
            ecosystem=self.ecosystem,
            registry_url=self.base_url,
        )
        if old != self._auth_headers:
            logger.info("Auth headers refreshed for ecosystem '%s'", self.ecosystem)
        self._auth_last_check = time.monotonic()

    async def _maybe_refresh_auth(self) -> None:
        """Periodic auth refresh guard — called before each request."""
        if self._auth_explicit:
            return
        elapsed = time.monotonic() - self._auth_last_check
        if elapsed > self._auth_refresh_interval:
            self.refresh_auth()

    async def close(self):
        """Async close."""
        if self.session and not self.session.closed:
            await self.session.close()
            if self.session in _sessions_registry:
                _sessions_registry.remove(self.session)
            self.session = None

    async def get_artifact_hash(
        self,
        package_name: str,
        version: str,
    ) -> dict | None:
        """Get artifact integrity hash."""
        return None

    def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            _sessions_registry.append(self.session)
        return self.session

    async def _cache_get(self, key: str) -> Any | None:
        data = await self._cache.get(key)
        if data is not None:
            return data
        return None

    async def _cache_set(self, key: str, data: Any):
        await self._cache.set(key, data, ttl=self._cache_ttl)

    async def _throttle(self):
        now = datetime.now()
        cutoff = now - timedelta(seconds=60)

        # Purge expired timestamps under the lock to avoid race
        async with self._throttle_lock:
            self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]
            if len(self._request_timestamps) >= self.rate_limit:
                sleep_for = (self._request_timestamps[0] - cutoff).total_seconds()
                if sleep_for > 0:
                    logger.debug(f"Rate limited for {self.ecosystem}, sleeping {sleep_for:.1f}s")
                    await asyncio.sleep(sleep_for)
                    # Re-check after sleep — another coroutine may have advanced the window
                    now = datetime.now()
                    cutoff = now - timedelta(seconds=60)
                    self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]
            self._request_timestamps.append(now)

    async def _make_request(self, method: str, url: str, **kwargs) -> dict | None:
        """Actual HTTP request without circuit breaker.

        Returns None for 404, raises IOError for network/server errors.
        """
        await self._maybe_refresh_auth()
        await self._throttle()
        session = self._get_session()
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", self.user_agent)
        headers.update(self._auth_headers)

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(connect=10, sock_read=self.timeout),
                    **kwargs,
                ) as resp:
                    if resp.status == 404:
                        return None
                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", "5"))
                        backoff = min(retry_after, RETRY_MAX_DELAY)
                        logger.warning(
                            f"{self.ecosystem} rate limited (429), retrying after {backoff}s"
                        )
                        await asyncio.sleep(backoff)
                        continue
                    if resp.status >= 500 and attempt < self.max_retries - 1:
                        backoff = min(RETRY_BACKOFF_FACTOR**attempt, RETRY_MAX_DELAY)
                        await asyncio.sleep(backoff)
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            except (TimeoutError, aiohttp.ClientError) as e:
                last_error = e
                if attempt == self.max_retries - 1:
                    logger.error(
                        f"{self.ecosystem} request failed after {self.max_retries} retries: {e}"
                    )
                    break
                await asyncio.sleep(min(RETRY_BACKOFF_FACTOR**attempt, RETRY_MAX_DELAY))
        raise OSError(f"{self.ecosystem} request failed: {last_error}") from last_error

    async def _circuit_breaker_call(self, method: str, url: str, **kwargs) -> dict | None:
        """Execute request with circuit breaker pattern.

        404s (None results) do NOT count as circuit failures.
        """
        async with self._circuit_lock:
            now = datetime.now()

            if self._circuit_state == "OPEN":
                if (
                    self._circuit_last_open_time
                    and (now - self._circuit_last_open_time).total_seconds()
                    >= self._circuit_open_time
                ):
                    logger.debug(f"Circuit half-opening for {self.ecosystem}")
                    self._circuit_state = "HALF_OPEN"
                    self._circuit_half_open_successes = 0
                else:
                    logger.warning(f"Circuit OPEN for {self.ecosystem}, skipping request to {url}")
                    return None

            try:
                result = await self._make_request(method, url, **kwargs)
            except OSError:
                self._circuit_failure_count += 1
                logger.debug(
                    f"Circuit failure count incremented to {self._circuit_failure_count} for {self.ecosystem}"
                )
                if self._circuit_state == "HALF_OPEN":
                    self._circuit_state = "OPEN"
                    self._circuit_last_open_time = datetime.now()
                    logger.warning(
                        f"Circuit re-OPENED for {self.ecosystem} after HALF_OPEN failure"
                    )
                elif self._circuit_failure_count >= self._circuit_failure_threshold:
                    self._circuit_state = "OPEN"
                    self._circuit_last_open_time = datetime.now()
                    logger.warning(
                        f"Circuit OPENED for {self.ecosystem} after {self._circuit_failure_count} failures"
                    )
                return None

            if self._circuit_state == "HALF_OPEN":
                self._circuit_half_open_successes += 1
                if self._circuit_half_open_successes >= self._circuit_half_open_max_successes:
                    self._circuit_state = "CLOSED"
                    self._circuit_failure_count = 0
                    logger.info(
                        f"Circuit CLOSED for {self.ecosystem} after successful HALF_OPEN probes"
                    )
            else:
                self._circuit_failure_count = 0

        return result

    async def _request(self, method: str, url: str, **kwargs) -> dict | None:
        return await self._circuit_breaker_call(method, url, **kwargs)

    async def _get(self, url: str, **kwargs) -> dict | None:
        return await self._request("GET", url, **kwargs)

    async def _get_text(self, url: str, **kwargs) -> str | None:
        """Like ``_get`` but returns the raw response body as text."""
        """Like ``_get`` but returns the raw response body as text."""
        await self._throttle()
        session = self._get_session()
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", self.user_agent)
        headers.update(self._auth_headers)
        try:
            async with session.request(
                "GET",
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(connect=10, sock_read=self.timeout),
                **kwargs,
            ) as resp:
                if resp.status == 404:
                    return None
                resp.raise_for_status()
                return await resp.text()
        except (TimeoutError, aiohttp.ClientError) as e:
            logger.debug("_get_text failed for %s: %s", url, e)
            return None

    async def cached_get(
        self, cache_key: str, url: str, ttl: int | None = None, headers: dict | None = None
    ) -> dict | None:
        """Get from cache or fetch from URL."""
        import time as _time

        cached = await self._cache_get(cache_key)
        if cached is not None:
            if isinstance(cached, dict) and cached.get("__etag_wrapped__"):
                data = cached.get("data")
                etag = cached.get("etag")
                expires = cached.get("expires")
                if expires and _time.time() < expires:
                    return data
                if etag:
                    session = self._get_session()
                    req_headers = {"User-Agent": self.user_agent, "If-None-Match": etag}
                    req_headers.update(self._auth_headers)
                    if headers:
                        req_headers.update(headers)
                    try:
                        async with session.request(
                            "GET",
                            url,
                            headers=req_headers,
                            timeout=aiohttp.ClientTimeout(connect=10, sock_read=self.timeout),
                        ) as resp:
                            if resp.status == 304:
                                new_expiry = _time.time() + (ttl or self._cache_ttl)
                                cached["expires"] = new_expiry
                                await self._cache_set(cache_key, cached)
                                return data
                            if resp.status == 200:
                                new_data = await resp.json()
                                new_etag = resp.headers.get("ETag")
                                new_expiry = _time.time() + (ttl or self._cache_ttl)
                                wrapped = {
                                    "__etag_wrapped__": True,
                                    "data": new_data,
                                    "etag": new_etag,
                                    "expires": new_expiry,
                                }
                                await self._cache_set(cache_key, wrapped)
                                return new_data
                    except Exception:
                        logger.debug("ETag revalidation failed for %s", url, exc_info=True)
                    return data
                return data
            return cached

        from backend.settings import UDR_OFFLINE

        if UDR_OFFLINE:
            logger.warning(f"Offline mode: skipping network request for {url}")
            return None

        await self._throttle()
        session = self._get_session()
        req_headers = {"User-Agent": self.user_agent}
        req_headers.update(self._auth_headers)
        if headers:
            req_headers.update(headers)
        try:
            async with session.request(
                "GET",
                url,
                headers=req_headers,
                timeout=aiohttp.ClientTimeout(connect=10, sock_read=self.timeout),
            ) as resp:
                if resp.status == 404:
                    return None
                resp.raise_for_status()
                data = await resp.json()
                etag = resp.headers.get("ETag")
                expiry = _time.time() + (ttl or self._cache_ttl)
                if etag:
                    wrapped = {
                        "__etag_wrapped__": True,
                        "data": data,
                        "etag": etag,
                        "expires": expiry,
                    }
                    await self._cache_set(cache_key, wrapped)
                else:
                    orig_ttl = self._cache_ttl
                    if ttl is not None:
                        self._cache_ttl = ttl
                    await self._cache_set(cache_key, data)
                    if ttl is not None:
                        self._cache_ttl = orig_ttl
                return data
        except (TimeoutError, aiohttp.ClientError) as e:
            logger.error(f"{self.ecosystem} cached_get failed for {url}: {e}")
            return None

    @property
    def circuit_state(self) -> str:
        """Current circuit breaker state."""
        """Current circuit breaker state."""
        return self._circuit_state

    def reset_circuit(self):
        """Manually reset the circuit breaker."""
        self._circuit_state = "CLOSED"
        self._circuit_failure_count = 0
        self._circuit_half_open_successes = 0
        self._circuit_last_open_time = None
        logger.info(f"Circuit manually reset for {self.ecosystem}")
