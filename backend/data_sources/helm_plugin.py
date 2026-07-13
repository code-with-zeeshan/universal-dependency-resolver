"""Helm — EcosystemPlugin for Helm Charts (Chart.yaml / Chart.lock)."""

import json
import logging
import re
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginLockFile,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("helm", name="Helm Charts", auth_prefix="HELM")
class HelmPlugin(EcosystemPlugin):
    """Plugin for Helm Charts — recognizes Chart.yaml and Chart.lock."""

    ecosystem = "helm"

    manifests = [
        PluginManifest(glob="Chart.yaml", parser="parse_chart_yaml"),
    ]

    lock_files = [
        PluginLockFile(glob="Chart.lock", parser="parse_chart_lock"),
    ]

    @staticmethod
    def parse_chart_yaml(content: str) -> list[dict]:
        """Parse Chart.yaml for dependencies.

        Handles multi-line YAML without a YAML library by scanning lines,
        tracking indentation, and looking for ``name:`` / ``version:`` keys
        inside a ``dependencies:`` block.
        """
        if not isinstance(content, str):
            return []
        deps: list[dict] = []
        in_dependencies = False
        dep_indent = 0
        current: dict | None = None

        for line in content.splitlines():
            stripped = line.rstrip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())

            # Detect dependencies: section
            m = re.match(r"^(\s*)dependencies:\s*$", line)
            if m:
                in_dependencies = True
                dep_indent = indent
                current = None
                continue

            if not in_dependencies:
                continue

            # Back to a key at or above the dependencies: indent → end of block
            if indent <= dep_indent and re.match(r"^\s*\w", line) and not line.lstrip().startswith("- "):
                break

            # Detect list items: "- name: ..."
            list_match = re.match(r"^\s*-\s+name:\s*(.+)$", line)
            if list_match:
                if current:
                    _finalize_dep(current, deps)
                current = {
                    "name": list_match.group(1).strip(),
                    "version": "*",
                    "_ecosystem": "helm",
                }
                continue

            # Detect key: value pairs inside a dependency block
            kv_match = re.match(r"^\s+(\w+):\s*(.*)$", line)
            if kv_match and current:
                key = kv_match.group(1)
                val = kv_match.group(2).strip()
                if key == "version":
                    current["version"] = val if val else "*"
                elif key == "repository":
                    current.setdefault("_metadata", {})["repository"] = val

        if current:
            _finalize_dep(current, deps)

        return deps

    @staticmethod
    def parse_chart_lock(content: str) -> dict[str, dict[str, Any]]:
        """Parse Chart.lock (JSON) into a name → {version} map."""
        if not isinstance(content, str):
            return {}
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {}

        packages: dict[str, dict[str, Any]] = {}
        for dep in data.get("dependencies", []):
            name = dep.get("name", "")
            version = dep.get("version", "*")
            if name:
                packages[name] = {
                    "version": version,
                    "dependencies": {},
                }
        return packages

    @staticmethod
    def _default_base_url() -> str:
        return ""

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        return {
            "name": package_name,
            "ecosystem": "helm",
            "version": "latest",
            "versions": [{"version": "latest"}],
            "dependencies": {},
            "description": "Helm chart (no remote metadata available)",
        }


def _finalize_dep(current: dict, deps: list[dict]) -> None:
    """Add *current* dependency to *deps* if it has a name."""
    name = current.get("name", "").strip().strip('"').strip("'")
    if name:
        entry = {
            "name": name,
            "version": current.get("version", "*"),
            "_ecosystem": "helm",
        }
        if "_metadata" in current:
            entry["_metadata"] = current["_metadata"]
        deps.append(entry)
