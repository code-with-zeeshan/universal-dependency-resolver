"""GNU Guix — EcosystemPlugin for Guix manifests and packages."""

import logging
import re
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("guix", name="GNU Guix", auth_prefix="GUIX")
class GuixPlugin(EcosystemPlugin):
    """Plugin for GNU Guix packages — recognizes guix.scm / manifest.scm."""

    ecosystem = "guix"

    manifests = [
        PluginManifest(glob="guix.scm", parser="parse_guix_scm"),
        PluginManifest(glob="manifest.scm", parser="parse_guix_scm"),
    ]

    @staticmethod
    def parse_guix_scm(content: str) -> list[dict]:
        """Parse a Guix manifest for package references.

        Handles patterns like:
          (list "python" "curl")
          (specification->package "python")
          (packages->manifest (list "gcc" "make"))
        """
        deps: list[dict] = []
        seen: set[str] = set()

        # Find all double-quoted strings that look like package names
        # Filter to avoid matching Guix internals (e.g. module paths)
        # Accept: alphabetic, hyphens, digits, + in names
        for m in re.finditer(
            r'"([a-zA-Z][a-zA-Z0-9@+\-_.]*(?:/[a-zA-Z][a-zA-Z0-9+\-_.]*)*)"', content
        ):
            name = m.group(1)
            if not name or name in seen:
                continue
            # Skip things that look like file paths, URLs, version-only tokens
            if name.startswith(("/", ".", "http")):
                continue
            if re.match(r"^\d+[\d.]*\d$", name):
                continue
            seen.add(name)
            deps.append({"name": name, "version": "*", "_ecosystem": "guix"})

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
            "ecosystem": "guix",
            "version": "latest",
            "versions": [{"version": "latest"}],
            "dependencies": {},
            "description": "GNU Guix package (no remote metadata available)",
        }
