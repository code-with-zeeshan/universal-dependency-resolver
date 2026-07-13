"""Hackage (Haskell) — EcosystemPlugin implementation."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)
from ..core.utils import normalize_package_name

logger = logging.getLogger(__name__)


@register_ecosystem("haskell", name="Hackage (Haskell)", auth_prefix="HASKELL")
class HaskellPlugin(EcosystemPlugin):
    """Plugin for Hackage — the Haskell package registry."""

    ecosystem = "haskell"

    manifests = [
        PluginManifest(glob="*.cabal", parser="parse_cabal"),
    ]

    # ------------------------------------------------------------------
    # Manifest parser
    # ------------------------------------------------------------------
    @staticmethod
    def parse_cabal(content: str) -> list[dict]:
        """Parse Cabal build file, handling multi-line build-depends."""
        deps = []
        in_build_depends = False
        continuation_lines = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("--") or stripped.startswith("{"):
                continue
            if stripped.startswith("build-depends:"):
                in_build_depends = True
                # Collect remaining part of this line and continuations
                rest = stripped[len("build-depends:") :].strip()
                if rest:
                    continuation_lines = [rest]
                else:
                    continuation_lines = []
                continue
            if in_build_depends:
                # Accumulate continuation lines (indented or starting with ,)
                if stripped.startswith(",") or (stripped and line[0] in (" ", "\t")):
                    continuation_lines.append(stripped.lstrip(",").strip())
                    continue
                # End of build-depends block — process accumulated lines
                all_deps = " ".join(continuation_lines)
                for dep_str in all_deps.split(","):
                    dep_str = dep_str.strip()
                    if not dep_str:
                        continue
                    parts = dep_str.split()
                    name = parts[0] if parts else dep_str
                    ver = parts[1] if len(parts) > 1 else "*"
                    deps.append({"name": name, "version": ver})
                in_build_depends = False
                continuation_lines = []
        # Handle end-of-file case (no blank line after build-depends)
        if in_build_depends and continuation_lines:
            all_deps = " ".join(continuation_lines)
            for dep_str in all_deps.split(","):
                dep_str = dep_str.strip()
                if not dep_str:
                    continue
                parts = dep_str.split()
                name = parts[0] if parts else dep_str
                ver = parts[1] if len(parts) > 1 else "*"
                deps.append({"name": name, "version": ver})
        return deps

    # ------------------------------------------------------------------
    # Manifest updater
    # ------------------------------------------------------------------
    @staticmethod
    def update_cabal(content: str, package_name: str, resolved_version: str) -> str | None:
        """Update .cabal file content with pinned version."""
        import re

        pattern = re.compile(
            r"(" + re.escape(package_name) + r"\s+)(?:[><=!]+\s*[\w.*,]+|[\w.*]+)",
            re.MULTILINE,
        )
        new_content, count = pattern.subn(
            r"\g<1>" + resolved_version,
            content,
        )
        return new_content if count > 0 else None

    # ------------------------------------------------------------------
    # Data source
    # ------------------------------------------------------------------
    @staticmethod
    def _default_base_url() -> str:
        return "https://hackage.haskell.org"

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        pkg = normalize_package_name(package_name)
        try:
            data = await self._get(f"{self.base_url}/package/{pkg}.json")
            if not data:
                return None
            versions = []
            if isinstance(data, dict):
                for ver_str in data:
                    versions.append({"version": ver_str})
            elif isinstance(data, list):
                for v in data:
                    if isinstance(v, dict):
                        versions.append({"version": v.get("version", "")})
                    elif isinstance(v, str):
                        versions.append({"version": v})
            return {
                "name": pkg,
                "version": versions[0]["version"] if versions else "unknown",
                "versions": versions,
                "dependencies": {"dependencies": {}},
            }
        except Exception as e:
            logger.error(f"Haskell error for {package_name}: {e}")
            return None

    async def get_package_versions(
        self,
        package_name: str,
        filters: dict | None = None,
    ) -> list[dict]:
        info = await self.get_package_info(package_name, include_versions=True)
        return info.get("versions", []) if info else []
