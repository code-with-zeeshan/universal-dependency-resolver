#!/usr/bin/env python3
"""Check architecture import rules are NOT violated.

Rules (from AGENTS.md):
  orchestrator/ → core/, data_sources/  (no cli, no api)
  cli/          → orchestrator/, core/ (no api)
  api/          → orchestrator/, core/ (no cli)
  core/         → zero knowledge of cli, api, desktop
  Desktop       → HTTP only (zero Python imports)
  settings/, utils/ → always allowed (infra)

Usage:
    python scripts/check_arch_imports.py
    # Returns exit code 0 if clean, 1 if violations found.
"""

import ast
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"

# --- rule definition ---
# Each rule: from_layer -> [forbidden_import_prefixes]
# "layer" = the first path component after "backend/"

RULES: dict[str, list[str]] = {
    "orchestrator": ["cli", "api", "desktop"],
    "cli": ["api", "desktop"],
    "api": ["cli", "desktop"],
    "data_sources": ["cli", "api", "desktop"],
    "core": ["cli", "api", "desktop", "data_sources"],
    "database": ["cli", "api", "desktop"],  # strict: DB should not know about layers above
}

# Files that are explicitly exempted
EXEMPTED_FILES: set[str] = {
    # serve command wraps FastAPI app — deployment concern, accepted
    "cli/commands/serve.py",
    # __init__.py may re-export across layers (accepted by architecture audit)
    "backend/__init__.py",
    # entry point shims (accepted by architecture audit)
    "cli.py",
    "run.py",
}

# Imports that are always OK (stdlib, third-party, or infra)
ALWAYS_OK = {
    "os",
    "sys",
    "re",
    "json",
    "pathlib",
    "typing",
    "logging",
    "abc",
    "dataclasses",
    "enum",
    "functools",
    "itertools",
    "collections",
    "datetime",
    "math",
    "copy",
    "hashlib",
    "inspect",
    "warnings",
    "asyncio",
    "contextlib",
    "importlib",
    "pkgutil",
    "platform",
    "subprocess",
    "tempfile",
    "shutil",
    "io",
    "textwrap",
    "uuid",
    "base64",
    "ssl",
    "http",
    "urllib",
    "email",
    "decimal",
    "fractions",
    "random",
    "statistics",
    "string",
    "struct",
    "time",
    "zoneinfo",
    "graphlib",
    "concurrent",
    "multiprocessing",
    "threading",
    "pickle",
    "shelve",
    "dbm",
    "sqlite3",
    "configparser",
    "argparse",
    "getopt",
    "optparse",
    "doctest",
    "unittest",
    "pytest",  # testing
}

# Third-party packages that are always OK
ALWAYS_OK_THIRD_PARTY = {
    "z3",
    "packaging",
    "yaml",
    "tomli",
    "tomllib",
    "aiohttp",
    "requests",
    "fastapi",
    "uvicorn",
    "pydantic",
    "sqlalchemy",
    "alembic",
    "sentry_sdk",
    "prometheus_client",
    "pkg_resources",
    "importlib_metadata",
    "pubgrub_py",
    "pubgrub",
    "hypothesis",
    "pytest",
}

# Actual imports found in tests that violate but are for testing purposes
TESTING_LAYER_ALLOWED = {"cli": {"api"}, "api": {"cli"}}


def _get_layer(filepath: Path) -> str | None:
    """Determine the architecture layer from a file path."""
    rel = filepath.relative_to(BACKEND.parent)  # relative to repo root
    parts = rel.parts
    if len(parts) < 2 or parts[0] != "backend":
        return None
    return parts[1]  # e.g. "cli", "api", "core", "orchestrator"


def _is_exempted(filepath: Path) -> bool:
    rel = str(filepath.relative_to(BACKEND.parent))
    for ex in EXEMPTED_FILES:
        if rel == ex or rel.endswith("/" + ex):
            return True
    return False


def _is_test_file(filepath: Path) -> bool:
    rel = str(filepath.relative_to(BACKEND.parent))
    return "/tests/" in rel or rel.startswith("tests/") or filepath.name.startswith("test_")


def _normalize_import(module: str) -> str:
    """Get the top-level package of a dotted import."""
    return module.split(".")[0]


def _check_file(filepath: Path) -> list[str]:
    """Check a single file for architecture import violations."""
    violations: list[str] = []
    layer = _get_layer(filepath)
    if layer is None or layer not in RULES:
        return violations

    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception:
        return violations

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = _normalize_import(alias.name)
                if top in ALWAYS_OK or top in ALWAYS_OK_THIRD_PARTY:
                    continue
                if _is_test_file(filepath) and _check_test_allowance(layer, top):
                    continue
                if top in RULES.get(layer, []):
                    violations.append(
                        f"{filepath}: imports {alias.name} (layer={layer}, forbidden={top})"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            top = _normalize_import(node.module)
            if top in ALWAYS_OK or top in ALWAYS_OK_THIRD_PARTY:
                continue
            if _is_test_file(filepath) and _check_test_allowance(layer, top):
                continue
            if top in RULES.get(layer, []):
                violations.append(
                    f"{filepath}: from {node.module} import ... (layer={layer}, forbidden={top})"
                )
        # Handle lazy imports inside functions (ast nodes within)
        # Note: ast.walk already visits all nodes recursively

    return violations


def _check_test_allowance(layer: str, target: str) -> bool:
    """Check if a test file crosses layers that are allowed for testing."""
    return target in TESTING_LAYER_ALLOWED.get(layer, set())


def main() -> int:
    violations: list[str] = []

    for root, dirs, files in os.walk(BACKEND):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = Path(root) / fname
            if _is_exempted(fpath):
                continue
            violations.extend(_check_file(fpath))

    if violations:
        print(f"ERROR: {len(violations)} architecture import violation(s) found:\n")
        for v in sorted(violations):
            print(f"  {v}")
        return 1

    print("OK: No architecture import violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
