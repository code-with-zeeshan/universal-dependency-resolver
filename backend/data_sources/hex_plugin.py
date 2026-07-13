"""Hex.pm (Elixir/Erlang) — EcosystemPlugin implementation."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginLockFile,
    PluginManifest,
    register_ecosystem,
)
from ..core.utils import normalize_package_name

logger = logging.getLogger(__name__)


@register_ecosystem("hex", name="Hex.pm (Elixir/Erlang)", auth_prefix="HEX")
class HexPlugin(EcosystemPlugin):
    """Plugin for hex.pm — the Elixir/Erlang package registry."""

    ecosystem = "hex"

    manifests = [
        PluginManifest(glob="mix.exs", parser="parse_mix_exs"),
    ]

    lock_files = [
        PluginLockFile(glob="mix.lock", parser="parse_mix_lock"),
    ]

    # ------------------------------------------------------------------
    # Manifest parser (called by ManifestDetector via _get_parser)
    # ------------------------------------------------------------------
    @staticmethod
    def parse_mix_exs(content: str) -> list[dict]:
        """Parse a mix.exs file for dependencies."""
        deps = []
        in_deps = False
        paren_depth = 0
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            if "defp deps" in stripped or "def deps" in stripped:
                in_deps = True
                continue
            if in_deps:
                if "end" in stripped:
                    break
                if stripped.startswith("{:"):
                    parts = stripped.strip().strip(",").split(",")
                    if len(parts) >= 1:
                        name = parts[0].strip("{:").strip()
                        version = (
                            parts[1].strip().strip('"').strip("~> ").strip(">= ").strip()
                            if len(parts) > 1
                            else "*"
                        )
                        deps.append({"name": name, "version": version})
                elif ":" in stripped and not stripped.startswith("["):
                    for char in stripped:
                        if char == "(":
                            paren_depth += 1
                        elif char == ")":
                            paren_depth -= 1
                    if paren_depth == 0 and stripped.endswith(","):
                        eq_idx = stripped.find(":")
                        if eq_idx > 0:
                            name = stripped[:eq_idx].strip()
                            rest = stripped[eq_idx + 1 :].strip().strip(",")
                            version = rest.strip('"').strip("~> ").strip(">= ").strip()
                            deps.append({"name": name, "version": version})
        return deps

    # ------------------------------------------------------------------
    # Lock-file parser
    # ------------------------------------------------------------------
    @staticmethod
    def parse_mix_lock(content: str) -> dict[str, dict[str, Any]]:
        """Parse a mix.lock file into a name -> {version} map."""
        import re

        packages: dict[str, dict[str, Any]] = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("%"):
                continue
            line = line.rstrip(",")
            m = re.match(r'["\']([^"\']+)["\']\s*:', line)
            if not m:
                continue
            name = m.group(1)
            inner = line[m.end() :].strip().lstrip("{").strip()
            parts = inner.split(",")
            if len(parts) >= 3:
                ver_m = re.search(r'["\']([^"\']+)["\']', parts[2])
                if ver_m:
                    packages[name] = {"version": ver_m.group(1)}
                    # Extract deps from the list at parts index 4 (if present)
                    dep_list = (
                        re.findall(r'["\']([^"\']+)["\']', parts[4]) if len(parts) > 4 else []
                    )
                    if dep_list:
                        packages[name]["dependencies"] = dict.fromkeys(dep_list)
        return packages

    # ------------------------------------------------------------------
    # Manifest updater
    # ------------------------------------------------------------------
    @staticmethod
    def update_mix_exs(content: str, package_name: str, resolved_version: str) -> str | None:
        """Update a version constraint in mix.exs for *package_name*."""
        import re

        pattern = re.compile(
            r'(:\s*)("?)' + re.escape(package_name) + r'("?\s*,?\s*")([^"]+)(")',
            re.MULTILINE,
        )
        new_content, count = pattern.subn(
            lambda m: (
                m.group(1) + m.group(2) + package_name + m.group(3) + resolved_version + m.group(5)
            ),
            content,
        )
        if count == 0:
            alt_pattern = re.compile(
                r'(:\s*)([a-zA-Z_]+)\s*,?\s*"([^"]+)"',
                re.MULTILINE,
            )
            match = alt_pattern.search(content)
            if match and match.group(2) == package_name:
                start, end = match.start(3), match.end(3)
                new_content = content[:start] + resolved_version + content[end:]
                count = 1
        return new_content if count > 0 else None

    # ------------------------------------------------------------------
    # Data source
    # ------------------------------------------------------------------
    @staticmethod
    def _default_base_url() -> str:
        return "https://hex.pm/api"

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        pkg = normalize_package_name(package_name)
        try:
            data = await self._get(f"{self.base_url}/packages/{pkg}")
            if not data:
                return None
            releases = data.get("releases", [])
            versions = []
            for r in releases:
                v = r.get("version", "") if isinstance(r, dict) else str(r)
                versions.append({"version": v})
            latest = versions[0]["version"] if versions else "unknown"
            return {
                "name": pkg,
                "version": latest,
                "versions": versions,
                "dependencies": {"dependencies": {}},
            }
        except Exception as e:
            logger.error(f"Hex error for {package_name}: {e}")
            return None

    async def search_packages(self, query: str, limit: int = 20) -> list[dict]:
        data = await self._get(
            f"{self.base_url}/packets",
            params={"sort": "name", "search": query, "per_page": limit},
        )
        if not data:
            return []
        return data.get("packages", data) if isinstance(data, dict) else data
