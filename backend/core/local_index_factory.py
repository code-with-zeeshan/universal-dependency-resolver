"""Factory for per-ecosystem local index managers.

Returns the appropriate manager instance based on the ecosystem string.
Supports all 28 ecosystems:
  - 3 with full specialized managers (pypi, npm, crates)
  - 10 with search-based listing sync
  - 13 with no listing API (sync returns 0, lookup falls through to API)
  - 2 internal (docs, custom_db — sync skipped)
"""

from __future__ import annotations

import logging

from backend import settings as _settings
from backend.core.local_index import LocalIndexManager
from backend.core.local_index_crates import CratesIndexManager
from backend.core.local_index_npm import NpmIndexManager
from backend.core.local_index_pypi import PyPIIndexManager
from backend.core.registry_index_manager import NullIndexManager, SearchApiIndexManager

logger = logging.getLogger(__name__)

_SEARCH_SYNC_CONFIG: dict[str, dict] = {
    "conda": {
        "url": "https://api.anaconda.org/search?q=&type=conda",
        "page_size": 50,
        "parser": lambda data: [
            {
                "name": pkg.get("full_name", "").split("/")[-1],
                "versions": [{"version": pkg.get("latest_version", "")}],
            }
            for pkg in data.get("results", [])
            if pkg.get("full_name")
        ],
        "next_page": lambda resp, page, page_size: resp.get("count", 0) > page * page_size,
        "page_param": "start",
        "page_calc": lambda page, page_size: page * page_size,
    },
    "maven": {
        "url": "https://search.maven.org/solrsearch/select?q=*&rows=1000&wt=json",
        "page_size": 1000,
        "parser": lambda data: [
            {"name": doc.get("id", ""), "versions": [{"version": doc.get("latestVersion", "")}]}
            for doc in data.get("response", {}).get("docs", [])
            if doc.get("id")
        ],
        "next_page": lambda resp, page, page_size: (
            resp.get("response", {}).get("numFound", 0) > (page + 1) * page_size
        ),
        "page_param": "start",
        "page_calc": lambda page, page_size: (page + 1) * page_size,
        "max_pages": 10,
    },
    "nuget": {
        "url": "https://azuresearch-usnc.nuget.org/query?q=&skip=0&take=1000&prerelease=false",
        "page_size": 1000,
        "parser": lambda data: [
            {"name": pkg.get("id", ""), "versions": [{"version": pkg.get("version", "")}]}
            for pkg in data.get("data", [])
            if pkg.get("id")
        ],
        "next_page": lambda resp, page, page_size: (
            resp.get("@totalResults", 0) > (page + 1) * page_size
        ),
        "page_param": "skip",
        "page_calc": lambda page, page_size: (page + 1) * page_size,
        "max_pages": 10,
    },
    "rubygems": {
        "url": "https://rubygems.org/api/v1/search.json?query=a",
        "page_size": 100,
        "parser": lambda data: [
            {"name": pkg.get("name", ""), "versions": [{"version": pkg.get("version", "")}]}
            for pkg in data
            if isinstance(pkg, dict) and pkg.get("name")
        ],
        "use_alpha_enumeration": True,
    },
    "packagist": {
        "url": "https://packagist.org/packages/list.json",
        "page_size": 0,
        "parser": lambda data: [
            {"name": name, "versions": []} for name in data.get("packageNames", [])
        ],
        "single_page": True,
    },
    "pub": {
        "url": "https://pub.dev/api/search?q=a&size=250",
        "page_size": 250,
        "parser": lambda data: [
            {
                "name": pkg.get("package", ""),
                "versions": [{"version": pkg.get("latest", {}).get("version", "")}],
            }
            for pkg in data.get("packages", [])
            if pkg.get("package")
        ],
        "use_alpha_enumeration": True,
    },
    "hex": {
        "url": "https://hex.pm/api/packages?sort=name&per_page=100",
        "page_size": 100,
        "parser": lambda data: [
            {"name": pkg.get("name", ""), "versions": [{"version": pkg.get("latest_version", "")}]}
            for pkg in data
            if isinstance(pkg, dict) and pkg.get("name")
        ],
        "next_page": lambda resp, page, page_size: len(resp) >= page_size,
        "page_param": "page",
        "page_calc": lambda page, page_size: page + 1,
        "max_pages": 50,
    },
    "cocoapods": {
        "url": "https://trunk.cocoapods.org/api/v1/pods",
        "page_size": 0,
        "parser": lambda data: [
            {"name": pkg.get("name", ""), "versions": [{"version": pkg.get("version", "")}]}
            for pkg in data
            if isinstance(pkg, dict) and pkg.get("name")
        ],
        "single_page": True,
    },
    "homebrew": {
        "url": "https://formulae.brew.sh/api/formula.json",
        "page_size": 0,
        "parser": lambda data: [
            {
                "name": pkg.get("name", ""),
                "versions": [{"version": pkg.get("versions", {}).get("stable", "")}],
            }
            for pkg in data
            if isinstance(pkg, dict) and pkg.get("name")
        ],
        "single_page": True,
    },
}

_ALPHA_PREFIXES = [chr(c) for c in range(ord("a"), ord("z") + 1)] + [str(i) for i in range(10)]


def get_local_index(
    ecosystem: str,
) -> (
    LocalIndexManager
    | NpmIndexManager
    | PyPIIndexManager
    | CratesIndexManager
    | SearchApiIndexManager
    | NullIndexManager
    | None
):
    """Return an index manager for *ecosystem*, or ``None`` if disabled.

    Supports all 28 registered ecosystems.
    When ``ENABLE_LOCAL_INDEX`` is ``false``, returns ``None``.
    """
    if not _settings.ENABLE_LOCAL_INDEX:
        return None

    eco = ecosystem.lower().strip()

    if eco == "pypi":
        return PyPIIndexManager(update_interval=_settings.LOCAL_INDEX_UPDATE_INTERVAL)
    if eco == "npm":
        return NpmIndexManager(update_interval=_settings.LOCAL_INDEX_UPDATE_INTERVAL)
    if eco == "crates":
        return CratesIndexManager(update_interval=_settings.LOCAL_INDEX_UPDATE_INTERVAL)

    if eco in _SEARCH_SYNC_CONFIG:
        config = _SEARCH_SYNC_CONFIG[eco]
        return SearchApiIndexManager(
            ecosystem=eco,
            update_interval=_settings.LOCAL_INDEX_UPDATE_INTERVAL,
            url=config["url"],
            page_size=config.get("page_size", 0),
            parser=config["parser"],
            single_page=config.get("single_page", False),
            use_alpha_enumeration=config.get("use_alpha_enumeration", False),
            next_page=config.get("next_page"),
            page_param=config.get("page_param"),
            page_calc=config.get("page_calc"),
            max_pages=config.get("max_pages"),
            alpha_prefixes=_ALPHA_PREFIXES if config.get("use_alpha_enumeration") else None,
        )

    if eco in ("docs", "custom_db"):
        logger.debug("Skipping local index for internal ecosystem: %s", ecosystem)
        return NullIndexManager(
            ecosystem=eco, update_interval=_settings.LOCAL_INDEX_UPDATE_INTERVAL
        )

    logger.debug("No local index listing API for ecosystem: %s", ecosystem)
    return NullIndexManager(ecosystem=eco, update_interval=_settings.LOCAL_INDEX_UPDATE_INTERVAL)
