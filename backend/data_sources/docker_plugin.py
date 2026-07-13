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
        return {
            "name": package_name,
            "ecosystem": "docker",
            "version": "latest",
            "versions": [{"version": "latest"}],
            "dependencies": {},
            "description": "Docker image (no remote metadata available)",
        }
