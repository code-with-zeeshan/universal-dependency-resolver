"""Graceful shutdown infrastructure — signal handlers + context managers.

Usage::

    from backend.core.shutdown import register_signal_handlers, ShutdownFlag

    flag = ShutdownFlag()
    register_signal_handlers(flag)
    while flag.running:
        ...
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ShutdownFlag:
    """A shared flag that tells long-running operations to stop.

    Check ``flag.running`` at safe points in your operation loop.
    """

    def __init__(self):
        """Initialize the ShutdownFlag."""
        self._shutdown_requested = False

    @property
    def running(self) -> bool:
        """Return ``True`` while no shutdown has been requested."""
        return not self._shutdown_requested

    def request_shutdown(self):
        """Signal that a graceful shutdown has been requested."""
        self._shutdown_requested = True

    def reset(self):
        """Reset the shutdown flag to ``False``."""
        self._shutdown_requested = False


def register_signal_handlers(flag: ShutdownFlag):
    """Register SIGINT and SIGTERM handlers that set *flag*.

    In the API (asyncio event loop), uses ``loop.add_signal_handler``.
    In the CLI (sync), uses ``signal.signal``.
    Safe to call from non-main threads — silently no-ops.
    """

    async def _async_handler(sig: signal.Signals):
        logger.warning("Received signal %s — shutting down gracefully...", sig.name)
        flag.request_shutdown()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, ValueError, RuntimeError):
                loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(_async_handler(s)))
    except RuntimeError:
        # No running loop — CLI mode
        try:

            def _handler(sig, frame):
                logger.warning(
                    "Received signal %s — shutting down gracefully...", signal.Signals(sig).name
                )
                flag.request_shutdown()

            signal.signal(signal.SIGINT, _handler)
            signal.signal(signal.SIGTERM, _handler)
        except ValueError:
            pass  # Non-main thread


# ---------------------------------------------------------------------------
# Context managers for key resources
# ---------------------------------------------------------------------------


@contextmanager
def managed_temp_dir(prefix: str = "udr_"):
    """Context-managed temporary directory — deleted on exit."""
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix=prefix)
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class ManagedExecutor:
    """Context-managed ThreadPoolExecutor."""

    def __init__(self, max_workers: int | None = None):
        """Initialize the ManagedExecutor."""
        import concurrent.futures

        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

    def __enter__(self):
        """Return the underlying executor for use as a context manager."""
        return self._executor

    def __exit__(self, *args: object):
        """Shut down the executor on context exit."""
        self._executor.shutdown(wait=True)
        logger.debug("ThreadPoolExecutor shut down")

    def submit(self, fn, *args, **kwargs):
        """Submit a callable to the executor pool."""
        return self._executor.submit(fn, *args, **kwargs)
