"""Platform marker expression parser and evaluator.

Supports PEP 508 marker syntax used by PyPI packages
(``sys_platform``, ``platform_machine``, ``python_version``, etc.)
and provides a ``evaluate_marker()`` function that can be called with
either a raw ``packaging.markers.Marker`` object or a marker string.

Usage::

    from backend.core.markers import evaluate_marker

    # Evaluate against host system_info
    ok = evaluate_marker('sys_platform == "linux"', system_info)

    # Evaluate against target env for cross-compilation
    ok = evaluate_marker('python_version >= "3.10"', target_info)
"""

from __future__ import annotations

import logging
import os
import platform as _platform
import re
from typing import Any

logger = logging.getLogger(__name__)

# PEP 508 marker variables mapped to system_info lookup paths
_MARKER_VAR_MAP: dict[str, str] = {
    "sys_platform": "platform.system",
    "platform_system": "platform.system",
    "platform_machine": "platform.machine",
    "platform_release": "platform.release",
    "platform_version": "platform.version",
    "python_version": "runtime_versions.python.version",
    "python_full_version": "runtime_versions.python.version",
    "implementation_name": "runtime_versions.python.implementation",
    "os_name": "platform.os_type",
}

# PEP 508 comparison operators
_CMP_OPS = {"===", "==", "!=", ">=", "<=", ">", "<", "in", "not in"}


def _get_value(var_name: str, system_info: dict | None) -> str:
    """Look up a PEP 508 marker variable in *system_info* (or fall back to live env)."""
    path = _MARKER_VAR_MAP.get(var_name)
    if path and system_info:
        parts = path.split(".")
        val: Any = system_info
        try:
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p, "")
                elif hasattr(val, p):
                    val = getattr(val, p, "")
                else:
                    val = ""
                    break
            return str(val) if val else ""
        except Exception:
            pass
    # Fallback: read from live environment
    fallbacks: dict[str, str] = {
        "sys_platform": _platform.system().lower(),
        "platform_system": _platform.system().lower(),
        "platform_machine": _platform.machine(),
        "platform_release": _platform.release(),
        "platform_version": _platform.version(),
        "python_version": ".".join(_platform.python_version_tuple()[:2]),
        "python_full_version": _platform.python_version(),
        "implementation_name": _platform.python_implementation().lower(),
        "os_name": os.name,
    }
    return fallbacks.get(var_name, "")


def _cmp_str(left: str, op: str, right: str) -> bool:
    """Compare two string values using a PEP 508 comparison operator."""
    if op == "===":
        return left == right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "in":
        return left in right
    if op == "not in":
        return left not in right

    # Numeric comparison for version-like values
    try:
        lv = tuple(int(x) for x in re.findall(r"\d+", left))
        rv = tuple(int(x) for x in re.findall(r"\d+", right))
    except (ValueError, TypeError):
        return False

    if op == ">=":
        return lv >= rv
    if op == "<=":
        return lv <= rv
    if op == ">":
        return lv > rv
    if op == "<":
        return lv < rv
    return False


def _tokenize_marker(expr: str) -> list[str]:
    """Tokenize a marker expression into operands, operators, and parens."""
    expr = expr.strip()
    if not expr:
        return []
    tokens: list[str] = []
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch in " \t":
            i += 1
            continue
        if ch in "()":
            tokens.append(ch)
            i += 1
            continue
        if ch in ('"', "'"):
            end = expr.find(ch, i + 1)
            if end == -1:
                tokens.append(expr[i:])
                break
            tokens.append(expr[i + 1 : end])
            i = end + 1
            continue
        # Operator
        for op_len in (5, 4, 3, 2):
            if expr[i : i + op_len] in _CMP_OPS:
                tokens.append(expr[i : i + op_len])
                i += op_len
                break
        else:
            # Variable name
            j = i
            while j < len(expr) and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            if j == i:
                # Non-alphanumeric character — skip it
                i += 1
                continue
            tokens.append(expr[i:j])
            i = j
    return tokens


def _eval_tokens(tokens: list[str], idx: int, system_info: dict | None) -> tuple[bool, int]:
    """Evaluate tokens from *idx* and return ``(result, next_idx)``."""
    if idx >= len(tokens):
        return True, idx

    # Parenthesized sub-expression
    if tokens[idx] == "(":
        result, idx = _eval_tokens(tokens, idx + 1, system_info)
        if idx < len(tokens) and tokens[idx] == ")":
            idx += 1
        else:
            return result, idx
    else:
        left = tokens[idx]
        idx += 1
        op = tokens[idx] if idx < len(tokens) and tokens[idx] in _CMP_OPS else "=="
        if op in _CMP_OPS:
            idx += 1
        right = tokens[idx] if idx < len(tokens) else ""
        if right.startswith(('"', "'")):
            right = right[1:-1]
        if left in _MARKER_VAR_MAP or left.startswith(("python", "platform", "sys", "os_")):
            left_val = _get_value(left, system_info)
        else:
            left_val = left.strip("\"'")
        idx += 1
        result = _cmp_str(left_val, op, right.strip("\"'"))

    # Chained boolean operators
    while idx < len(tokens):
        if tokens[idx] in ("and", "or"):
            op = tokens[idx]
            idx += 1
            right_result, idx = _eval_tokens(tokens, idx, system_info)
            result = result and right_result if op == "and" else result or right_result
        elif tokens[idx] == ")":
            break
        else:
            idx += 1

    return result, idx


def evaluate_marker_string(marker_str: str, system_info: dict | None = None) -> bool:
    """Evaluate a PEP 508 marker string against *system_info*.

    Args:
        marker_str: A PEP 508 marker expression like
            ``'sys_platform == "linux"'`` or
            ``'python_version >= "3.8" and sys_platform != "win32"'``.
        system_info: The system info dict (from system_scanner or
            cross-compilation target).  Falls back to live environment
            when ``None`` or when a variable is not found.

    Returns:
        ``True`` if the marker evaluates positively (dependency should
        be included), ``False`` if it should be excluded.
    """
    marker_str = marker_str.strip()
    if not marker_str:
        return True

    # Try packaging.markers first — it's robust and handles edge cases
    try:
        from packaging.markers import Marker as _Marker

        m = _Marker(marker_str)
        if system_info:
            env: dict[str, str] = {}
            for var in _MARKER_VAR_MAP:
                val = _get_value(var, system_info)
                if val:
                    env[var] = val
            return m.evaluate(env)
        return m.evaluate()
    except Exception:
        pass

    # Fall back to our token-based evaluator
    try:
        tokens = _tokenize_marker(marker_str)
        if not tokens:
            return True
        result, _ = _eval_tokens(tokens, 0, system_info)
        return result
    except Exception as exc:
        logger.warning("Failed to evaluate marker '%s': %s", marker_str, exc)
        return True


def filter_deps_by_marker(
    deps: list,
    system_info: dict | None = None,
) -> list:
    """Filter a list of :class:`Dependency` objects by their marker field.

    Dependencies whose marker evaluates to ``False`` are excluded.
    Dependencies without a marker are always included.
    """
    result: list = []
    for dep in deps:
        marker = getattr(dep, "marker", None)
        if marker:
            try:
                if not evaluate_marker_string(marker, system_info):
                    continue
            except Exception:
                pass
        result.append(dep)
    return result
