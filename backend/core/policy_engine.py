"""Policy engine — load and enforce project-level dependency policies."""

import logging
from pathlib import Path

from backend.core.license_checker import normalize_license

logger = logging.getLogger(__name__)

SEVERITY = "severity"
RULE = "rule"


def load_policy(path: str | Path) -> dict:
    """Load and validate a YAML policy file.

    Returns the parsed policy dict with a ``policies`` list.
    """
    import yaml

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Policy file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "policies" not in raw:
        raise ValueError("Policy file must contain a top-level 'policies' list")
    policies = raw["policies"]
    if not isinstance(policies, list):
        raise ValueError("'policies' must be a list")
    known = {
        "no-deprecated",
        "no-yanked",
        "no-gpl",
        "no-agpl",
        "max-vulnerabilities",
        "max-critical-vulns",
        "must-pin-transitives",
        "allowed-licenses",
        "blocked-packages",
        "require-vendor",
    }
    for i, entry in enumerate(policies):
        if not isinstance(entry, dict) or RULE not in entry:
            raise ValueError(f"Policy #{i}: each entry must have a 'rule' key")
        rule = entry[RULE]
        if rule not in known:
            raise ValueError(f"Policy #{i}: unknown rule '{rule}'")
        if "severity" in entry and entry["severity"] not in ("error", "warning"):
            raise ValueError(f"Policy #{i}: severity must be 'error' or 'warning'")
    return raw


def check_policy(lock_data: dict, policy: dict) -> list[dict]:
    """Run all policy rules against lock file data.

    Returns a list of violations::

        [{rule, package, severity, message}, ...]
    """
    violations: list[dict] = []
    packages = lock_data.get("packages", {})
    for entry in policy.get("policies", []):
        rule = entry[RULE]
        severity = entry.get("severity", "error")
        _dispatch(rule, entry, packages, violations, severity)
    return violations


def _dispatch(
    rule: str,
    entry: dict,
    packages: dict[str, dict],
    violations: list[dict],
    severity: str,
) -> None:
    handler = {
        "no-deprecated": _check_no_deprecated,
        "no-yanked": _check_no_yanked,
        "no-gpl": _check_no_gpl,
        "no-agpl": _check_no_agpl,
        "max-vulnerabilities": _check_max_vulnerabilities,
        "max-critical-vulns": _check_max_critical_vulns,
        "must-pin-transitives": _check_must_pin_transitives,
        "allowed-licenses": _check_allowed_licenses,
        "blocked-packages": _check_blocked_packages,
        "require-vendor": _check_require_vendor,
    }.get(rule)
    if handler:
        handler(entry, packages, violations, severity)


def _check_no_deprecated(
    entry: dict,
    packages: dict[str, dict],
    violations: list[dict],
    severity: str,
) -> None:
    for name, info in packages.items():
        if info.get("deprecated"):
            violations.append(
                {
                    RULE: "no-deprecated",
                    "package": name,
                    SEVERITY: severity,
                    "message": f"{name}@{info.get('resolved_version', '?')} is deprecated",
                }
            )


def _check_no_yanked(
    entry: dict,
    packages: dict[str, dict],
    violations: list[dict],
    severity: str,
) -> None:
    for name, info in packages.items():
        if info.get("yanked"):
            violations.append(
                {
                    RULE: "no-yanked",
                    "package": name,
                    SEVERITY: severity,
                    "message": f"{name}@{info.get('resolved_version', '?')} is yanked",
                }
            )


def _check_no_gpl(
    entry: dict,
    packages: dict[str, dict],
    violations: list[dict],
    severity: str,
) -> None:
    gpl_keywords = {"gpl", "gpl-2.0", "gpl-3.0", "agpl", "agpl-3.0"}
    for name, info in packages.items():
        raw = info.get("license")
        if not raw:
            continue
        norm = normalize_license(str(raw)).lower()
        if norm in gpl_keywords:
            violations.append(
                {
                    RULE: "no-gpl",
                    "package": name,
                    SEVERITY: severity,
                    "message": f"{name}@{info.get('resolved_version', '?')} has GPL license: {raw}",
                }
            )


