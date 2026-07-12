"""PyPI compressed index manager.

Uses the PyPI Simple API (HTML page) to seed the local package list,
then fetches individual package JSON lazily on first access.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
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

_PYPI_SIMPLE_URL = "https://pypi.org/simple/"
_PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"


class PyPIIndexManager:
    """Per-ecosystem manager for the local PyPI index.

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
        """Search the local PyPI index for packages matching *name*."""
        conn = _connect("pypi")
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
        """Return full info for a single PyPI package from the local index."""
        info = get_package_info("pypi", name)
        if info is not None:
            return info
        return None

    @property
    def last_updated(self) -> datetime | None:
        """Return the timestamp of the last successful sync, or *None*."""
        if self._last_updated is not None:
            return self._last_updated
        status = index_status("pypi")
        if status is None:
            return None
        updated = status.get("metadata", {}).get("updated_at", "")
        if not updated:
            return None
        try:
            return datetime.strptime(updated, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    async def sync(self) -> int:
        """Synchronise the local PyPI index.

        Strategy: fetch the full package list from the Simple API,
        then lazily fetch JSON details for packages not yet cached.

        Returns the number of packages synced.
        """
        logger.info("Syncing PyPI index …")

        packages = await self._fetch_package_list()
        if not packages:
            logger.warning("PyPI sync returned 0 packages — aborting")
            return 0

        existing = self._existing_packages()
        new_packages = [p for p in packages if p not in existing]

        if not new_packages:
            logger.info("PyPI index already up to date (%d packages)", len(existing))
            self._last_updated = datetime.now(timezone.utc)
            return 0

        sem = asyncio.Semaphore(10)
        batch_size = 50
        total = 0

        for i in range(0, len(new_packages), batch_size):
            batch = new_packages[i : i + batch_size]
            tasks = [self._fetch_package_json(pkg, sem) for pkg in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            valid = [r for r in results if isinstance(r, dict)]
            if valid:
                inserted = create_or_update_index("pypi", valid)
                total += inserted

        self._last_updated = datetime.now(timezone.utc)
        logger.info(
            "PyPI sync complete: %d new packages indexed (total %d)",
            total,
            len(packages),
        )
        return total

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _existing_packages(self) -> set[str]:
        """Return the set of package names already in the local index."""
        conn = _connect("pypi")
        if conn is None:
            return set()
        try:
            rows = conn.execute("SELECT name FROM packages").fetchall()
            return {r["name"] for r in rows}
        except Exception:
            return set()
        finally:
            conn.close()

    async def _fetch_package_list(self) -> list[str]:
        """Fetch all package names from the PyPI Simple API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    _PYPI_SIMPLE_URL, headers={"Accept": "text/html"}
                ) as resp:
                    if resp.status != 200:
                        logger.warning("PyPI Simple API returned status %d", resp.status)
                        return []
                    html = await resp.text()
        except Exception as exc:
            logger.warning("Failed to fetch PyPI package list: %s", exc)
            return []

        pkgs = re.findall(r'<a\s+href="([^"]+)"', html)
        return sorted(set(p.rstrip("/") for p in pkgs if p and not p.startswith("..")))

    async def _fetch_package_json(
        self,
        package: str,
        sem: asyncio.Semaphore,
    ) -> dict | None:
        """Fetch full JSON metadata for a single PyPI package."""
        url = _PYPI_JSON_URL.format(package=package)
        async with sem:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers={"Accept": "application/json"}) as resp:
                        if resp.status != 200:
                            return None
                        data = await resp.json()
            except Exception as exc:
                logger.debug("Failed to fetch PyPI package %s: %s", package, exc)
                return None

        info = data.get("info", {})
        releases = data.get("releases", {})
        versions = []
        for ver_str, files in releases.items():
            if not files:
                continue
            release_date = None
            requires_python = None
            try:
                release_date = files[0].get("upload_time")
            except (IndexError, KeyError):
                pass
            try:
                requires_python = files[0].get("requires_python")
            except (IndexError, KeyError):
                pass
            deps = self._parse_deps(info.get("requires_dist", []))
            versions.append(
                {
                    "version": ver_str,
                    "release_date": release_date,
                    "requires_python": requires_python,
                    "dependencies": {"dependencies": {}} if not deps else deps,
                }
            )
        return {
            "name": info.get("name", package),
            "versions": versions,
        }

    @staticmethod
    def _parse_deps(requires_dist: list[str]) -> dict:
        """Parse PyPI ``requires_dist`` into ``{dependencies: {dep: spec}}``."""
        deps: dict[str, str] = {}
        pattern = re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9._\-]*)\s*([><=!~].+)?$")
        for entry in requires_dist:
            if not entry or ";" in entry:
                continue
            m = pattern.match(entry.strip())
            if m:
                name = m.group(1)
                spec = m.group(2) or "*"
                deps[name] = spec.strip()
        return {"dependencies": deps}
