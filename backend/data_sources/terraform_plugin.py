"""Terraform — EcosystemPlugin for Terraform (`.terraform.lock.hcl`)."""

import logging
import re
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("terraform", name="Terraform", auth_prefix="TERRAFORM")
class TerraformPlugin(EcosystemPlugin):
    """Plugin for Terraform — recognizes .terraform.lock.hcl."""

    ecosystem = "terraform"

    manifests = [
        PluginManifest(glob=".terraform.lock.hcl", parser="parse_terraform_lock"),
    ]

    @staticmethod
    def parse_terraform_lock(content: str) -> list[dict]:
        """Parse .terraform.lock.hcl for provider dependencies.

        Handles blocks like::

            provider "registry.terraform.io/hashicorp/aws" {
                version = "5.0.0"
                ...
            }

        Returns a list of dicts with ``name`` set to the provider source
        (e.g. ``hashicorp/aws``) and ``version`` from the ``version`` attribute.
        """
        if not isinstance(content, str):
            return []
        deps: list[dict] = []
        current_source: str | None = None
        in_block = False
        brace_depth = 0
        version = "*"

        for line in content.splitlines():
            stripped = line.strip()

            # Skip comments and blank lines
            if not stripped or stripped.startswith("#"):
                continue

            # Detect provider "SOURCE" {
            m = re.match(r'^provider\s+"([^"]+)"\s*\{$', stripped)
            if m:
                current_source = m.group(1)
                in_block = True
                brace_depth = 1
                version = "*"
                continue

            if in_block:
                # Track braces inside the block
                brace_depth += stripped.count("{")
                brace_depth -= stripped.count("}")

                # Extract version = "V"
                vm = re.match(r'^\s*version\s*=\s*"([^"]*)"', stripped)
                if vm:
                    version = vm.group(1) if vm.group(1) else "*"

                # Block closed
                if brace_depth <= 0:
                    if current_source:
                        deps.append(
                            {
                                "name": current_source,
                                "version": version,
                                "_ecosystem": "terraform",
                            }
                        )
                    current_source = None
                    in_block = False
                    version = "*"

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
            url = f"{self.base_url}/providers/{package_name}/versions"
            data = await self._get(url)
            if not data:
                return None
            raw_versions = data.get("versions", [])
            versions = [{"version": v["version"]} for v in raw_versions if isinstance(v, dict)]
            return {
                "name": package_name,
                "ecosystem": "terraform",
                "version": versions[0]["version"] if versions else "*",
                "versions": versions if include_versions else [],
                "dependencies": {},
            }
        except Exception as e:
            logger.warning("Terraform fetch failed for %s: %s", package_name, e)
            return None
