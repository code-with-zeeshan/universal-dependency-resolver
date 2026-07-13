"""Conan — EcosystemPlugin for the C/C++ package manager."""

import logging
import re
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("conan", name="Conan (C/C++)", auth_prefix="CONAN")
class ConanPlugin(EcosystemPlugin):
    """Plugin for Conan packages — recognizes conanfile.py and conanfile.txt."""

    ecosystem = "conan"

    manifests = [
        PluginManifest(glob="conanfile.txt", parser="parse_conanfile_txt"),
        PluginManifest(glob="conanfile.py", parser="parse_conanfile_py"),
    ]

    @staticmethod
    def parse_conanfile_txt(content: str) -> list[dict]:
        """Parse conanfile.txt for ``[requires]`` section.

        Lines look like::

            pkg/1.2.3
            pkg/1.2.3@user/channel
        """
        deps: list[dict] = []
        in_requires = False

        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("["):
                in_requires = stripped.lower().startswith("[requires]")
                continue
            if not in_requires or not stripped or stripped.startswith("#"):
                continue

            # pkg/1.2.3 or pkg/1.2.3@user/channel
            parts = stripped.split("/", 1)
            if len(parts) < 2:
                continue
            name = parts[0].strip()
            rest = parts[1].strip()
            # rest may be "1.2.3" or "1.2.3@user/channel"
            version = rest.split("@", 1)[0].strip()
            if name:
                deps.append({"name": name, "version": version, "_ecosystem": "conan"})

        return deps

    @staticmethod
    def parse_conanfile_py(content: str) -> list[dict]:
        """Parse conanfile.py for ``self.requires("pkg/1.2.3")`` or
        ``requires = ("pkg/1.2.3",)`` patterns.
        """
        deps: list[dict] = []
        seen: set[str] = set()

        # self.requires("pkg/1.2.3")
        for m in re.finditer(r'self\.requires\s*\(\s*"([^"]+)"\s*\)', content):
            spec = m.group(1)
            parts = spec.split("/", 1)
            name = parts[0].strip()
            version = parts[1].strip() if len(parts) > 1 else "*"
            key = f"{name}@{version}"
            if key not in seen:
                seen.add(key)
                deps.append({"name": name, "version": version, "_ecosystem": "conan"})

        # requires = ("pkg/1.2.3", "other/2.0.0")
        requires_match = re.search(r"requires\s*=\s*\(([^)]*)\)", content, re.DOTALL)
        if requires_match:
            inner = requires_match.group(1)
            for spec in re.finditer(r'"([^"]+)"', inner):
                spec_val = spec.group(1)
                parts = spec_val.split("/", 1)
                name = parts[0].strip()
                version = parts[1].strip() if len(parts) > 1 else "*"
                key = f"{name}@{version}"
                if key not in seen:
                    seen.add(key)
                    deps.append({"name": name, "version": version, "_ecosystem": "conan"})

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
            "ecosystem": "conan",
            "version": "latest",
            "versions": [{"version": "latest"}],
            "dependencies": {},
            "description": "Conan package (no remote metadata available)",
        }
