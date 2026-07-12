"""NPM compressed index manager.

Seeds the local index from the npm ``/-/v1/search`` endpoint
and keeps it current via the ``_changes`` feed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

import aiohttp

from backend.core.offline_index import (
    _connect,
    _ensure_index,
    create_or_update_index,
    get_package_info,
    index_status,
)

logger = logging.getLogger(__name__)

_NPM_SEARCH_URL = "https://registry.npmjs.org/-/v1/search"
_NPM_CHANGES_URL = "https://registry.npmjs.org/-/v1/_changes"
_NPM_PACKAGE_URL = "https://registry.npmjs.org"


class NpmIndexManager:
    """Per-ecosystem manager for the local npm index.

    Parameters
    ----------
    update_interval:
        Minimum seconds between full syncs (default 3600).
    """

    def __init__(self, update_interval: int = 3600) -> None:
        self.update_interval = update_interval
        self._last_updated: datetime | None = None

    # ------------------------------------------------------------------
    # Search / Lookup
    # ------------------------------------------------------------------

    def search(self, name: str) -> list[dict[str, Any]]:
        """Search the local npm index for packages matching *name*."""
        conn = _connect("npm")
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
        finally:
            conn.close()

    def get(self, name: str) -> dict[str, Any] | None:
        """Return full info for a single npm package from the local index."""
        return get_package_info("npm", name)

    @property
    def last_updated(self) -> datetime | None:
        """Return the timestamp of the last successful sync, or *None*."""
        if self._last_updated is not None:
            return self._last_updated
        status = index_status("npm")
        if status is None:
            return None
        updated = status.get("metadata", {}).get("updated_at", "")
        if not updated:
            return None
        try:
            return datetime.strptime(updated, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    async def sync(self) -> int:
        """Synchronise the local npm index.

        Strategy:
            1. If the index is empty, seed it from ``/-/v1/search?text=*``.
            2. Incrementally update via the ``_changes`` feed.

        Returns the number of packages synced.
        """
        status = index_status("npm")
        pkg_count = status.get("packages", 0) if status else 0

        total = 0
        if pkg_count == 0:
            logger.info("npm index empty — seeding from search endpoint")
            total += await self._seed_from_search()

        total += await self._sync_changes()

        self._last_updated = datetime.now(UTC)
        return total

    async def _seed_from_search(self) -> int:
        """Seed the index by paginating through ``/-/v1/search``."""
        sem = asyncio.Semaphore(10)
        total = 0
        from_arg = 0
        size = 250

        async with aiohttp.ClientSession() as session:
            while True:
                url = f"{_NPM_SEARCH_URL}?text=*&size={size}&from={from_arg}"
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            logger.warning(
                                "npm search returned %d at from=%d", resp.status, from_arg
                            )
                            break
                        data = await resp.json()
                except Exception as exc:
                    logger.warning("npm search failed at from=%d: %s", from_arg, exc)
                    break

                objects = data.get("objects", [])
                if not objects:
                    break

                packages = [o["package"] for o in objects if "package" in o]
                if not packages:
                    break

                tasks = [self._fetch_details(pkg["name"], sem) for pkg in packages]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                valid = [r for r in results if isinstance(r, dict)]
                if valid:
                    inserted = create_or_update_index("npm", valid)
                    total += inserted

                from_arg += size
                if from_arg >= data.get("total", 0):
                    break

        logger.info("npm seed complete: %d packages indexed", total)
        return total

    async def _sync_changes(self) -> int:
        """Incremental update via the ``_changes`` feed."""
        since = 0
        status = index_status("npm")
        if status:
            try:
                since = int(status.get("metadata", {}).get("changes_since", "0"))
            except (ValueError, TypeError):
                since = 0

        url = f"{_NPM_CHANGES_URL}?since={since}&limit=1000"
        try:
            async with aiohttp.ClientSession() as session, session.get(url) as resp:
                if resp.status != 200:
                    logger.warning("npm _changes feed returned %d", resp.status)
                    return 0
                rows = await resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch npm changes feed: %s", exc)
            return 0

        if not rows:
            return 0

        sem = asyncio.Semaphore(10)
        batch_size = 25
        total = 0
        new_since = since

        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            tasks = [self._fetch_details(row["id"], sem) for row in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            valid = [r for r in results if isinstance(r, dict)]
            if valid:
                total += create_or_update_index("npm", valid)
            new_since = max(new_since, batch[-1].get("seq", 0))

        conn = _ensure_index("npm")
        if conn:
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO index_metadata (key, value) VALUES (?, ?)",
                    ("changes_since", str(new_since)),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO index_metadata (key, value) VALUES (?, ?)",
                    ("updated_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                )
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

        logger.info("npm changes sync: %d packages updated (changes_since=%d)", total, new_since)
        return total

    async def _fetch_details(self, package: str, sem: asyncio.Semaphore) -> dict | None:
        """Fetch full metadata for a single npm package."""
        url = f"{_NPM_PACKAGE_URL}/{package}"
        async with sem:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            return None
                        data = await resp.json()
            except Exception as exc:
                logger.debug("Failed to fetch npm package %s: %s", package, exc)
                return None

        versions = []
        for ver_str, ver_data in data.get("versions", {}).items():
            deps = ver_data.get("dependencies", {})
            versions.append(
                {
                    "version": ver_str,
                    "release_date": ver_data.get("date"),
                    "requires_python": None,
                    "dependencies": {"dependencies": deps},
                }
            )
        return {
            "name": data.get("name", package),
            "versions": versions,
        }
