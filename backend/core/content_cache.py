"""ContentAddressedCache — immutable blob storage keyed by SHA256 content hash.

Structure
---------
``~/.cache/udr/cac/index.json`` — flat dict of
``{external_key: {hash, ttl, created}}``.
``~/.cache/udr/cac/blobs/{prefix}/{hash}.json`` — one file per content blob.

Benefits over a conventional key-value cache
---------------------------------------------
* Integrity: the key is the hash of the content — every read verifies
  ``sha256(stored_bytes) == key``, detecting silent corruption.
* Deduplication: two external keys pointing to identical data share one
  blob on disk.
* GC: orphaned blobs (unreferenced by any key in the index) can be
  collected lazily.

Integration
-----------
Callers should use the :meth:`get` / :meth:`set` / :meth:`delete` interface,
which is deliberately compatible with :class:`~backend.core.cache.DictCache`::

    from backend.core.content_cache import content_cache

    data = await content_cache.get("my:cache:key")
    if data is None:
        data = await fetch_expensive_data()
        await content_cache.set("my:cache:key", data, ttl=3600)
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CAC_DIR = Path.home() / ".cache" / "udr" / "cac"
_BLOBS_DIR = _CAC_DIR / "blobs"
_INDEX_PATH = _CAC_DIR / "index.json"
_DEFAULT_TTL = 3600  # 1 hour

# Sentinel for "use the default TTL" (must be defined before class body)
_UNSET = object()

# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

_JSON_OPTS = {"sort_keys": True, "default": str, "ensure_ascii": False}


def _to_json_bytes(value: Any) -> bytes:
    return json.dumps(value, **_JSON_OPTS).encode("utf-8")


def _from_json_bytes(raw: bytes) -> Any:
    return json.loads(raw.decode("utf-8"))


def _content_hash(data: bytes) -> str:
    """Return the SHA-256 hex digest of *data*."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# ContentAddressedCache
# ---------------------------------------------------------------------------


