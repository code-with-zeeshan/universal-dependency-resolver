"""Private registry authentication for data source clients.

Priority: explicit constructor arg > env var > .netrc
Ecosystem env vars follow the pattern: {ECOSYSTEM}_AUTH_TOKEN, {ECOSYSTEM}_AUTH_TYPE, etc.
"""

import base64
import logging
import os
from netrc import NetrcParseError, netrc
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Map ecosystem slugs to env var name prefixes (uppercased)
_ECOSYSTEM_AUTH_ENV = {
    "pypi": "PYPI",
    "npm": "NPM",
    "crates": "CRATES",
    "gomodules": "GOMODULES",
    "maven": "MAVEN",
    "nuget": "NUGET",
    "rubygems": "RUBYGEMS",
    "conda": "CONDA",
    "packagist": "PACKAGIST",
    "pub": "PUB",
    "gradle": "GRADLE",
    "swift": "SWIFT",
    "hex": "HEX",
    "haskell": "HASKELL",
    "cocoapods": "COCOAPODS",
    "homebrew": "HOMEBREW",
    "apt": "APT",
    "apk": "APK",
}

# Which auth types are supported
AUTH_TYPES = ("bearer", "basic", "header")


def resolve_auth_headers(
    ecosystem: str,
    registry_url: str | None = None,
    explicit_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    """Resolve authentication headers for a given ecosystem and registry URL.

    Priority:
      1. ``explicit_headers`` — caller-injected (constructor arg).
      2. Environment variables — ``{PREFIX}_AUTH_TOKEN``, ``{PREFIX}_AUTH_TYPE``,
         ``{PREFIX}_AUTH_USERNAME`` / ``{PREFIX}_AUTH_PASSWORD``.
      3. ``.netrc`` file — matched by hostname from ``registry_url``.

    Returns a dict of header key → value (may be empty).
    """
    headers: dict[str, str] = {}

    # ---- Priority 1: explicit headers ----
    if explicit_headers:
        headers.update(explicit_headers)
        return headers

    # ---- Priority 2: environment variables ----
    prefix = _ECOSYSTEM_AUTH_ENV.get(ecosystem, ecosystem.upper())
    token = os.getenv(f"{prefix}_AUTH_TOKEN", "")
    auth_type = os.getenv(f"{prefix}_AUTH_TYPE", "bearer").lower()
    username = os.getenv(f"{prefix}_AUTH_USERNAME", "")
    password = os.getenv(f"{prefix}_AUTH_PASSWORD", "")

    if token:
        _apply_auth_header(headers, token, auth_type)
        return headers

    if username and password:
        _apply_basic_auth(headers, username, password)
        return headers

    # ---- Priority 3: .netrc ----
    if registry_url:
        _apply_netrc(headers, registry_url)

    return headers


def _apply_auth_header(headers: dict[str, str], token: str, auth_type: str) -> None:
    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {token}"
    elif auth_type == "basic":
        encoded = base64.b64encode(f"{token}:".encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    elif auth_type == "header":
        key, value = token.split(":", 1) if ":" in token else ("X-Auth-Token", token)
        headers[key] = value
    else:
        logger.warning("Unknown auth_type '%s', defaulting to Bearer", auth_type)
        headers["Authorization"] = f"Bearer {token}"


def _apply_basic_auth(headers: dict[str, str], username: str, password: str) -> None:
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    headers["Authorization"] = f"Basic {encoded}"


def _apply_netrc(headers: dict[str, str], url: str) -> None:
    try:
        host = urlparse(url).hostname
        if not host:
            return
        n = netrc()
        auth = n.authenticators(host)
        if auth:
            login, _account, password = auth
            if password:
                _apply_basic_auth(headers, login, password)
    except (FileNotFoundError, NetrcParseError, OSError):
        pass
