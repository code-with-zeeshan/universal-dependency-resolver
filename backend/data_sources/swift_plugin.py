"""Swift Package Manager — EcosystemPlugin implementation."""

import logging
import re
from typing import Any
from urllib.parse import quote

from ..core.plugin import (
    EcosystemPlugin,
    PluginLockFile,
    PluginManifest,
    register_ecosystem,
)
from ..core.swift_parser import parse_package_swift
from ..settings import get_ecosystem_config

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"

GIT_URL_RE = re.compile(r"(?:github\.com[/:]|git@)([\w.-]+)/([\w.-]+?)(?:\.git)?(?:\s|$|[/#?])")


@register_ecosystem("swift", name="Swift Package Manager", auth_prefix="SWIFT")
class SwiftPlugin(EcosystemPlugin):
    """Plugin for Swift Package Manager dependencies."""

    ecosystem = "swift"

    manifests = [
        PluginManifest(glob="Package.swift", parser="parse_swift"),
    ]

    lock_files = [
        PluginLockFile(glob="Package.resolved", parser="parse_package_resolved"),
    ]

    # ------------------------------------------------------------------
    # Manifest parser
    # ------------------------------------------------------------------
    @staticmethod
    def parse_swift(content: str) -> list[dict]:
        """Parse Swift Package Manager file for dependencies."""
        parsed = parse_package_swift(content)
        return [
            {"name": name, "version": ver} for name, ver in parsed.get("dependencies", {}).items()
        ]

    @staticmethod
    def parse_package_resolved(content: str) -> dict[str, dict[str, Any]]:
        """Parse Package.resolved into a name -> {version} map."""
        try:
            import json as _json

            data = _json.loads(content)
        except Exception:
            return {}

        packages: dict[str, dict[str, Any]] = {}
        pins = data.get("pins", data.get("object", {}).get("pins", []))
        for entry in pins:
            name = entry.get("identity", entry.get("package", ""))
            version = entry.get("version", entry.get("state", {}).get("version", ""))
            if name and version:
                packages[name] = {"version": version}
        return packages

    # ------------------------------------------------------------------
    # Manifest updater
    # ------------------------------------------------------------------
    @staticmethod
    def update_swift(content: str, package_name: str, resolved_version: str) -> str | None:
        """Update Package.swift content with pinned version."""
        import re

        # Match `.package(url: "...", from: "X.Y.Z")` or exact
        pattern = re.compile(
            r'(\.package\(url:\s*")([^"]+)("\s*,\s*(?:from|exact|revision):\s*")'
            r'([^"]+)(")',
            re.MULTILINE,
        )
        new_content, count = pattern.subn(
            lambda m: (
                m.group(1) + m.group(2) + m.group(3) + resolved_version + m.group(5)
                if package_name in m.group(2)
                else m.group(0)
            ),
            content,
        )
        return new_content if count > 0 else None

    # ------------------------------------------------------------------
    # Data source
    # ------------------------------------------------------------------
    @staticmethod
    def _default_base_url() -> str:
        return GITHUB_API

    def __init__(self, cache_ttl: int | None = None, max_retries: int | None = None):
        config = get_ecosystem_config("swift")
        configured_url = config.get("url", "").rstrip("/")
        self._registry_url = configured_url or GITHUB_API
        self._prefer_registry = bool(configured_url)
        super().__init__(cache_ttl=cache_ttl, max_retries=max_retries)

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        try:
            owner, repo = self._resolve_package(package_name)
            versions = await self._list_versions(owner, repo) if include_versions else []
            deps: dict[str, Any] = {}
            if include_dependencies and versions:
                latest = versions[0]["version"]
                manifest = await self._fetch_manifest(owner, repo, latest)
                if manifest:
                    parsed = parse_package_swift(manifest)
                    deps["dependencies"] = parsed["dependencies"]

            return {
                "name": package_name,
                "version": versions[0]["version"] if versions else "unknown",
                "versions": versions,
                "dependencies": deps,
            }
        except Exception as e:
            logger.error("Swift error for %s: %s", package_name, e)
            return None

    async def get_package_versions(
        self,
        package_name: str,
        filters: dict | None = None,
    ) -> list[dict]:
        info = await self.get_package_info(
            package_name, include_versions=True, include_dependencies=False
        )
        return info.get("versions", []) if info else []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_package(name: str) -> tuple[str, str]:
        name = name.strip()
        m = GIT_URL_RE.search(name)
        if m:
            return m.group(1), m.group(2).rstrip("/")
        if "/" in name:
            parts = name.split("/", 1)
            return parts[0], parts[1]
        if "." in name:
            parts = name.split(".", 1)
            return parts[0], parts[1]
        return name, name

    async def _list_versions(self, owner: str, repo: str) -> list[dict]:
        if self._prefer_registry:
            versions = await self._list_registry_releases(owner, repo)
            if versions:
                return versions
            return await self._list_github_tags(owner, repo)
        versions = await self._list_github_tags(owner, repo)
        if versions:
            return versions
        return await self._list_registry_releases(owner, repo)

    async def _list_github_tags(self, owner: str, repo: str) -> list[dict]:
        tags = await self._get(
            f"{GITHUB_API}/repos/{quote(owner)}/{quote(repo)}/tags",
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        if not tags or not isinstance(tags, list):
            return []
        versions: list[dict] = []
        for tag in tags:
            raw = tag.get("name", "")
            cleaned = raw.lstrip("v")
            if cleaned:
                versions.append({"version": cleaned})
        return versions

    async def _list_registry_releases(self, owner: str, repo: str) -> list[dict]:
        scope = quote(owner, safe="")
        name = quote(repo, safe="")
        data = await self._get(
            f"{self.base_url}/{scope}/{name}",
            headers={"Accept": "application/vnd.swift.registry.v1+json"},
        )
        if not data:
            return []
        releases = data.get("releases", {})
        return [{"version": v} for v in releases if isinstance(v, str)]

    async def _fetch_manifest(self, owner: str, repo: str, version: str) -> str | None:
        if self._prefer_registry:
            manifest = await self._fetch_registry_manifest(owner, repo, version)
            if manifest:
                return manifest
            return await self._fetch_raw_manifest(owner, repo, version)
        manifest = await self._fetch_raw_manifest(owner, repo, version)
        if manifest:
            return manifest
        return await self._fetch_registry_manifest(owner, repo, version)

    async def _fetch_raw_manifest(self, owner: str, repo: str, version: str) -> str | None:
        url = f"{GITHUB_RAW}/{quote(owner)}/{quote(repo)}/{quote(version)}/Package.swift"
        return await self._get_text(url)

    async def _fetch_registry_manifest(self, owner: str, repo: str, version: str) -> str | None:
        scope = quote(owner, safe="")
        name = quote(repo, safe="")
        ver = quote(version, safe="")
        return await self._get_text(
            f"{self.base_url}/{scope}/{name}/{ver}/Package.swift",
            headers={"Accept": "application/vnd.swift.registry.v1+swift"},
        )
