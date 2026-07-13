"""Backward-compat shim — delegates to backend/cli/ package.
All functionality lives in backend/cli/{main,shared,commands/}*.py.
"""

from backend.cli import _build_parser, main  # noqa: F401
