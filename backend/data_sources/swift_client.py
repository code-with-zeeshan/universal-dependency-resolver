"""Swift Package Manager client with dual-path resolution.

Resolution order (try-fallback):
  1. SE-0292 registry (if configured) — ``Accept: application/vnd.swift.registry.v1+json``
  2. GitHub API — tags via ``api.github.com``, manifests via ``raw.githubusercontent.com``
  3. Falls back gracefully with user guidance when all paths fail.
"""

import logging
import re
from typing import Any
from urllib.parse import quote

from ..core.swift_parser import parse_package_swift
from ..settings import CACHE_TTL, get_ecosystem_config
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"

GIT_URL_RE = re.compile(r"(?:github\.com[/:]|git@)([\w.-]+)/([\w.-]+?)(?:\.git)?(?:\s|$|[/#?])")

_SWIFT_HELP = """\
Swift packages require one of:
  1) A local Package.swift checkout (for `udr lock` — no API needed)
  2) A Swift Package Registry host (SE-0292) — used automatically for \
GitHub-hosted packages, no auth required
  3) SPI GraphQL API key (if you prefer, request one via \
https://swiftpackageindex.com)
"""


class SwiftClient(BaseDataSourceClient):
    """Swift Package Manager client.

    Resolution tries the configured registry first, then falls back to
    GitHub's public API.  All paths support public packages without auth.
    """

    def __init__(
        self,
        cache_ttl: int | None = None,
        max_retries: int | None = None,
    ):
        """Initialize."""
        config = get_ecosystem_config("swift")
        configured_url = config.get("url", "").rstrip("/")
        self._registry_url = configured_url or GITHUB_API
        self._prefer_registry = bool(configured_url)

        super().__init__(
            ecosystem="swift",
            base_url=self._registry_url,
            cache_ttl=cache_ttl or config.get("cache_ttl", CACHE_TTL),
        )

    async def get_package_info_async(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        """get package info async."""
        return await self.get_package_info(
            package_name,
            include_dependencies=include_dependencies,
            include_versions=include_versions,
        )

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        """get package info."""
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
        self, package_name: str, filters: dict | None = None
    ) -> list[dict]:
        """get package versions."""
        info = await self.get_package_info(
            package_name, include_versions=True, include_dependencies=False
        )
        return info.get("versions", []) if info else []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_package(name: str) -> tuple[str, str]:
        """Parse *name* into ``(owner, repo)``.

        Accepts:

        * ``https://github.com/owner/repo``
        * ``git@github.com:owner/repo.git``
        * ``owner/repo``
        * ``scope.name`` (SE-0292 identity)
        * ``name`` (plain - used as both owner and repo)
        """
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
        """Return ``[{"version": str}, ...]``.

        Tries primary path first, then falls back to the alternative.
        """
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
        """SE-0292 ``GET /{scope}/{name}``."""
        """SE-0292 ``GET /{scope}/{name}``."""
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
        """Return the raw ``Package.swift`` content.

        Tries primary path first, then falls back to the alternative.
        """
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
        """SE-0292 ``GET /{scope}/{name}/{version}/Package.swift``."""
        """SE-0292 ``GET /{scope}/{name}/{version}/Package.swift``."""
        scope = quote(owner, safe="")
        name = quote(repo, safe="")
        ver = quote(version, safe="")
        return await self._get_text(
            f"{self.base_url}/{scope}/{name}/{ver}/Package.swift",
            headers={"Accept": "application/vnd.swift.registry.v1+swift"},
        )

    @staticmethod
    def _swift_resolution_help() -> str:
        """Return a user-facing message explaining Swift resolution options."""
        """Return a user-facing message explaining Swift resolution options."""
        return _SWIFT_HELP

    @staticmethod
    def _parse_swift_deps(content: str) -> dict[str, str]:
        """Extract ``{package_name: version_constraint}`` from ``Package.swift``."""
        return parse_package_swift(content)["dependencies"]
