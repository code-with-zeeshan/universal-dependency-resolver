"""Crates.io compressed index manager.

Mirrors the ``crates.io-index`` Git repository locally and
parses the sparse directory structure into the offline SQLite index.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.core.offline_index import (
    _connect,
    create_or_update_index,
    get_package_info,
    index_status,
)
from backend.settings import LOCAL_INDEX_DIR

logger = logging.getLogger(__name__)

_CRATES_INDEX_REPO = "https://github.com/rust-lang/crates.io-index"


class CratesIndexManager:
    """Per-ecosystem manager for the local crates.io index.

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
        """Search the local crates.io index for packages matching *name*."""
        conn = _connect("crates")
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
        """Return full info for a single crate from the local index."""
        return get_package_info("crates", name)

    @property
    def last_updated(self) -> datetime | None:
        """Return the timestamp of the last successful sync, or *None*."""
        if self._last_updated is not None:
            return self._last_updated
        status = index_status("crates")
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
        """Synchronise the local crates.io index.

        Strategy: clone (or pull) the crates.io-index Git repository,
        then walk the sparse directory structure to parse every crate.

        Returns the number of packages indexed.
        """
        logger.info("Syncing crates.io index …")
        index_dir = self._index_path()

        if not index_dir.exists():
            logger.info("Cloning crates.io-index Git repo (first sync) …")
            try:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--depth=1",
                        _CRATES_INDEX_REPO,
                        str(index_dir),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError) as exc:
                logger.warning("Git clone failed (%s) — falling back to API sync", exc)
                return await self._sync_api()
        else:
            try:
                subprocess.run(
                    ["git", "-C", str(index_dir), "pull", "--ff-only"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=True,
                )
            except subprocess.CalledProcessError:
                logger.warning("Git pull failed — index may be stale")

        return self._walk_index(index_dir)

    def _walk_index(self, index_dir: Path) -> int:
        """Walk the Git index directory, parse crate files, and update the DB."""
        pkgs_found = 0
        batch: list[dict] = []

        for letter_dir in sorted(index_dir.iterdir()):
            if not letter_dir.is_dir() or letter_dir.name.startswith("."):
                continue
            for crate_file in sorted(letter_dir.iterdir()):
                if crate_file.suffix != ".json":
                    continue
                try:
                    data = self._parse_crate_file(crate_file)
                    if data:
                        batch.append(data)
                        pkgs_found += 1
                except Exception:
                    continue
                if len(batch) >= 100:
                    create_or_update_index("crates", batch)
                    batch = []

        if batch:
            create_or_update_index("crates", batch)

        self._last_updated = datetime.now(UTC)
        logger.info("crates.io sync complete: %d packages indexed", pkgs_found)
        return pkgs_found

    async def _sync_api(self) -> int:
        """Fallback: sync crates via the crates.io API when Git is unavailable."""
        import aiohttp

        logger.info("Syncing crates.io via API …")
        total = 0
        async with aiohttp.ClientSession() as session:
            for page in range(1, 51):
                url = f"https://crates.io/api/v1/crates?page={page}&per_page=100&sort=new"
                try:
                    async with session.get(url, headers={"User-Agent": "UDR/1.0"}) as resp:
                        if resp.status != 200:
                            break
                        data = await resp.json()
                        crates = data.get("crates", [])
                        if not crates:
                            break
                        batch = [{"name": c["id"], "versions": []} for c in crates]
                        if batch:
                            create_or_update_index("crates", batch)
                            total += len(batch)
                except Exception:
                    break

        self._last_updated = datetime.now(UTC)
        logger.info("crates.io API sync complete: %d packages registered", total)
        return total

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _index_path() -> Path:
        """Return the path to the local crates.io-index Git checkout."""
        return Path(LOCAL_INDEX_DIR) / "crates.io-index"

    @staticmethod
    def _parse_crate_file(crate_file: Path) -> dict | None:
        """Parse a single crate JSON file (may contain multiple version lines)."""
        try:
            content = crate_file.read_text(encoding="utf-8")
        except Exception:
            return None

        versions = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            deps = {}
            for dep in entry.get("deps", []):
                dep_name = dep.get("name", "")
                dep_req = dep.get("req", "*")
                if dep_name:
                    deps[dep_name] = dep_req
            versions.append(
                {
                    "version": entry.get("vers", ""),
                    "release_date": None,
                    "requires_python": None,
                    "dependencies": {"dependencies": deps},
                }
            )

        if not versions:
            return None
        name = versions[0].get("name", crate_file.stem)
        return {"name": name, "versions": versions}
