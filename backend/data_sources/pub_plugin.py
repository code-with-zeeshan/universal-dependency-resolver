"""Pub.dev (Dart/Flutter) — EcosystemPlugin implementation."""

import logging
from typing import Any
from urllib.parse import quote

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)
from ..core.utils import normalize_package_name, parse_version, parse_version_key

logger = logging.getLogger(__name__)


@register_ecosystem("pub", name="Pub.dev (Dart/Flutter)", auth_prefix="PUB")
class PubPlugin(EcosystemPlugin):
    """Plugin for pub.dev — the Dart/Flutter package registry."""

    ecosystem = "pub"

    manifests = [
        PluginManifest(glob="pubspec.yaml", parser="parse_pubspec"),
    ]

    # ------------------------------------------------------------------
    # Manifest parser
    # ------------------------------------------------------------------
    @staticmethod
    def parse_pubspec(content: str) -> list[dict]:
        """Parse pubspec.yaml."""
        deps = []
        in_deps = False
        in_dev_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            if stripped.startswith("dependencies:"):
                in_deps = True
                in_dev_deps = False
                continue
            if stripped.startswith("dev_dependencies:"):
                in_deps = False
                in_dev_deps = True
                continue
            if in_deps or in_dev_deps:
                indent = len(line) - len(line.lstrip())
                if indent == 0 and stripped:
                    break
                if ":" in stripped and not stripped.startswith("  ") and indent >= 2:
                    parts = stripped.split(":", 1)
                    name = parts[0].strip()
                    version = parts[1].strip()
                    # Handle multi-line format with version on next line
                    if not version and ("  " in line):
                        continue
                    if version == "":
                        version = "*"
                    # Skip Flutter SDK packages
                    if name == "flutter" or name.startswith("flutter_"):
                        continue
                    if name == "sdk":
                        continue
                    deps.append({"name": name, "version": version})
        return deps

    # ------------------------------------------------------------------
    # Manifest updater
    # ------------------------------------------------------------------
    @staticmethod
    def update_pubspec(content: str, package_name: str, resolved_version: str) -> str | None:
        """Update pubspec.yaml content with pinned version."""
        import re

        pattern = re.compile(
            r"(^\s*" + re.escape(package_name) + r":\s*).*$",
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
        return "https://pub.dev/api"

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        package_name = normalize_package_name(package_name)
        try:
            data = await self._get(f"{self.base_url}/packages/{quote(package_name)}")
            if not data:
                return None

            latest_version = data.get("latest", {}).get("version") or data.get("versions", [{}])[
                0
            ].get("version")

            versions: list[Any] = []
            for v in data.get("versions", []):
                version_str = v.get("version", "")
                if parse_version(version_str) is None:
                    continue
                pubspec = v.get("pubspec", {})
                versions.append(
                    {
                        "version": version_str,
                        "published": v.get("published", ""),
                        "pubspec": pubspec,
                    }
                )

            deps: dict[str, Any] = {"dependencies": {}}
            latest_pubspec = None
            if data.get("latest", {}).get("pubspec"):
                latest_pubspec = data["latest"]["pubspec"]
            elif versions and versions[0].get("pubspec"):
                latest_pubspec = versions[0]["pubspec"]
            if latest_pubspec:
                for dep_name, dep_ver in latest_pubspec.get("dependencies", {}).items():
                    if dep_name == "flutter" or dep_name.startswith("flutter_"):
                        continue
                    dep_str = str(dep_ver) if not isinstance(dep_ver, str) else dep_ver
                    deps["dependencies"][dep_name] = dep_str
                for dep_name, dep_ver in latest_pubspec.get("dev_dependencies", {}).items():
                    dep_str = str(dep_ver) if not isinstance(dep_ver, str) else dep_ver
                    deps.setdefault("dev_dependencies", {})[dep_name] = dep_str

            return {
                "name": data.get("name"),
                "version": latest_version,
                "description": data.get("description", ""),
                "homepage": data.get("homepage", ""),
                "repository": data.get("repository", ""),
                "documentation": data.get("documentation", ""),
                "latest_version": latest_version,
                "versions": versions,
                "dependencies": deps,
            }
        except Exception as e:
            logger.error(f"Pub.dev error for {package_name}: {e}")
            return None

    async def get_package_versions(
        self,
        package_name: str,
        filters: dict | None = None,
    ) -> list[dict]:
        package_name = normalize_package_name(package_name)
        try:
            data = await self._get(f"{self.base_url}/packages/{quote(package_name)}")
            if not data:
                return []

            versions: list[Any] = []
            for v in data.get("versions", []):
                version_str = v.get("version", "")
                if parse_version(version_str) is None:
                    continue
                versions.append(
                    {
                        "version": version_str,
                        "published": v.get("published", ""),
                        "pubspec": v.get("pubspec", {}),
                    }
                )

            return sorted(
                versions,
                key=lambda x: parse_version_key(x["version"]),
                reverse=True,
            )
        except Exception as e:
            logger.error(f"Pub.dev versions error for {package_name}: {e}")
            return []

    async def search_packages(self, query: str, limit: int = 20) -> list[dict]:
        try:
            data = await self._get(
                f"{self.base_url}/search",
                params={"q": query, "size": limit},
            )
            if not data:
                return []
            return data.get("packages", [])
        except Exception:
            return []
