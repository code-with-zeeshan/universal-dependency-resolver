"""Offline SQLite index for local package resolution.

Each ecosystem has its own SQLite database at ``~/.cache/udr/indexes/{eco}.db``.

Schema
------
packages
    Core package registry.  One row per known package.
versions
    Every published version for each package, with dependencies stored
    as a JSON blob so the SAT solver can reconstruct the graph offline.
index_metadata
    Build timestamp, version count, index format version.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

INDEX_DIR = Path.home() / ".cache" / "udr" / "indexes"
INDEX_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS packages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    ecosystem   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id      INTEGER NOT NULL REFERENCES packages(id),
    version         TEXT    NOT NULL,
    release_date    TEXT,
    requires_python TEXT,
    dependencies    TEXT,
    UNIQUE(package_id, version)
);

CREATE TABLE IF NOT EXISTS index_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_packages_name ON packages(name);
CREATE INDEX IF NOT EXISTS idx_versions_pkg   ON versions(package_id);
"""

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def _db_path(ecosystem: str) -> Path:
    eco = ecosystem.lower().replace("-", "_")
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    return INDEX_DIR / f"{eco}.db"


def _connect(ecosystem: str) -> sqlite3.Connection | None:
    path = _db_path(ecosystem)
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.debug("Failed to open index for %s: %s", ecosystem, e)
        return None


def _ensure_index(ecosystem: str) -> sqlite3.Connection:
    """Open index DB, creating it with schema if needed."""
    path = _db_path(ecosystem)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    return conn


# ---------------------------------------------------------------------------
# Query API  (used by data aggregator when offline)
# ---------------------------------------------------------------------------


def package_exists(ecosystem: str, package_name: str) -> bool:
    """Return *True* if *package_name* is in the offline index."""
    conn = _connect(ecosystem)
    if conn is None:
        return False
    try:
        row = conn.execute("SELECT 1 FROM packages WHERE name = ?", (package_name,)).fetchone()
        return row is not None
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def get_package_info(ecosystem: str, package_name: str) -> dict[str, Any] | None:
    """Return a dict matching the format the data aggregator expects.

    Keys: ``name``, ``version``, ``versions``, ``dependencies``.
    """
    _parse_version_available = False
    try:
        from packaging.version import parse as _parse_version

        _parse_version_available = True
    except ImportError:
        _parse_version = None  # type: ignore[assignment]

    conn = _connect(ecosystem)
    if conn is None:
        return None
    try:
        pkg_row = conn.execute("SELECT id FROM packages WHERE name = ?", (package_name,)).fetchone()
        if pkg_row is None:
            return None

        version_rows = conn.execute(
            "SELECT version, release_date, requires_python, dependencies "
            "FROM versions WHERE package_id = ?",
            (pkg_row["id"],),
        ).fetchall()

        if not version_rows:
            return None

        versions: list[dict[str, Any]] = []
        deps: dict[str, str] = {}

        sorted_rows = sorted(
            version_rows,
            key=lambda r: (
                _parse_version(r["version"]) if _parse_version_available else r["version"]
            ),
            reverse=True,
        )
        latest = sorted_rows[0]["version"]

        for vr in sorted_rows:
            versions.append({"version": vr["version"]})
            if vr["version"] == latest and vr["dependencies"]:
                try:
                    parsed = json.loads(vr["dependencies"])
                    if isinstance(parsed, dict):
                        deps.update(parsed)
                except (json.JSONDecodeError, TypeError):
                    pass

        return {
            "name": package_name,
            "version": latest,
            "versions": versions,
            "dependencies": {"dependencies": deps} if deps else {},
        }
    except sqlite3.Error as e:
        logger.debug("Index query error for %s/%s: %s", ecosystem, package_name, e)
        return None
    finally:
        conn.close()


def get_package_versions(ecosystem: str, package_name: str) -> list[dict[str, str]]:
    """Return ``[{"version": str}, ...]``."""
    info = get_package_info(ecosystem, package_name)
    return info.get("versions", []) if info else []


# ---------------------------------------------------------------------------
# Index status
# ---------------------------------------------------------------------------


def index_status(ecosystem: str) -> dict[str, Any] | None:
    """Return metadata about a local index, or *None* if absent."""
    conn = _connect(ecosystem)
    if conn is None:
        return None
    try:
        pkg_count = conn.execute("SELECT COUNT(*) AS c FROM packages").fetchone()["c"]
        ver_count = conn.execute("SELECT COUNT(*) AS c FROM versions").fetchone()["c"]
        meta = dict(conn.execute("SELECT key, value FROM index_metadata").fetchall())
        path = _db_path(ecosystem)
        return {
            "ecosystem": ecosystem,
            "path": str(path),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "packages": pkg_count,
            "versions": ver_count,
            "metadata": meta,
        }
    except sqlite3.Error as e:
        logger.debug("Index status error for %s: %s", ecosystem, e)
        return None
    finally:
        conn.close()


def list_indexes() -> list[str]:
    """Return list of ecosystem names that have a local index."""
    if not INDEX_DIR.exists():
        return []
    return sorted(p.stem.replace("_", "-") for p in INDEX_DIR.iterdir() if p.suffix == ".db")


# ---------------------------------------------------------------------------
# Index builder  (used by ``udr index build``)
# ---------------------------------------------------------------------------


def create_or_update_index(
    ecosystem: str,
    packages: list[dict[str, Any]],
) -> int:
    """Insert/update *packages* into the offline index.

    Each *packages* dict should have:
      ``name`` (str)
      ``versions`` (list of dicts with ``version``, ``release_date``,
                    ``requires_python``, ``dependencies``)

    Returns the number of packages inserted/updated.
    """
    conn = _ensure_index(ecosystem)
    count = 0
    try:
        for pkg in packages:
            name = pkg.get("name", "").strip()
            if not name:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO packages (name, ecosystem) VALUES (?, ?)",
                (name, ecosystem),
            )
            row = conn.execute("SELECT id FROM packages WHERE name = ?", (name,)).fetchone()
            if row is None:
                continue
            pkg_id = row["id"]

            for ver in pkg.get("versions", []):
                v = ver.get("version", "").strip()
                if not v:
                    continue
                deps_json = json.dumps(ver.get("dependencies", {}), default=str)
                conn.execute(
                    """INSERT OR REPLACE INTO versions
                       (package_id, version, release_date, requires_python, dependencies)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        pkg_id,
                        v,
                        ver.get("release_date"),
                        ver.get("requires_python"),
                        deps_json,
                    ),
                )
            count += 1

        conn.execute(
            "INSERT OR REPLACE INTO index_metadata (key, value) VALUES (?, ?)",
            ("index_version", str(INDEX_VERSION)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO index_metadata (key, value) VALUES (?, ?)",
            ("updated_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.error("Index build error for %s: %s", ecosystem, e)
        conn.rollback()
        raise
    finally:
        conn.close()
    return count
