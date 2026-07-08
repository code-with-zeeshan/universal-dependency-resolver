"""Install command generation — shared by CLI and API."""

import logging
import re
import shutil

from backend.orchestrator.resolve import _normalize_cuda
from backend.settings import INSTALLERS

logger = logging.getLogger(__name__)

_CUDA_VERSION_RE = re.compile(r"\+cu(\d+)$")


def _generate_install_command(
    ecosystem: str,
    packages: list[tuple[str, str]],
    cuda_version: str | None = None,
) -> str | None:
    """Generate a shell command to install *packages* for *ecosystem*.

    Parameters
    ----------
    ecosystem
        Ecosystem identifier (e.g. ``"pypi"``, ``"npm"``).
    packages
        List of ``(name, version)`` tuples.
    cuda_version
        If set, PyPI packages with ``+cu*`` version suffixes are filtered
        to only include versions matching this CUDA version.

    Returns
    -------
    A shell command string, or ``None`` if no installer is known.
    """
    if not packages:
        return None
    installer = INSTALLERS.get(ecosystem)
    if not installer:
        logger.warning("No installer known for ecosystem: %s", ecosystem)
        return None

    specs: list[str] = []
    for name, ver in packages:
        if ecosystem == "npm":
            specs.append(f"{name}@{ver}")
        elif ecosystem == "pub":
            specs.append(f"{name}:{ver}")
        elif ecosystem in ("gomodules", "cocoapods") or ecosystem == "crates":
            specs.append(f"{name}@{ver}")
        elif ecosystem in ("homebrew",):
            specs.append(name)
        elif ecosystem in ("hex", "swift"):
            continue  # these ecosystems use a single resolve command for all pkgs
        else:
            # PyPI and most others: strip CUDA suffix for pip
            if ecosystem == "pypi" and cuda_version:
                m = _CUDA_VERSION_RE.search(ver)
                if m:
                    pkg_cuda = _normalize_cuda(m.group(1))
                    target_cuda = _normalize_cuda(cuda_version)
                    if pkg_cuda != target_cuda:
                        continue
                ver = _CUDA_VERSION_RE.sub("", ver)
            specs.append(f"{name}=={ver}")

    if not specs and ecosystem not in ("hex", "swift", "homebrew"):
        return None

    # swift and hex use a single command with no package list
    if ecosystem == "swift":
        return "swift package resolve"
    if ecosystem == "hex":
        return "mix deps.update"

    return " ".join(list(installer) + specs)


def _check_toolchain(ecosystem: str) -> bool:
    """Check whether the native tool for *ecosystem* is available on PATH."""
    installer = INSTALLERS.get(ecosystem)
    if not installer:
        return False
    tool = installer[0]
    return shutil.which(tool) is not None


def check_toolchains(ecosystems: list[str]) -> dict[str, bool]:
    """Check toolchain availability for a list of ecosystems."""
    return {eco: _check_toolchain(eco) for eco in ecosystems}
