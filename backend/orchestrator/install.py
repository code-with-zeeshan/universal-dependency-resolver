"""Install command generation — shared by CLI and API."""

import logging

logger = logging.getLogger(__name__)


def _generate_install_command(
    ecosystem: str,
    packages: list[tuple[str, str]],
) -> str | None:
    if not packages:
        return None
    installers = {
        "pypi": ("pip", "install"),
        "npm": ("npm", "install"),
        "crates": ("cargo", "add"),
        "gomodules": ("go", "get"),
        "conda": ("conda", "install"),
        "rubygems": ("gem", "install"),
        "packagist": ("composer", "require"),
        "pub": ("dart", "pub", "add"),
        "nuget": ("dotnet", "add", "package"),
        "cocoapods": ("pod", "install"),
        "maven": ("mvn", "dependency:copy-dependencies"),
    }
    installer = installers.get(ecosystem)
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
