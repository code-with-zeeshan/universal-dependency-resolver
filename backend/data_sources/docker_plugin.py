"""Docker — EcosystemPlugin for Dockerfile FROM directives."""

import logging
import re
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)

_FROM_RE = re.compile(
    r"^FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+\S+)?$",
    re.IGNORECASE,
)


@register_ecosystem("docker", name="Docker", auth_prefix="DOCKER")
class DockerPlugin(EcosystemPlugin):
    """Plugin for Docker images — parses FROM directives in Dockerfiles."""

    ecosystem = "docker"

    manifests = [
        PluginManifest(glob="Dockerfile", parser="parse_dockerfile"),
        PluginManifest(glob="Dockerfile.*", parser="parse_dockerfile"),
    ]

    @staticmethod
    def parse_dockerfile(content: str) -> list[dict]:
        """Parse a Dockerfile and extract FROM image references."""
        if not isinstance(content, str):
            return []
        deps: list[dict] = []

        for line in content.splitlines():
            stripped = line.strip()
            m = _FROM_RE.match(stripped)
            if not m:
                continue
            image_ref = m.group(1)

            if image_ref == "scratch":
                continue

            if "@" in image_ref:
                name, version = image_ref.split("@", 1)
            elif ":" in image_ref:
                name, version = image_ref.split(":", 1)
            else:
                name = image_ref
                version = "latest"

            deps.append(
                {
                    "name": name,
                    "version": version,
                    "_ecosystem": "docker",
                }
            )

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
        try:
            from ..data_sources.docker_client import DockerRegistryClient

            client = DockerRegistryClient()
            try:
                tags = await client.get_tags(package_name)
                if not tags:
                    logger.warning("Docker: no tags found for %s", package_name)
                    return None
                versions = [{"version": t} for t in tags]
                return {
                    "name": package_name,
                    "ecosystem": "docker",
                    "version": tags[0],
                    "versions": versions if include_versions else [],
                    "dependencies": {},
                }
            finally:
                await client.close()
        except Exception as e:
            logger.warning("Docker fetch failed for %s: %s", package_name, e)
            return None
