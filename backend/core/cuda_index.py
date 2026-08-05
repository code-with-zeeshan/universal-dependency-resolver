"""PyTorch CUDA-index-aware version selection support.

PyPI's torch (and torchvision/torchaudio/etc.) publishes one wheel per
version whose CUDA is baked into its nvidia-*-cuXX dependency package names -
there are no +cu local-version labels on PyPI.  The actual per-CUDA builds
live on the PyTorch wheel index at https://download.pytorch.org/whl/ where
each subdirectory (cu118, cu121, cu126, cu128, cpu, ...) is a PEP 503
"simple" index of wheels tagged with a +cuXXX local version.

This module lets the resolver map a requested CUDA version (12.1) to the
matching index tag (cu121), fetch which base versions actually ship a wheel
for that tag, and rewrite a resolved base version to its +cuXXX form - the
"accurate CUDA-tagged resolution" that plain PyPI data cannot express.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

INDEX_BASE_URL = "https://download.pytorch.org/whl"

#: Local-version fragment in a wheel name, e.g. ``%2Bcu121`` (URL-encoded '+')
#: or a literal ``+cu121``.
_CU_LOCAL_RE = re.compile(r"(?:\+|\%2B)cu\d+", re.IGNORECASE)

#: Packages whose CUDA builds are published on the pytorch index rather than
#: on PyPI.  These get CUDA-index-aware candidate restriction + +cuXXX rewriting.
PYTORCH_FAMILY_PACKAGES: frozenset[str] = frozenset(
    {
        "torch",
        "torchaudio",
        "torchvision",
        "torchtext",
        "torchdata",
        "torchrec",
        "torchtune",
        "torchcsprng",
        "torchdistx",
        "torchserve",
        "torchmetrics",
        "torchao",
        "torchcodec",
        "torchcomms",
        "torch-tensorrt",
        "torch-tb-profiler",
        "triton",
        "pytorch-triton",
        "pytorch-triton-rocm",
        "pytorch-triton-xpu",
        "xformers",
    }
)

_DEFAULT_FETCH_TIMEOUT = 8.0

#: In-memory cache: ``(pkg, tag) -> {"fetched_at": float, "windows": dict}``
_index_cache: dict[tuple[str, str], dict[str, Any]] = {}
_INDEX_CACHE_TTL = 3600.0

#: Hard cap on the number of distinct base versions to consider per package -
#: torch has ~30/tag, which is fine, but guard against pathological indexes.
_MAX_INDEX_BASE_VERSIONS = 200


def normalize_cuda_tag(cuda: str) -> str:
    """Map a user CUDA version string to the pytorch index tag.

    ``"12.1"`` -> ``"cu121"``, ``"11.8"`` -> ``"cu118"``, ``"13.0"`` -> ``"cu130"``.
    Strips dots and any existing ``cu`` prefix, then prefixes ``cu``.
    """
    cleaned = re.sub(r"[^0-9.]", "", cuda)
    if not cleaned:
        return ""
    digits = cleaned.replace(".", "")
    if not digits:
        return ""
    return "cu" + digits


def is_pytorch_family(pkg_name: str) -> bool:
    """Return True for packages whose CUDA builds live on the pytorch index."""
    return (pkg_name or "").lower() in PYTORCH_FAMILY_PACKAGES


def parse_simple_index(text: str) -> dict[str, str]:
    """Parse a pytorch simple-index into {base_version: full_version}.

    Each anchor href/text contains wheel filenames like
    ``torch-2.1.0%2Bcu121-cp310-cp310-linux_x86_64.whl``.  We extract the version
    field between the package name and the python tag, unescape ``%2B`` -> ``+``,
    then split into ``(base_version, full_version_with_local)``.  A torch-family
    base version like ``2.1.0`` may appear under a ``+cu121`` (CUDA) and a plain
    CPU wheel; both map back to the same base key.  Returns a dict so callers can
    rewrite a resolved base version to its CUDA-tagged form.
    """
    out: dict[str, str] = {}
    # anchor hrefs (relative ``torch-2.1.0%2Bcu121-...whl`` or full CDN URLs).
    for href in re.findall(r"href=\"([^\"]+\.whl[^\"]*)\"", text, re.IGNORECASE):
        file_uri = href.partition("#")[0]
        file = file_uri.rsplit("/", 1)[-1]
        _name_part, _, rest = file.partition("-")
        if not rest:
            continue
        version_part, _, _ = rest.partition("-")
        if not version_part:
            continue
        # unescape %2B -> +
        version = version_part.replace("%2B", "+")
        base = _CU_LOCAL_RE.sub("", version).lstrip("-")
        if not base:
            continue
        # Some wheels carry no ^+cu local (CPU) - then full == base already.
        full = version
        out[base] = full
    return out


def _fetch_simple_index_sync(pkg: str, tag: str, timeout: float) -> str:
    url = f"{INDEX_BASE_URL}/{tag}/{pkg}/"
    req = urllib.request.Request(url, headers={"User-Agent": "udr/cuda-index"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_index_versions(
    pkg: str, cuda_tag: str, *, timeout: float | None = None
) -> dict[str, str]:
    """Return ``{base_version: full_cu_version}`` for ``pkg`` on ``cuda_tag``'s index.

    Caches per ``(pkg, tag)`` for ``_INDEX_CACHE_TTL`` seconds.  On any network
    or parse failure, returns ``{}`` (callers should degrade gracefully - the
    traditional PyPI/version-suffix logic remains the fallback).
    """
    key = (pkg.lower(), cuda_tag)
    now = time.monotonic()
    cached = _index_cache.get(key)
    if cached and (now - cached["fetched_at"]) < _INDEX_CACHE_TTL:
        return dict(cached["windows"])

    default_timeout = timeout if timeout is not None else _DEFAULT_FETCH_TIMEOUT
    max_versions = _MAX_INDEX_BASE_VERSIONS
    try:
        text = _fetch_simple_index_sync(pkg, cuda_tag, default_timeout)
        windows = parse_simple_index(text)
    except Exception as exc:
        logger.warning("cuda-index fetch failed for %s/%s: %s", pkg, cuda_tag, exc)
        return {}

    # Trim to a sane upper bound of base versions to keep memory bounded.
    windows = dict(list(windows.items())[:max_versions])
    _index_cache[key] = {"fetched_at": now, "windows": dict(windows)}
    return dict(windows)


async def fetch_index_versions_async(
    pkg: str, cuda_tag: str, *, timeout: float | None = None
) -> dict[str, str]:
    """Async wrapper around ``fetch_index_versions`` (runs the blocking IO in a thread)."""
    return await asyncio.to_thread(fetch_index_versions, pkg, cuda_tag, timeout=timeout)


def restrict_to_index_versions(
    available_versions: list[str],
    pkg_name: str,
    cuda_tag: str,
    *,
    timeout: float | None = None,
) -> list[str]:
    """Filter *available_versions* to base versions that ship a wheel on the CUDA index.

    Only applies to pytorch-family packages; for everything else (or on fetch
    failure) returns the input unchanged.  This is the mechanism that stops the
    solver from picking torch 2.9.1 for a ``cu121`` request — the cu121 index
    only carries up to 2.5.1.
    """
    if not is_pytorch_family(pkg_name):
        return available_versions
    windows = fetch_index_versions(pkg_name, cuda_tag, timeout=timeout)
    if not windows:
        return available_versions
    restricted = [v for v in available_versions if v in windows]
    if not restricted:
        return available_versions
    return restricted


def clear_index_cache() -> None:
    """Drop the in-memory index cache (used by tests)."""
    _index_cache.clear()
