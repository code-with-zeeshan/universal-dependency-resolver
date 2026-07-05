"""Install command generation — shared by CLI and API."""

import logging

from backend.settings import INSTALLERS

logger = logging.getLogger(__name__)


def _generate_install_command(
    ecosystem: str,
    packages: list[tuple[str, str]],
) -> str | None:
    if not packages:
        return None
    installer = INSTALLERS.get(ecosystem)
    if not installer:
        logger.warning("No installer known for ecosystem: %s", ecosystem)
        return None
    if ecosystem == "npm":
        specs = [f"{name}@{ver}" for name, ver in packages]
    elif ecosystem == "pub":
        specs = [f"{name}:{ver}" for name, ver in packages]
    elif ecosystem in ("gomodules", "cocoapods"):
        specs = [f"{name}@{ver}" for name, ver in packages]
    else:
        specs = [f"{name}=={ver}" for name, ver in packages]
    return " ".join(list(installer) + specs)