def _check_no_agpl(
    entry: dict,
    packages: dict[str, dict],
    violations: list[dict],
    severity: str,
) -> None:
    agpl_keywords = {"agpl", "agpl-3.0"}
    for name, info in packages.items():
        raw = info.get("license")
        if not raw:
            continue
        norm = normalize_license(str(raw)).lower()
        if norm in agpl_keywords:
            violations.append(
                {
                    RULE: "no-agpl",
                    "package": name,
                    SEVERITY: severity,
                    "message": f"{name}@{info.get('resolved_version', '?')} has AGPL license: {raw}",
                }
            )


def _check_max_vulnerabilities(
    entry: dict,
    packages: dict[str, dict],
    violations: list[dict],
    severity: str,
) -> None:
    max_vulns = entry.get("max", 0)
    total = 0
    for info in packages.values():
        total += len(info.get("vulnerabilities", []))
    if total > max_vulns:
        violations.append(
            {
                RULE: "max-vulnerabilities",
                "package": "*",
                SEVERITY: severity,
                "message": f"Found {total} vulnerabilities, max allowed is {max_vulns}",
            }
        )


def _check_max_critical_vulns(
    entry: dict,
    packages: dict[str, dict],
    violations: list[dict],
    severity: str,
) -> None:
    max_crit = entry.get("max", 0)
    count = 0
    for info in packages.values():
        for v in info.get("vulnerabilities", []):
            if v.get("severity", "").upper() == "CRITICAL":
                count += 1
    if count > max_crit:
        violations.append(
            {
                RULE: "max-critical-vulns",
                "package": "*",
                SEVERITY: severity,
                "message": f"Found {count} critical vulnerabilities, max allowed is {max_crit}",
            }
        )


def _check_must_pin_transitives(
    entry: dict,
    packages: dict[str, dict],
    violations: list[dict],
    severity: str,
) -> None:
    for name, info in packages.items():
        if info.get("direct"):
            continue
        constraint = info.get("original_constraint", "")
        if not constraint or constraint == "*":
            continue
        violations.append(
            {
                RULE: "must-pin-transitives",
                "package": name,
                SEVERITY: severity,
                "message": f"Transitive dep {name}@{info.get('resolved_version', '?')} has unpinned constraint '{constraint}'",
            }
        )


def _check_allowed_licenses(
    entry: dict,
    packages: dict[str, dict],
    violations: list[dict],
    severity: str,
) -> None:
    allowed = {lcase.lower() for lcase in entry.get("licenses", [])}
    for name, info in packages.items():
        raw = info.get("license")
        if not raw:
            violations.append(
                {
                    RULE: "allowed-licenses",
                    "package": name,
                    SEVERITY: severity,
                    "message": f"{name}@{info.get('resolved_version', '?')} has no license info",
                }
            )
            continue
        norm = normalize_license(str(raw)).lower()
        if norm not in allowed:
            violations.append(
                {
                    RULE: "allowed-licenses",
                    "package": name,
                    SEVERITY: severity,
                    "message": f"{name}@{info.get('resolved_version', '?')} has unapproved license: {raw}",
                }
            )


def _check_blocked_packages(
    entry: dict,
    packages: dict[str, dict],
    violations: list[dict],
    severity: str,
) -> None:
    blocked = set(entry.get("packages", []))
    for name in packages:
        if name in blocked:
            violations.append(
                {
                    RULE: "blocked-packages",
                    "package": name,
                    SEVERITY: severity,
                    "message": f"Blocked package {name} is present in lock file",
                }
            )


def _check_require_vendor(
    entry: dict,
    packages: dict[str, dict],
    violations: list[dict],
    severity: str,
) -> None:
    for name, info in packages.items():
        if not info.get("direct"):
            continue
        if not info.get("vendor"):
            violations.append(
                {
                    RULE: "require-vendor",
                    "package": name,
                    SEVERITY: severity,
                    "message": f"Direct dependency {name} has no vendor field",
                }
            )
