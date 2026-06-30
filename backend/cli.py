"""
Backward-compat shim — delegates to backend/cli/ package.
All functionality lives in backend/cli/{main,shared,commands/}*.py
"""

from backend.cli import *  # noqa: F401, F403
from backend.cli import main, _build_parser  # noqa: F401, F403
