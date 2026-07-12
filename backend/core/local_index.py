"""Local compressed index manager.

Wraps ``offline_index`` storage with per-ecosystem sync logic.
Three modes of index population:

- **Lazy** (PyPI): Seed package-list from the Simple API HTML page,
  then fetch individual package JSON on first access.
- **Changes-feed** (npm): Subscribe to the ``_changes`` feed for
  incremental updates.
- **Git-clone** (crates.io): Mirror the crates.io-index Git repo.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from backend import settings as _settings

logger = logging.getLogger(__name__)


class LocalIndexManager:
    """Facade over the offline SQLite index with ecosystem-specific sync.

    Parameters
    ----------
    update_interval:
        Minimum seconds between full syncs (default 3600).

    """

    def __init__(self, update_interval: int = 3600) -> None:
        """Docstring — Initialize."""
        self.update_interval = update_interval

    # ------------------------------------------------------------------
    # Lookup  (used by data aggregator)
    # ------------------------------------------------------------------

    def lookup(self, ecosystem: str, package_name: str) -> dict[str, Any] | None:
        """Return cached package info, or ``None`` if not in the index."""
        from backend.core.offline_index import get_package_info

        return get_package_info(ecosystem, package_name)

    def needs_sync(self, ecosystem: str) -> bool:
        """Return *True* if the index for *ecosystem* is stale or absent."""
        from backend.core.offline_index import index_status

        status = index_status(ecosystem)
        if status is None:
            return True
        try:
            updated = status.get("metadata", {}).get("updated_at", "")
            if not updated:
                return True
            updated_ts = time.mktime(time.strptime(updated, "%Y-%m-%dT%H:%M:%SZ"))
            return (time.time() - updated_ts) > self.update_interval
        except (ValueError, OSError):
            return True

    def package_count(self, ecosystem: str) -> int:
        """Return number of packages in the local index (0 if absent)."""
        from backend.core.offline_index import index_status

        status = index_status(ecosystem)
        return status.get("packages", 0) if status else 0

    # ------------------------------------------------------------------
    # Ecosystem-specific sync
    # ------------------------------------------------------------------

    async def sync_pypi(self) -> int:
        """Sync the PyPI index using the Simple API.

        Strategy: fetch the full package list from ``/simple/``,
        then lazily fetch JSON details for packages not yet cached.
        Returns the number of packages synced.
        """
        from backend.core.offline_index import create_or_update_index

        logger.info("Syncing PyPI index …")

        packages = await _fetch_pypi_package_list()
        if not packages:
            logger.warning("PyPI sync returned 0 packages — aborting")
            return 0

        # Check which packages are new or have new versions
        existing_pkgs = set()
        conn = _offline_conn("pypi")
        if conn:
            try:
                rows = conn.execute("SELECT name FROM packages").fetchall()
                existing_pkgs = {r["name"] for r in rows}
            except Exception:
                pass
            finally:
                conn.close()

        new_packages = [p for p in packages if p not in existing_pkgs]
        if not new_packages:
            logger.info("PyPI index already up to date (%d packages)", len(existing_pkgs))
            return 0

        # Batch-fetch new packages in parallel
        sem = asyncio.Semaphore(10)
        batch_size = 50
        total_synced = 0
        for i in range(0, len(new_packages), batch_size):
            batch = new_packages[i : i + batch_size]
            tasks = [_fetch_pypi_package_json(pkg, sem) for pkg in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            valid = [r for r in results if isinstance(r, dict)]
            if valid:
                inserted = create_or_update_index("pypi", valid)
                total_synced += inserted
            logger.debug(
                "PyPI sync batch %d/%d: %d packages inserted",
                i // batch_size + 1,
                (len(new_packages) + batch_size - 1) // batch_size,
                sum(1 for r in results if isinstance(r, dict)),
            )

        logger.info(
            "PyPI sync complete: %d new packages indexed (total %d)",
            total_synced,
            len(packages),
        )
        return total_synced

    async def sync_npm(self) -> int:
        """Sync the npm index using the ``_changes`` feed.

        Fetches the sequential changes feed at ``/-/v1/_changes``
        and adds/updates packages that have changed since last sync.
        """
        from backend.core.offline_index import create_or_update_index, index_status

        logger.info("Syncing npm index …")
        since = 0
        status = index_status("npm")
        if status:
            try:
                since = int(status.get("metadata", {}).get("changes_since", "0"))
            except (ValueError, TypeError):
                since = 0

        rows = await _fetch_npm_changes(since)
        if not rows:
            logger.info("npm changes feed returned no rows")
            return 0

        sem = asyncio.Semaphore(10)
        batch_size = 25
        total_synced = 0
        new_since = since
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            tasks = [_fetch_npm_package_json(row["id"], sem) for row in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            valid = [r for r in results if isinstance(r, dict)]
            if valid:
                total_synced += create_or_update_index("npm", valid)
            new_since = max(new_since, batch[-1].get("seq", 0))

        # Persist the changes seq for next incremental sync
        conn = _offline_conn("npm", create=True)
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

        logger.info(
            "npm sync complete: %d packages updated (changes_since=%d)", total_synced, new_since
        )
        return total_synced

    async def sync_crates(self) -> int:
        """Sync the crates.io index.

        Uses the crates.io Git index repo (``crates.io-index``).
        For environments without Git access, falls back to the API.
        """
        import subprocess

        from backend.core.offline_index import create_or_update_index

        logger.info("Syncing crates.io index …")
        index_dir = _crates_index_path()

        if not index_dir.exists():
            logger.info("Cloning crates.io-index Git repo (first sync) …")
            try:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--depth=1",
                        "https://github.com/rust-lang/crates.io-index",
                        str(index_dir),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError) as exc:
                logger.warning("Git clone failed (%s) — falling back to API", exc)
                return await self._sync_crates_api()
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

        # Walk the Git index directory structure
        pkgs_found = 0
        batch: list[dict] = []
        for letter_dir in sorted(index_dir.iterdir()):
            if not letter_dir.is_dir() or letter_dir.name.startswith("."):
                continue
            for crate_file in sorted(letter_dir.iterdir()):
                if crate_file.suffix != ".json":
                    continue
                try:
                    data = _parse_crate_index_file(crate_file)
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

        logger.info("crates.io sync complete: %d packages indexed", pkgs_found)
        return pkgs_found

    async def _sync_crates_api(self) -> int:
        """Fallback: sync crates via the crates.io API."""
        from backend.core.offline_index import create_or_update_index

        logger.info("Syncing crates.io via API …")
        url = "https://crates.io/api/v1/crates?page=1&per_page=100&sort=new"
        import aiohttp

        total = 0
        async with aiohttp.ClientSession() as session:
            for page in range(1, 51):
                page_url = f"https://crates.io/api/v1/crates?page={page}&per_page=100&sort=new"
                try:
                    async with session.get(page_url, headers={"User-Agent": "UDR/1.0"}) as resp:
                        if resp.status != 200:
                            break
                        data = await resp.json()
                        crates = data.get("crates", [])
                        if not crates:
                            break
                        batch = []
                        for c in crates:
                            batch.append(
                                {
                                    "name": c["id"],
                                    "versions": [],
                                }
                            )
                        if batch:
                            create_or_update_index("crates", batch)
                            total += len(batch)
                except Exception:
                    break
        logger.info("crates.io API sync complete: %d packages registered", total)
        return total

    async def sync(self, ecosystem: str) -> int:
        """Sync the index for *ecosystem*.

        Returns the number of packages updated.
        """
        eco = ecosystem.lower().strip()
        if eco == "pypi":
            return await self.sync_pypi()
        if eco == "npm":
            return await self.sync_npm()
        if eco == "crates":
            return await self.sync_crates()
        logger.warning("No local index support for ecosystem: %s", ecosystem)
        return 0


def get_local_index(ecosystem: str) -> LocalIndexManager | None:
    """Factory: return a ``LocalIndexManager`` for *ecosystem*, or ``None`` if unsupported.

    Only ``pypi``, ``npm``, and ``crates`` are supported.
    When ``ENABLE_LOCAL_INDEX`` is ``false``, returns ``None``.
    """
    if not _settings.ENABLE_LOCAL_INDEX:
        return None
    eco = ecosystem.lower().strip()
    if eco in ("pypi", "npm", "crates"):
        return LocalIndexManager()
    logger.debug("No local index support for ecosystem: %s", ecosystem)
    return None


# ======================================================================
# Private helpers  (per-ecosystem HTTP fetching)
# ======================================================================


def _offline_conn(ecosystem: str, create: bool = False) -> Any:
    """Open a connection to the offline index DB."""
    from backend.core.offline_index import _connect, _ensure_index

    if create:
        try:
            return _ensure_index(ecosystem)
        except Exception:
            return None
    try:
        return _connect(ecosystem)
    except Exception:
        return None


def _crates_index_path() -> Any:
    """Return path to the local crates.io-index Git checkout."""
    from pathlib import Path

    from backend.settings import LOCAL_INDEX_DIR

    return Path(LOCAL_INDEX_DIR) / "crates.io-index"


async def _fetch_pypi_package_list() -> list[str]:
    """Fetch all package names from PyPI Simple API."""
    import aiohttp

    url = "https://pypi.org/simple/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"Accept": "text/html"}) as resp:
                if resp.status != 200:
                    logger.warning("PyPI Simple API returned status %d", resp.status)
                    return []
                html = await resp.text()
    except Exception as exc:
        logger.warning("Failed to fetch PyPI package list: %s", exc)
        return []

    import re

    pkgs = re.findall(r'<a\s+href="([^"]+)"', html)
    return sorted(set(p.rstrip("/") for p in pkgs if p and not p.startswith("..")))


async def _fetch_pypi_package_json(package: str, sem: asyncio.Semaphore) -> dict | None:
    """Fetch full JSON metadata for a single PyPI package."""
    import aiohttp

    url = f"https://pypi.org/pypi/{package}/json"
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
        deps = info.get("requires_dist", [])
        try:
            release_date = files[0].get("upload_time")
        except (IndexError, KeyError):
            pass
        try:
            requires_python = files[0].get("requires_python")
        except (IndexError, KeyError):
            pass
        versions.append(
            {
                "version": ver_str,
                "release_date": release_date,
                "requires_python": requires_python,
                "dependencies": {"dependencies": {}} if not deps else _parse_pypi_deps(deps),
            }
        )
    return {
        "name": info.get("name", package),
        "versions": versions,
    }


def _parse_pypi_deps(requires_dist: list[str]) -> dict:
    """Parse PyPI ``requires_dist`` into ``{dependencies: {dep: spec}}``."""
    import re as _re

    deps: dict[str, str] = {}
    _pat = _re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9._\-]*)\s*([><=!~].+)?$")
    for entry in requires_dist:
        if not entry or ";" in entry:
            continue
        m = _pat.match(entry.strip())
        if m:
            name = m.group(1)
            spec = m.group(2) or "*"
            deps[name] = spec.strip()
    return {"dependencies": deps}


async def _fetch_npm_changes(since: int = 0) -> list[dict]:
    """Fetch the npm ``_changes`` feed."""
    import aiohttp

    url = f"https://registry.npmjs.org/-/v1/_changes?since={since}&limit=1000"
    try:
        async with aiohttp.ClientSession() as session, session.get(url) as resp:
            if resp.status != 200:
                logger.warning("npm _changes feed returned status %d", resp.status)
                return []
            return await resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch npm changes feed: %s", exc)
        return []


async def _fetch_npm_package_json(package: str, sem: asyncio.Semaphore) -> dict | None:
    """Fetch full metadata for a single npm package."""
    import aiohttp

    url = f"https://registry.npmjs.org/{package}"
    async with sem:
        try:
            async with aiohttp.ClientSession() as session, session.get(url) as resp:
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


def _parse_crate_index_file(crate_file: Any) -> dict | None:
    """Parse a single crate file from the crates.io-index Git repo."""
    import json

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
