"""Wheel compatibility checking using ``packaging.tags``.

Determines whether a given Python wheel is compatible with a target
(OS, arch, Python version) using the standard ``packaging.tags`` module.
"""

from __future__ import annotations

import logging
import sys

from packaging.tags import Tag, compatible_tags, cpython_tags, sys_tags

logger = logging.getLogger(__name__)


def check_wheel_compatibility(
    wheel_tags: list[str],
    target_os: str | None = None,
    target_arch: str | None = None,
    target_python: str | None = None,
) -> bool:
    """Check if a wheel's tags are compatible with the target platform.

    *wheel_tags* — list of tag strings like ``"cp311-cp311-manylinux_2_17_x86_64"``.
    Returns ``True`` if at least one tag is compatible.
    """
    target_tags = _build_target_tags(target_os, target_arch, target_python)
    for tag_str in wheel_tags:
        parts = tag_str.split("-")
        if len(parts) < 3:
            continue
        tag = Tag(*parts[:3])
        if tag in target_tags:
            return True
    return False


def _build_target_tags(
    target_os: str | None,
    target_arch: str | None,
    target_python: str | None,
) -> set[Tag]:
    """Build the set of compatible tags for the target platform.

    Uses the host platform when a target field is ``None``.
    """
    if target_os is None and target_arch is None and target_python is None:
        return set(sys_tags())

    pyver = _resolve_python_version(target_python)
    interps = _resolve_interp(target_python)
    abi = _resolve_abi(target_python)
    plat = _resolve_platform(target_os, target_arch)

    tags: set[Tag] = set()

    # CPython-specific tags
    if interps and abi and plat:
        tags.update(_safe_cpython_tags(pyver, abi, [plat]))

    # Compatible tags (broader matching)
    if interps and abi and plat:
        tags.update(compatible_tags(pyver, interps[0], [plat]))

    # Generic platform tags
    if plat:
        for i in interps or ["py3"]:
            for a in abi or ["none"]:
                tags.add(Tag(i, a, plat))

    return tags or set(sys_tags())


def _safe_cpython_tags(
    pyver: tuple[int, int], abi: list[str], platforms: list[str] | None
) -> set[Tag]:
    try:
        return set(cpython_tags(pyver, abi, platforms))
    except Exception:
        return set()


def _resolve_python_version(python_ver: str | None) -> tuple[int, int]:
    if not python_ver:
        return (sys.version_info.major, sys.version_info.minor)
    ver = python_ver.replace("python", "").strip()
    parts = ver.split(".")
    if len(parts) >= 2:
        return (int(parts[0]), int(parts[1]))
    return (int(parts[0]), 0)


def _resolve_interp(python_ver: str | None) -> list[str]:
    if not python_ver:
        return _current_interp()
    ver = python_ver.replace("python", "").strip()
    parts = ver.split(".")
    if len(parts) >= 2:
        major, minor = parts[0], parts[1]
        return [f"cp{major}{minor}", f"py{major}{minor}", f"py{major}"]
    return [f"cp{ver}", f"py{ver}"]


def _current_interp() -> list[str]:
    ver = sys.version_info
    return [f"cp{ver.major}{ver.minor}", f"py{ver.major}{ver.minor}", f"py{ver.major}"]


def _resolve_abi(python_ver: str | None) -> list[str]:
    if not python_ver:
        return _current_abi()
    ver = python_ver.replace("python", "").strip()
    parts = ver.split(".")
    if len(parts) >= 2:
        return [f"cp{parts[0]}{parts[1]}", f"cp{parts[0]}{parts[1]}d", "none"]
    return ["none"]


def _current_abi() -> list[str]:
    ver = sys.version_info
    return [f"cp{ver.major}{ver.minor}", f"cp{ver.major}{ver.minor}d", "none"]


def _resolve_platform(target_os: str | None, target_arch: str | None) -> str | None:
    if not target_os and not target_arch:
        return None

    _os = (target_os or "linux").lower().replace("macos", "macosx").replace("darwin", "macosx")
    _arch = (target_arch or "x86_64").lower()
    _arch = _arch.replace("amd64", "x86_64").replace("arm64", "aarch64")

    if _os == "linux":
        return f"manylinux_2_17_{_arch}"
    if _os == "macosx":
        return f"macosx_10_9_{_arch}"
    if _os in ("windows", "win32"):
        return f"win_{_arch}"
    return f"{_os}_{_arch}"
