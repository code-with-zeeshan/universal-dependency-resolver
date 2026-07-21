"""Factory for per-ecosystem local index managers.

Returns the appropriate ``LocalIndexManager`` subclass based on
the ecosystem string.  Currently returns ``None`` for all ecosystems
— the per-ecosystem manager modules are ready but not yet wired in.
"""

from __future__ import annotations

import logging

from backend import settings as _settings

logger = logging.getLogger(__name__)


def get_local_index(ecosystem: str) -> object | None:
    """Return a per-ecosystem local index manager, or ``None``.

    Parameters
    ----------
    ecosystem:
        Lowercase ecosystem name (e.g. ``"pypi"``, ``"npm"``, ``"crates"``).

    Returns
    -------
    object or None
        A manager instance with ``search(name)``, ``get(name)``,
        ``sync()``, and ``last_updated``, or ``None`` if the ecosystem
        is not supported or ``ENABLE_LOCAL_INDEX`` is false.

    """
    if not _settings.ENABLE_LOCAL_INDEX:
        return None

    eco = ecosystem.lower().strip()

    from backend.core.local_index_crates import CratesIndexManager
    from backend.core.local_index_npm import NpmIndexManager
    from backend.core.local_index_pypi import PyPIIndexManager

    _MANAGERS: dict[str, type] = {
        "npm": NpmIndexManager,
        "pypi": PyPIIndexManager,
        "crates": CratesIndexManager,
    }

    cls = _MANAGERS.get(eco)
    if cls is not None:
        return cls(update_interval=_settings.LOCAL_INDEX_UPDATE_INTERVAL)

    logger.debug("No local index support for ecosystem: %s", ecosystem)
    return None
