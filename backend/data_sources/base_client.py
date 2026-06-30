import aiohttp
import asyncio
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timedelta

from backend.settings import (
    CACHE_TTL,
    USER_AGENTS,
    RATE_LIMITS,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    RETRY_BACKOFF_FACTOR,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_OPEN_TIME,
)

logger = logging.getLogger(__name__)


class BaseDataSourceClient:
    """Shared HTTP client + caching + rate limiting for all data sources."""

    def __init__(
        self,
        ecosystem: str,
        base_url: str,
        cache_ttl: int = CACHE_TTL,
        user_agent: Optional[str] = None,
        rate_limit: Optional[int] = None,
        timeout: int = REQUEST_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ):
        self.ecosystem = ecosystem
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl = cache_ttl
        self.user_agent = user_agent or USER_AGENTS.get(
            ecosystem, USER_AGENTS["default"]
        )
        self.rate_limit = rate_limit or RATE_LIMITS.get(ecosystem, 600)
        self.timeout = timeout
        self.max_retries = max_retries
        self._request_timestamps: list = []
        self._circuit_state = "CLOSED"
        self._circuit_failure_count = 0
        self._circuit_failure_threshold = CIRCUIT_BREAKER_FAILURE_THRESHOLD
        self._circuit_open_time = CIRCUIT_BREAKER_OPEN_TIME
        self._circuit_last_open_time: Optional[datetime] = None
        self._circuit_half_open_successes = 0
        self._circuit_half_open_max_successes = 2

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    def _cache_get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            data, timestamp = self._cache[key]
            if (datetime.now() - timestamp).total_seconds() < self._cache_ttl:
                return data
            del self._cache[key]
        return None

    def _cache_set(self, key: str, data: Any):
        self._cache[key] = (data, datetime.now())

    async def _throttle(self):
        now = datetime.now()
        cutoff = now - timedelta(seconds=60)
        self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]
        if len(self._request_timestamps) >= self.rate_limit:
            sleep_for = (self._request_timestamps[0] - cutoff).total_seconds()
            if sleep_for > 0:
                logger.debug(
                    f"Rate limited for {self.ecosystem}, sleeping {sleep_for:.1f}s"
                )
                await asyncio.sleep(sleep_for)
        self._request_timestamps.append(now)

    async def _make_request(self, method: str, url: str, **kwargs) -> Optional[Dict]:
        """Actual HTTP request without circuit breaker.
        Returns None for 404, raises IOError for network/server errors."""
        await self._throttle()
        session = self._get_session()
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", self.user_agent)

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with session.request(
                    method, url, headers=headers, timeout=aiohttp.ClientTimeout(total=self.timeout), **kwargs
                ) as resp:
                    if resp.status == 404:
                        return None
                    if resp.status >= 500 and attempt < self.max_retries - 1:
                        backoff = RETRY_BACKOFF_FACTOR**attempt
                        await asyncio.sleep(backoff)
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt == self.max_retries - 1:
                    logger.error(
                        f"{self.ecosystem} request failed after {self.max_retries} retries: {e}"
                    )
                    break
                await asyncio.sleep(RETRY_BACKOFF_FACTOR**attempt)
        raise IOError(f"{self.ecosystem} request failed: {last_error}") from last_error

    async def _circuit_breaker_call(
        self, method: str, url: str, **kwargs
    ) -> Optional[Dict]:
        """Execute request with circuit breaker pattern.
        404s (None results) do NOT count as circuit failures."""
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
                logger.warning(
                    f"Circuit OPEN for {self.ecosystem}, skipping request to {url}"
                )
                return None

        try:
            result = await self._make_request(method, url, **kwargs)
        except IOError:
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
            if (
                self._circuit_half_open_successes
                >= self._circuit_half_open_max_successes
            ):
                self._circuit_state = "CLOSED"
                self._circuit_failure_count = 0
                logger.info(
                    f"Circuit CLOSED for {self.ecosystem} after successful HALF_OPEN probes"
                )
        else:
            self._circuit_failure_count = 0

        return result

    async def _request(self, method: str, url: str, **kwargs) -> Optional[Dict]:
        return await self._circuit_breaker_call(method, url, **kwargs)

    async def _get(self, url: str, **kwargs) -> Optional[Dict]:
        return await self._request("GET", url, **kwargs)

    async def cached_get(
        self, cache_key: str, url: str, ttl: Optional[int] = None
    ) -> Optional[Dict]:
        import os as _os

        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if _os.environ.get("UDR_OFFLINE", "").lower() == "true":
            logger.warning(f"Offline mode: skipping network request for {url}")
            return None

        data = await self._get(url)
        if data is not None:
            orig_ttl = self._cache_ttl
            if ttl is not None:
                self._cache_ttl = ttl
            self._cache_set(cache_key, data)
            if ttl is not None:
                self._cache_ttl = orig_ttl
        return data

    @property
    def circuit_state(self) -> str:
        """Current circuit breaker state."""
        return self._circuit_state

    def reset_circuit(self):
        """Manually reset the circuit breaker."""
        self._circuit_state = "CLOSED"
        self._circuit_failure_count = 0
        self._circuit_half_open_successes = 0
        self._circuit_last_open_time = None
        logger.info(f"Circuit manually reset for {self.ecosystem}")
