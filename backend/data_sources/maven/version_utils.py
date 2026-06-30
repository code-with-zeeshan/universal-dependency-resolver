import re
from typing import Dict, Optional

from ...core.utils import parse_version


def _is_maven_version(version_str: str) -> bool:
    return bool(re.match(r"^\d+(\.\d+)*(-\w+)?$", version_str))


def _sort_maven_version(version_str: str) -> tuple:
    parsed = parse_version(version_str)
    if parsed:
        return (parsed, 0)

    if "SNAPSHOT" in version_str:
        base_version = version_str.replace("-SNAPSHOT", "")
        parsed_base = parse_version(base_version)
        if parsed_base:
            return (parsed_base, 1)

    return (parse_version("0.0.0"), 2, version_str)


def _compare_java_versions(version1: str, version2: str) -> int:
    def extract_major(v):
        v = v.split("_")[0]
        parts = v.split(".")
        if parts[0] == "1" and len(parts) > 1:
            return int(parts[1])
        return int(parts[0])

    try:
        major1 = extract_major(version1)
        major2 = extract_major(version2)
        return (major1 > major2) - (major1 < major2)
    except Exception:
        return 0


def _parse_version_range_syntax(range_str: str) -> Dict:
    range_info = {
        "type": "range",
        "raw": range_str,
        "min_version": None,
        "max_version": None,
        "min_inclusive": False,
        "max_inclusive": False,
    }

    range_str = range_str.strip()

    if range_str.startswith("["):
        range_info["min_inclusive"] = True
    elif range_str.startswith("("):
        range_info["min_inclusive"] = False

    if range_str.endswith("]"):
        range_info["max_inclusive"] = True
    elif range_str.endswith(")"):
        range_info["max_inclusive"] = False

    inner = range_str[1:-1]
    parts = inner.split(",")

    if len(parts) == 1:
        range_info["min_version"] = parts[0].strip()
        range_info["max_version"] = parts[0].strip()
    elif len(parts) == 2:
        if parts[0].strip():
            range_info["min_version"] = parts[0].strip()
        if parts[1].strip():
            range_info["max_version"] = parts[1].strip()

    return range_info


def _should_include_transitive_dependency(parent_scope: str, dep_scope: str) -> bool:
    scope_rules = {
        "compile": ["compile", "runtime"],
        "runtime": ["runtime"],
        "test": ["compile", "runtime", "test"],
        "provided": [],
        "system": [],
    }

    allowed_scopes = scope_rules.get(parent_scope, [])
    return dep_scope in allowed_scopes


def _get_element_text(parent, tag: str, namespaces: Dict) -> Optional[str]:
    elem = parent.find(f".//maven:{tag}", namespaces)
    if elem is not None and elem.text:
        return elem.text.strip()

    elem = parent.find(f".//{tag}")
    if elem is not None and elem.text:
        return elem.text.strip()

    return None
