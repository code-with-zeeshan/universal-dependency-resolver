"""Gradle Plugin Portal — EcosystemPlugin implementation."""

import logging
import xml.etree.ElementTree as ET
from typing import Any

from packaging import version as packaging_version

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("gradle", name="Gradle Plugin Portal", auth_prefix="GRADLE")
class GradlePlugin(EcosystemPlugin):
    """Plugin for Gradle dependencies.

    Tries the Gradle Plugin Portal first for plugin dependencies.
    Falls back to Maven Central (repo1.maven.org) for regular
    Maven dependencies declared in build.gradle files.
    """

    ecosystem = "gradle"

    manifests = [
        PluginManifest(glob="build.gradle", parser="parse_gradle"),
        PluginManifest(glob="build.gradle.kts", parser="parse_gradle"),
    ]

    # ------------------------------------------------------------------
    # Manifest parser
    # ------------------------------------------------------------------
    @staticmethod
    def parse_gradle(content: str) -> list[dict]:
        """Parse Gradle build file for dependencies."""
        deps = []
        gradle_configs = {
            "implementation",
            "api",
            "compile",
            "runtimeOnly",
            "testImplementation",
            "kapt",
            "annotationProcessor",
            "compileOnly",
            "androidTestImplementation",
            "debugImplementation",
            "releaseImplementation",
        }
        import re

        # Match map-style notation: group:name:version or group:name:version@ext
        map_pattern = re.compile(
            r"(implementation|api|compile|runtimeOnly|testImplementation|kapt|"
            r"annotationProcessor|compileOnly|androidTestImplementation|"
            r"debugImplementation|releaseImplementation)\s+['\"]([^'\"]+)['\"]"
        )
        for match in map_pattern.finditer(content):
            config = match.group(1)
            value = match.group(2)
            if value.count(":") >= 1:
                parts = value.rsplit(":", 2) if value.count(":") >= 2 else value.split(":")
                group = parts[0]
                artifact = parts[1] if len(parts) > 1 else parts[0]
                version = parts[2] if len(parts) > 2 else "*"
                full_name = f"{group}:{artifact}"
                deps.append({"name": full_name, "version": version})

        # Match function-style: dependencies { implementation("group:name:version") }
        func_pattern = re.compile(
            r"(?:implementation|api|compile|runtimeOnly|testImplementation|kapt|"
            r"annotationProcessor|compileOnly|androidTestImplementation|"
            r"debugImplementation|releaseImplementation)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
        )
        for match in func_pattern.finditer(content):
            value = match.group(1)
            if value.count(":") >= 1:
                parts = value.rsplit(":", 2) if value.count(":") >= 2 else value.split(":")
                group = parts[0]
                artifact = parts[1] if len(parts) > 1 else parts[0]
                version = parts[2] if len(parts) > 2 else "*"
                full_name = f"{group}:{artifact}"
                deps.append({"name": full_name, "version": version})

        return deps

    # ------------------------------------------------------------------
    # Manifest updater
    # ------------------------------------------------------------------
    @staticmethod
    def update_gradle(content: str, package_name: str, resolved_version: str) -> str | None:
        """Update build.gradle/.kts content with pinned version."""
        import re

        escaped = re.escape(package_name)
        pattern = re.compile(
            r"(" + escaped + r":)([\w.*-]+)",
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
        return "https://plugins.gradle.org/api"

    def __init__(self, cache_ttl: int | None = None, max_retries: int | None = None):
        super().__init__(cache_ttl=cache_ttl, max_retries=max_retries)
        self.maven_repo_url = "https://repo1.maven.org/maven2"

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        group, artifact = (
            package_name.split(":", 1) if ":" in package_name else (package_name, package_name)
        )
        group = group.lower()
        artifact = artifact.lower()

        # Try Gradle Plugin Portal first
        try:
            data = await self._get(f"{self.base_url}/g/{group}/a/{artifact}")
            if data:
                versions = data.get("versions", [])
                return {
                    "name": package_name,
                    "version": versions[0] if versions else "unknown",
                    "versions": [{"version": v} for v in versions],
                    "dependencies": {"dependencies": {}},
                    "ecosystem": "gradle",
                }
        except Exception as exc:
            logger.debug("Gradle Plugin Portal lookup failed for %s: %s", package_name, exc)

        # Fall back to Maven Central
        return await self._fetch_from_maven_central(group, artifact, package_name)

    async def _fetch_from_maven_central(
        self,
        group: str,
        artifact: str,
        full_name: str,
    ) -> dict[str, Any] | None:
        group_path = group.replace(".", "/")
        metadata_url = f"{self.maven_repo_url}/{group_path}/{artifact}/maven-metadata.xml"

        try:
            import aiohttp

            session = self._get_session()
            timeout = aiohttp.ClientTimeout(total=15)
            async with session.get(metadata_url, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                text = await resp.text()
        except Exception as exc:
            logger.debug("Maven Central metadata fetch failed for %s: %s", full_name, exc)
            return None

        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return None

        version_elements = root.findall(".//version")
        versions = [v.text for v in version_elements if v.text]

        if not versions:
            return None

        try:
            sorted_versions = sorted(
                set(versions),
                key=lambda v: packaging_version.parse(
                    v.replace("-", ".").replace("_", ".")
                    if packaging_version.parse(v) is not None
                    else v
                ),
                reverse=True,
            )
        except Exception:
            sorted_versions = sorted(set(versions), reverse=True)

        latest = sorted_versions[0]
        return {
            "name": full_name,
            "version": latest,
            "versions": sorted_versions,
            "dependencies": {"dependencies": {}},
            "ecosystem": "gradle",
        }

    async def get_package_versions(
        self,
        package_name: str,
        filters: dict | None = None,
    ) -> list[dict]:
        info = await self.get_package_info(package_name, include_versions=True)
        raw = info.get("versions", []) if info else []
        return [{"version": v} if isinstance(v, str) else v for v in raw]
