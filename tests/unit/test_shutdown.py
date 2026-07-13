"""Regression tests for graceful shutdown module."""

from __future__ import annotations

import os
import signal
import tempfile
from pathlib import Path

import pytest

from backend.core.shutdown import (
    ManagedExecutor,
    ShutdownFlag,
    managed_temp_dir,
    register_signal_handlers,
)


class TestShutdownFlag:
    def test_starts_running(self):
        flag = ShutdownFlag()
        assert flag.running is True

    def test_request_shutdown(self):
        flag = ShutdownFlag()
        flag.request_shutdown()
        assert flag.running is False

    def test_reset(self):
        flag = ShutdownFlag()
        flag.request_shutdown()
        flag.reset()
        assert flag.running is True

    def test_multiple_requests(self):
        flag = ShutdownFlag()
        flag.request_shutdown()
        flag.request_shutdown()  # Should not raise
        assert flag.running is False

    def test_independent_flags(self):
        f1 = ShutdownFlag()
        f2 = ShutdownFlag()
        f1.request_shutdown()
        assert f1.running is False
        assert f2.running is True


class TestRegisterSignalHandlers:
    def test_does_not_crash_in_non_main_thread(self):
        """Must be safe to call from any thread/context."""
        flag = ShutdownFlag()
        # Should not raise ValueError or RuntimeError
        register_signal_handlers(flag)

    def test_flag_not_set_by_default(self):
        flag = ShutdownFlag()
        assert flag.running is True
        register_signal_handlers(flag)
        assert flag.running is True  # No signal sent

    def test_respects_already_stopped_flag(self):
        flag = ShutdownFlag()
        flag.request_shutdown()
        register_signal_handlers(flag)
        assert flag.running is False


class TestManagedTempDir:
    def test_creates_and_cleans_up(self):
        path = None
        with managed_temp_dir("test_") as tmp:
            path = tmp
            assert os.path.isdir(tmp)
            assert Path(tmp).name.startswith("test_")
        assert not os.path.exists(path)

    def test_works_on_exception(self):
        path = None
        try:
            with managed_temp_dir("test_") as tmp:
                path = tmp
                raise ValueError("test error")
        except ValueError:
            pass
        assert path is not None
        assert not os.path.exists(path)

    def test_empty_prefix(self):
        with managed_temp_dir() as tmp:
            assert os.path.isdir(tmp)

    def test_multiple_nested(self):
        paths = []
        with managed_temp_dir("outer") as outer:
            paths.append(outer)
            with managed_temp_dir("inner") as inner:
                paths.append(inner)
                assert os.path.isdir(outer)
                assert os.path.isdir(inner)
        for p in paths:
            assert not os.path.exists(p)


class TestManagedExecutor:
    def test_executes_function(self):
        with ManagedExecutor(max_workers=2) as ex:
            fut = ex.submit(lambda: 42)
            assert fut.result() == 42

    def test_shuts_down_on_exit(self):
        ex = ManagedExecutor(max_workers=1)
        with ex as executor:
            assert executor is not None
        # Should not hang

    def test_multiple_submissions(self):
        with ManagedExecutor(max_workers=4) as ex:
            futs = [ex.submit(lambda i=i: i * 2, i) for i in range(10)]
            results = [f.result() for f in futs]
        assert results == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]
