"""Generic search-based and null index managers for ecosystems.

SearchApiIndexManager
    Syncs a local index by polling a registry search/list API.
    Supports pagination, single-page responses, and alphabetical
    prefix enumeration (for registries that require a query string).

NullIndexManager
    Placeholder for ecosystems without a listing API.
    ``sync()`` returns 0; lookup falls through to the live API.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any, Callable

import aiohttp

from backend.core.offline_index import (
    _connect,
    create_or_update_index,
    get_package_info,
    index_status,
)

logger = logging.getLogger(__name__)

_USER_AGENT = "UDR/1.0"


class NullIndexManager:
    """Placeholder for ecosystems without a listing API.

    ``sync()`` logs a warning and returns 0.
    ``search()`` and ``get()`` query ``offline_index`` (usually empty).
    """

    def __init__(self, ecosystem: str, update_interval: int = 3600) -> None:
        self.ecosystem = ecosystem
        self.update_interval = update_interval

    def search(self, name: str) -> list[dict[str, Any]]:
        return _search_offline(self.ecosystem, name)

    def get(self, name: str) -> dict[str, Any] | None:
        return get_package_info(self.ecosystem, name)

    @property
    def last_updated(self) -> datetime | None:
        return _last_updated(self.ecosystem)

    def needs_sync(self) -> bool:
        return _needs_sync(self.ecosystem, self.update_interval)

    async def sync(self) -> int:
        logger.debug("No local index listing API for %s — skipping sync", self.ecosystem)
        return 0


class SearchApiIndexManager:
    """Index manager that syncs via a registry search/list API.

    Parameters
    ----------
    ecosystem:
        Lowercase ecosystem name.
    update_interval:
        Seconds between full syncs.
    url:
        Base URL for the search API.
    page_size:
        Number of results per page (0 for single-page).
    parser:
        Callback that converts the API response JSON into
        ``[{name, versions: [{version}]}]``.
    single_page:
        If *True*, the response contains all packages at once.
    use_alpha_enumeration:
        If *True*, iterate alphabetical/digit prefixes instead of pages.
    next_page:
        Callback ``(response, page, page_size) -> bool`` — whether more pages exist.
    page_param:
        Query parameter name for pagination offset.
    page_calc:
        Callback ``(page, page_size) -> value`` for the page parameter.
    max_pages:
        Maximum pages to fetch (prevents runaway syncs).
    alpha_prefixes:
        List of prefix strings for alphabetical enumeration.
    """

    def __init__(
        self,
        ecosystem: str,
        update_interval: int = 3600,
        url: str = "",
        page_size: int = 0,
        parser: Callable[[Any], list[dict]] | None = None,
        single_page: bool = False,
        use_alpha_enumeration: bool = False,
        next_page: Callable[[Any, int, int], bool] | None = None,
        page_param: str = "",
        page_calc: Callable[[int, int], int] | None = None,
        max_pages: int | None = None,
        alpha_prefixes: list[str] | None = None,
    ) -> None:
        self.ecosystem = ecosystem
        self.update_interval = update_interval
        self._url = url
        self._page_size = page_size
        self._parser = parser
        self._single_page = single_page
        self._use_alpha_enumeration = use_alpha_enumeration
        self._next_page = next_page
        self._page_param = page_param
        self._page_calc = page_calc
        self._max_pages = max_pages
        self._alpha_prefixes = alpha_prefixes

    # ------------------------------------------------------------------
    # Search / Lookup  (via offline_index)
    # ------------------------------------------------------------------

    def search(self, name: str) -> list[dict[str, Any]]:
        return _search_offline(self.ecosystem, name)

    def get(self, name: str) -> dict[str, Any] | None:
        return get_package_info(self.ecosystem, name)

    @property
    def last_updated(self) -> datetime | None:
        return _last_updated(self.ecosystem)

    def needs_sync(self) -> bool:
        return _needs_sync(self.ecosystem, self.update_interval)

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    async def sync(self) -> int:
        logger.info("Syncing %s index …", self.ecosystem)

        if self._use_alpha_enumeration:
            return await self._sync_alpha_enumeration()
        if self._single_page:
            return await self._sync_single_page()
        return await self._sync_paginated()

    async def _sync_single_page(self) -> int:
        """Fetch everything in one request."""
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": _USER_AGENT}) as session:
                async with session.get(self._url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status != 200:
                        logger.warning("%s listing API returned %d", self.ecosystem, resp.status)
                        return 0
                    data = await resp.json()
        except (TimeoutError, aiohttp.ClientError, ValueError) as exc:
            logger.warning("Failed to sync %s: %s", self.ecosystem, exc)
            return 0

        if self._parser:
            packages = self._parser(data)
            if packages:
                count = create_or_update_index(self.ecosystem, packages)
                logger.info("%s sync complete: %d packages indexed", self.ecosystem, count)
                return count
        return 0

    async def _sync_paginated(self) -> int:
        """Fetch results page by page."""
        total = 0
        page = 0
        seen = set()

        while True:
            if self._max_pages and page >= self._max_pages:
                logger.info("%s sync stopped at max_pages=%d", self.ecosystem, self._max_pages)
                break

            page_value = self._page_calc(page, self._page_size) if self._page_calc else page
            url = self._build_page_url(page_value)
            try:
                async with aiohttp.ClientSession(headers={"User-Agent": _USER_AGENT}) as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                        if resp.status != 200:
                            logger.warning(
                                "%s API returned %d at page %d", self.ecosystem, resp.status, page
                            )
                            break
                        data = await resp.json()
            except (TimeoutError, aiohttp.ClientError, ValueError) as exc:
                logger.warning("Failed to sync %s page %d: %s", self.ecosystem, page, exc)
                break

            if self._parser:
                packages = self._parser(data)
                if not packages:
                    break

                new_packages = [p for p in packages if p.get("name") not in seen]
                if new_packages:
                    count = create_or_update_index(self.ecosystem, new_packages)
                    total += count
                    seen.update(p["name"] for p in new_packages)

                if not self._next_page or not self._next_page(data, page, self._page_size):
                    break

            page += 1

        logger.info("%s sync complete: %d packages indexed", self.ecosystem, total)
        return total

    async def _sync_alpha_enumeration(self) -> int:
        """Search with alphabetical prefix enumeration.

        Many registries require a query string in their search API.
        This iterates single-character prefixes (a-z, 0-9) to get
        broad coverage without needing a full listing endpoint.
        """
        if not self._alpha_prefixes or not self._parser:
            return 0

        total = 0
        seen = set()

        for prefix in self._alpha_prefixes:
            url = (
                self._url.replace("a", prefix, 1)
                if "q=a" in self._url
                else f"{self._url}&q={prefix}"
            )
            try:
                async with aiohttp.ClientSession(headers={"User-Agent": _USER_AGENT}) as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
            except (TimeoutError, aiohttp.ClientError, ValueError):
                continue

            packages = self._parser(data)
            if not packages:
                continue

            new_packages = [p for p in packages if p.get("name") not in seen]
            if new_packages:
                count = create_or_update_index(self.ecosystem, new_packages)
                total += count
                seen.update(p["name"] for p in new_packages)

        logger.info("%s alpha-enumeration sync complete: %d packages", self.ecosystem, total)
        return total

    def _build_page_url(self, page_value: int) -> str:
        """Insert the page parameter into the URL."""
        if self._page_param:
            from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

            parsed = urlparse(self._url)
            qs = parse_qs(parsed.query, keep_blank_values=True)
            qs[self._page_param] = [str(page_value)]
            new_qs = urlencode(qs, doseq=True)
            return urlunparse(parsed._replace(query=new_qs))
        return self._url


# ======================================================================
# Shared helpers
# ======================================================================


def _search_offline(ecosystem: str, name: str) -> list[dict[str, Any]]:
    """Search the offline index for packages matching *name*."""
    conn = _connect(ecosystem)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT p.name, "
            "  (SELECT v.version FROM versions v "
            "   WHERE v.package_id = p.id ORDER BY v.id DESC LIMIT 1) "
            "  AS latest_version "
            "FROM packages p WHERE p.name LIKE ? "
            "ORDER BY p.name LIMIT 100",
            (f"%{name}%",),
        ).fetchall()
        return [{"name": r["name"], "latest_version": r["latest_version"]} for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def _last_updated(ecosystem: str) -> datetime | None:
    """Return the timestamp of the last successful sync."""
    status = index_status(ecosystem)
    if status is None:
        return None
    updated = status.get("metadata", {}).get("updated_at", "")
    if not updated:
        return None
    try:
        return datetime.strptime(updated, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def _needs_sync(ecosystem: str, update_interval: int) -> bool:
    """Return *True* if the index is stale or absent."""
    status = index_status(ecosystem)
    if status is None:
        return True
    updated = status.get("metadata", {}).get("updated_at", "")
    if not updated:
        return True
    try:
        updated_ts = time.mktime(time.strptime(updated, "%Y-%m-%dT%H:%M:%SZ"))
        return (time.time() - updated_ts) > update_interval
    except (ValueError, OSError):
        return True
