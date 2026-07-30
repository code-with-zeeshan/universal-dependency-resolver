"""Conftest for unit tests — reduce Hypothesis max_examples for speed."""

import pytest_asyncio

from hypothesis import settings
from backend.core.cache import cache_manager

settings.register_profile("ci", max_examples=100)
settings.register_profile("dev", max_examples=30)
settings.load_profile("dev")


@pytest_asyncio.fixture(autouse=True)
async def _clear_cache():
    """Prevent @cached cross-contamination between tests.

    The global ``cache_manager`` singleton persists across tests.  Without
    clearing it, a ``@cached`` result from test *A* may be returned to test
    *B* (same function + same argument — only *self* differs, and CPython may
    reuse the same memory address after GC).
    """
    await cache_manager.clear_all()
