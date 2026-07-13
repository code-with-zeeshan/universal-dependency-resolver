"""Docker Registry HTTP v2 client.

Implements the Docker Registry HTTP API v2 for resolving container image
manifests and tags.  Used by ``docker_plugin.py``.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# Default concurrency
_DOCKER_SEMAPHORE = asyncio.Semaphore(4)


class DockerRegistryClient:
    """Client for the Docker Registry HTTP API v2.

    *registry* — hostname (default ``registry-1.docker.io``).
    *auth_token* — optional Bearer token for private registries.
    """

    BASE_URL: str = "https://registry-1.docker.io/v2"
    RATE_LIMIT: int = 60  # requests per minute (token auth)

    def __init__(
        self,
        registry: str = "registry-1.docker.io",
        auth_token: str | None = None,
    ):
        self.registry = registry.rstrip("/")
        self.base_url = f"https://{registry}/v2"
        self._auth_token = auth_token
        self._session: aiohttp.ClientSession | None = None

    def clear_auth_token(self) -> None:
        """Clear the stored auth token from memory."""
        self._auth_token = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            headers = {}
            if self._auth_token:
                headers["Authorization"] = f"Bearer {self._auth_token}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def get_tags(self, image: str) -> list[str]:
        """List all tags for *image* (e.g. ``"library/python"``)."""
        session = await self._get_session()
        url = f"{self.base_url}/{image}/tags/list"
        async with _DOCKER_SEMAPHORE, session.get(url) as resp:
            if resp.status == 401:
                token = await self._authenticate(resp, image)
                if token:
                    return await self._retry_with_token(url, token)
            if resp.status != 200:
                logger.warning("Docker tags list %s → %d", url, resp.status)
                return []
            data = await resp.json()
        return data.get("tags", [])

    async def get_manifest(self, image: str, tag: str) -> dict[str, Any] | None:
        """Fetch the manifest for ``image:tag``.

        Returns the parsed manifest dict, or ``None`` on error.
        """
        session = await self._get_session()
        url = f"{self.base_url}/{image}/manifests/{tag}"
        headers = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
        async with _DOCKER_SEMAPHORE, session.get(url, headers=headers) as resp:
            if resp.status == 401:
                token = await self._authenticate(resp, image)
                if token:
                    return await self._retry_with_token(url, token, headers)
            if resp.status != 200:
                logger.debug("Docker manifest %s → %d", url, resp.status)
                return None
            manifest = await resp.json()
        return manifest

    async def resolve_image(self, image_ref: str) -> dict[str, Any]:
        """Resolve an image reference to a digest and metadata.

        Supports ``image:tag``, ``image@digest``, and bare ``image`` (→ latest).
        Returns ``{"image": ..., "tag": ..., "digest": ..., "manifest": ...}``.
        """
        image, tag, digest = self._parse_ref(image_ref)
        if digest:
            manifest = await self.get_manifest(image, digest)
        else:
            manifest = await self.get_manifest(image, tag or "latest")

        result: dict[str, Any] = {
            "image": image,
            "tag": tag or "latest",
            "digest": digest or "",
        }
        if manifest:
            result["manifest"] = manifest
            result["digest"] = result.get("digest") or manifest.get("config", {}).get("digest", "")
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _authenticate(self, resp: aiohttp.ClientResponse, image: str) -> str | None:
        """Handle 401 by fetching a Bearer token from the Www-Authenticate header."""
        auth_header = resp.headers.get("Www-Authenticate", "")
        m = re.search(r'realm="([^"]+)"', auth_header)
        if not m:
            return None
        realm = m.group(1)
        service = ""
        scope = f"repository:{image}:pull"
        m2 = re.search(r'service="([^"]+)"', auth_header)
        if m2:
            service = m2.group(1)
        token_url = f"{realm}?service={service}&scope={scope}"
        session = await self._get_session()
        async with session.get(token_url) as token_resp:
            if token_resp.status != 200:
                return None
            data = await token_resp.json()
        return data.get("token")

    async def _retry_with_token(
        self, url: str, token: str, extra_headers: dict[str, str] | None = None
    ) -> dict[str, Any] | list[Any] | None:
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {token}"}
        if extra_headers:
            headers.update(extra_headers)
        async with _DOCKER_SEMAPHORE, session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return None
            return await resp.json()

    @staticmethod
    def _parse_ref(ref: str) -> tuple[str, str | None, str | None]:
        """Parse ``image:tag``, ``image@sha256:...``, or bare ``image``."""
        image = ref
        tag: str | None = None
        digest: str | None = None

        if "@" in ref:
            image, digest = ref.split("@", 1)
        elif ":" in ref:
            parts = ref.split(":", 1)
            if "/" in parts[0] or len(parts) == 2:
                image, tag = parts

        # Default to library/ if no org
        if "/" not in image:
            image = f"library/{image}"
        return image, tag, digest