class ContentAddressedCache:
    """Immutable, content-addressed blob cache with on-disk persistence.

    Parameters
    ----------
    cache_dir:
        Root directory for the cache.  Defaults to
        ``~/.cache/udr/cac``.
    default_ttl:
        Default TTL in seconds when ``set()`` is called without an
        explicit *ttl*.  ``None`` means no expiry.

    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        default_ttl: int | None = _DEFAULT_TTL,
    ) -> None:
        self._root = Path(cache_dir) if cache_dir else _CAC_DIR
        self._blobs = self._root / "blobs"
        self._index_path = self._root / "index.json"
        self._default_ttl = default_ttl

        self._index: dict[str, dict[str, Any]] = {}
        self._dirty = False
        self._ensure_dirs()
        self._load_index()

    # ---- public API -------------------------------------------------------

    async def get(self, key: str) -> Any | None:
        """Retrieve a value by its external *key*.

        Returns ``None`` when the key does not exist, has expired, or
        the stored blob fails integrity verification.
        """
        entry = self._get_index_entry(key)
        if entry is None:
            return None

        blob_hash: str = entry["hash"]
        blob_bytes = self._read_blob(blob_hash)
        if blob_bytes is None:
            # Blob missing — remove dangling index entry
            await self.delete(key)
            return None

        # Integrity check: recompute hash
        if _content_hash(blob_bytes) != blob_hash:
            logger.warning("Content cache integrity fail for key=%s hash=%s", key, blob_hash)
            await self.delete(key)
            return None

        try:
            return _from_json_bytes(blob_bytes)
        except Exception:
            logger.warning("Content cache deserialisation fail for key=%s", key, exc_info=True)
            await self.delete(key)
            return None

    async def set(self, key: str, value: Any, ttl: int | None = _UNSET) -> None:
        """Store *value* addressed by external *key*.

        If the serialised content is identical to an existing blob, the
        existing blob is reused (deduplication).
        """
        if ttl is _UNSET:
            ttl = self._default_ttl

        blob_bytes = _to_json_bytes(value)
        blob_hash = _content_hash(blob_bytes)

        # Write blob (no-op if already exists)
        self._write_blob(blob_hash, blob_bytes)

        # Update index
        created = time.time()
        expiry = (created + ttl) if ttl is not None else None
        self._index[key] = {
            "hash": blob_hash,
            "created": created,
            "ttl": ttl,
            "expiry": expiry,
        }
        self._dirty = True
        self._save_index()

    async def delete(self, key: str) -> None:
        """Remove *key* from the index.

        .. note:: The blob is **not** deleted immediately; unreferenced
           blobs are cleaned up by :meth:`gc`.
        """
        if key in self._index:
            del self._index[key]
            self._dirty = True
            self._save_index()

    async def clear(self) -> None:
        """Remove all index entries and blob files."""
        self._index.clear()
        self._dirty = True
        self._save_index()
        self._remove_blob_dir()

    async def gc(self) -> int:
        """Garbage-collect orphaned blobs.

        Returns the number of blobs removed.
        """
        referenced: set[str] = {e["hash"] for e in self._index.values()}
        blobs_dir = self._blobs
        if not blobs_dir.is_dir():
            return 0

        removed = 0
        for prefix_dir in list(blobs_dir.iterdir()):
            if not prefix_dir.is_dir():
                continue
            for blob_file in list(prefix_dir.iterdir()):
                blob_hash = blob_file.stem  # filename without .json
                if blob_hash not in referenced:
                    try:
                        blob_file.unlink()
                        removed += 1
                    except OSError:
                        pass
            # Remove empty prefix dirs
            try:
                if not any(prefix_dir.iterdir()):
                    prefix_dir.rmdir()
            except OSError:
                pass

        if removed:
            logger.info("Content cache GC removed %d orphaned blobs", removed)
        return removed

    async def flush(self) -> None:
        """Flush index to disk immediately."""
        self._save_index()

    async def close(self) -> None:
        """Flush and release resources."""
        self._save_index()

    # ---- internal helpers -------------------------------------------------

    def _ensure_dirs(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._blobs.mkdir(parents=True, exist_ok=True)

    def _blob_path(self, blob_hash: str) -> Path:
        """Return the on-disk path for a blob.

        Uses a two-character prefix directory to avoid too many files in
        a single directory (same scheme as git objects).
        """
        prefix = blob_hash[:2]
        return self._blobs / prefix / f"{blob_hash}.json"

    def _write_blob(self, blob_hash: str, data: bytes) -> None:
        """Atomically write *data* to the blob store."""
        dest = self._blob_path(blob_hash)
        if dest.is_file():
            return  # Already exists — deduplication
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        try:
            tmp.write_bytes(data)
            tmp.rename(dest)
        except Exception:
            with contextlib.suppress(Exception):
                tmp.unlink(missing_ok=True)
            raise

    def _read_blob(self, blob_hash: str) -> bytes | None:
        """Read blob bytes from disk, or ``None`` if missing."""
        dest = self._blob_path(blob_hash)
        try:
            return dest.read_bytes()
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.debug("Failed to read blob %s: %s", blob_hash, exc)
            return None

    def _remove_blob_dir(self) -> None:
        """Remove the entire blob directory tree."""
        try:
            if self._blobs.is_dir():
                shutil.rmtree(self._blobs)
                self._blobs.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.debug("Failed to remove blob dir: %s", exc)

    # ---- index management -------------------------------------------------

    def _load_index(self) -> None:
        """Load the index from disk."""
        try:
            if self._index_path.is_file():
                raw = self._index_path.read_bytes()
                self._index = json.loads(raw.decode("utf-8"))
                # Evict expired entries
                now = time.time()
                expired = [
                    k for k, v in self._index.items() if v.get("expiry") and v["expiry"] <= now
                ]
                for k in expired:
                    del self._index[k]
                if expired:
                    self._dirty = True
        except Exception as exc:
            logger.debug("Content cache index load failed: %s", exc)
            self._index = {}

    def _save_index(self) -> None:
        """Save the index to disk (synchronous)."""
        if not self._dirty:
            return
        try:
            raw = json.dumps(self._index, **_JSON_OPTS).encode("utf-8")
            tmp = self._index_path.with_suffix(".tmp")
            tmp.write_bytes(raw)
            tmp.rename(self._index_path)
            self._dirty = False
        except Exception as exc:
            logger.debug("Content cache index save failed: %s", exc)

    def _get_index_entry(self, key: str) -> dict | None:
        """Return the index entry for *key*, or ``None`` if missing/expired."""
        entry = self._index.get(key)
        if entry is None:
            return None
        expiry = entry.get("expiry")
        if expiry and time.time() > expiry:
            del self._index[key]
            self._dirty = True
            self._save_index()
            return None
        return entry


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

content_cache = ContentAddressedCache()
