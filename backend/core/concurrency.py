"""Centralized :class:`asyncio.Semaphore` factory.

All semaphores across the codebase should be created through
:func:`get_semaphore` so that concurrency limits are consistent,
observable, and configurable from a single place.

Usage::

    from backend.core.concurrency import get_semaphore

    sem = get_semaphore("npm", concurrency=10)
    async with sem:
        ...
"""

from __future__ import annotations

import asyncio

_registry: dict[str, asyncio.Semaphore] = {}


def get_semaphore(name: str, concurrency: int = 10) -> asyncio.Semaphore:
    """Get or create a named :class:`asyncio.Semaphore`.

    Semaphores are cached globally by *name* — repeated calls return
    the same instance.  This means all callers sharing the same name
    share the same concurrency limit.

    Parameters
    ----------
    name:
        Logical name (e.g. ``"npm"``, ``"docker"``, ``"cli_fetch"``).
        Used as the cache key — pick a short, unique identifier.
    concurrency:
        Maximum number of concurrent operations allowed.  Should be
        sourced from :mod:`backend.settings` when a dedicated setting
        exists (e.g. ``NPM_CONCURRENCY``); otherwise pass a sensible
        literal default.
    """
    if name not in _registry:
        _registry[name] = asyncio.Semaphore(concurrency)
    return _registry[name]


def reset_semaphores() -> None:
    """Clear all cached semaphores.

    Intended for test teardown to avoid cross-test leaks.
    """
    _registry.clear()
