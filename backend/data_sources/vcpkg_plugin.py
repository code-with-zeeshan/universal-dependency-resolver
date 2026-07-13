"""Vcpkg — EcosystemPlugin for Microsoft's C/C++ package manager."""

import json
import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("vcpkg", name="Vcpkg (C/C++)", auth_prefix="VCPKG")
class VcpkgPlugin(EcosystemPlugin):
    """Plugin for Vcpkg packages — recognizes vcpkg.json manifests."""

    ecosystem = "vcpkg"

    manifests = [
        PluginManifest(glob="vcpkg.json", parser="parse_vcpkg_json"),
    ]

    @staticmethod
    def parse_vcpkg_json(content: str) -> list[dict]:
        """Parse vcpkg.json for dependencies.

        Supports:
          - String deps: ``{"dependencies": ["fmt", "spdlog"]}``
          - Object deps: ``{"dependencies": [{"name": "fmt", "version>=": "7.1.3"}]}``
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []

        if not isinstance(data, dict):
            return []

        deps: list[dict] = []
        raw_deps = data.get("dependencies", [])
        if not isinstance(raw_deps, list):
            return []

        for entry in raw_deps:
            if isinstance(entry, str):
                deps.append({"name": entry, "version": "*", "_ecosystem": "vcpkg"})
            elif isinstance(entry, dict):
                name = entry.get("name", "")
                if not name:
                    continue
                # version>= or version: string constraint
                version = entry.get("version>=") or entry.get("version") or "*"
                deps.append({"name": name, "version": version, "_ecosystem": "vcpkg"})

        return deps

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
            "ecosystem": "vcpkg",
            "version": "latest",
            "versions": [{"version": "latest"}],
            "dependencies": {},
            "description": "Vcpkg package (no remote metadata available)",
        }
