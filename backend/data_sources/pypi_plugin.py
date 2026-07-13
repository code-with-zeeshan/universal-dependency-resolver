"""PyPI (Python) — EcosystemPlugin adapter delegating to legacy PyPIClient."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("pypi", name="PyPI (Python)", auth_prefix="PYPI")
class PypiPlugin(EcosystemPlugin):
    """Plugin for the Python Package Index — delegates to the existing PyPIClient."""

    ecosystem = "pypi"

    manifests = [
        PluginManifest(glob="requirements.txt", parser="parse_requirements"),
        PluginManifest(glob="requirements.in", parser="parse_requirements"),
        PluginManifest(glob="Pipfile", parser="parse_pipfile"),
        PluginManifest(glob="Pipfile.lock", parser="parse_pipfile_lock"),
        PluginManifest(glob="pyproject.toml", parser="parse_pyproject"),
        PluginManifest(glob="poetry.lock", parser="parse_poetry_lock"),
        PluginManifest(glob="uv.lock", parser="parse_uv_lock"),
    ]

    # Manifest/lock parsers — thin stubs that delegate to ManifestDetector
    # at runtime via the static MANIFEST_PATTERNS list.

    @staticmethod
    def parse_requirements(content: str) -> list[dict]:
        return []

    @staticmethod
    def parse_pipfile(content: str) -> list[dict]:
        return []

    @staticmethod
    def parse_pipfile_lock(content: str) -> list[dict]:
        return []

    @staticmethod
    def parse_pyproject(content: str) -> list[dict]:
        return []

    @staticmethod
    def parse_poetry_lock(content: str) -> list[dict]:
        return []

    @staticmethod
    def parse_uv_lock(content: str) -> list[dict]:
        return []

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from .pypi_client import PyPIClient

            self._legacy_client = PyPIClient()
        return self._legacy_client

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        client = self._get_client()
        data = await client.get_package_info_async(package_name)
        if data is None:
            return None
        if not include_versions:
            data.pop("versions", None)
        if not include_dependencies:
            data.pop("dependencies", None)
        return data

    async def get_package_versions(
        self,
        package_name: str,
        filters: dict | None = None,
    ) -> list[dict]:
        client = self._get_client()
        return await client.get_versions(package_name)

    async def search_packages(self, query: str, limit: int = 20) -> list[dict]:
        client = self._get_client()
        return await client.search(query, limit=limit)

    async def get_artifact_hash(self, package_name: str, version: str) -> dict | None:
        client = self._get_client()
        return await client.get_artifact_hash(package_name, version)
