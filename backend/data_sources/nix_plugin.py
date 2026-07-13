"""Nix — EcosystemPlugin for Nix derivations and flakes."""

import json
import logging
import re
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginLockFile,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("nix", name="Nix", auth_prefix="NIX")
class NixPlugin(EcosystemPlugin):
    """Plugin for Nix packages — recognizes default.nix, shell.nix, flake.nix, flake.lock."""

    ecosystem = "nix"

    manifests = [
        PluginManifest(glob="default.nix", parser="parse_nix"),
        PluginManifest(glob="shell.nix", parser="parse_nix"),
        PluginManifest(glob="flake.nix", parser="parse_nix"),
    ]

    lock_files = [
        PluginLockFile(glob="flake.lock", parser="parse_nix_lock"),
    ]

    @staticmethod
    def parse_nix(content: str) -> list[dict]:
        """Parse a Nix expression for buildInputs / propagatedBuildInputs."""
        deps: list[dict] = []

        # Find buildInputs / propagatedBuildInputs = [ ... ] blocks
        in_block = False
        block_depth = 0
        block_parts: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith(("#", "//")):
                continue

            if not in_block:
                m = re.search(
                    r"(buildInputs|propagatedBuildInputs|nativeBuildInputs|checkInputs)\s*=\s*\[",
                    stripped,
                )
                if m:
                    in_block = True
                    block_depth = 1
                    remainder = stripped[m.end() :]
                    if "]" in remainder:
                        block_depth -= remainder.count("]")
                        if block_depth <= 0:
                            in_block = False
                            block_parts.append(remainder[: remainder.index("]")])
                            continue
                    block_parts.append(remainder)
                    continue
            else:
                block_depth += stripped.count("[")
                block_depth -= stripped.count("]")
                if block_depth <= 0:
                    in_block = False
                    idx = stripped.index("]") if "]" in stripped else len(stripped)
                    block_parts.append(stripped[:idx])
                    text = " ".join(block_parts)
                    NixPlugin._extract_nix_pkgs(text, deps)
                    block_parts = []
                    continue
                block_parts.append(stripped)

        # Also handle multi-line blocks that don't close with ]
        if block_parts:
            text = " ".join(block_parts)
            NixPlugin._extract_nix_pkgs(text, deps)

        return deps

    @staticmethod
    def _extract_nix_pkgs(text: str, deps: list[dict]) -> None:
        """Extract package references from Nix expression text."""
        seen_pkgs: set[tuple[str, str]] = set()
        # Match pkgs.packageName, python3Packages.packageName, or bare identifiers
        for token in re.findall(r"[a-zA-Z_][\w.]*(?:\.[a-zA-Z_][\w.]+)*", text):
            if not token or token in ("pkgs", "inputs", "self"):
                continue
            if (
                "python3Packages." in token
                or "python310Packages." in token
                or "python311Packages." in token
                or "python312Packages." in token
            ):
                # python3Packages.requests → pypi ecosystem
                for prefix in (
                    "python3Packages.",
                    "python310Packages.",
                    "python311Packages.",
                    "python312Packages.",
                ):
                    if token.startswith(prefix):
                        pkg_name = token[len(prefix) :]
                        if pkg_name and pkg_name not in ("pkgs", "inputs", "self"):
                            key = (pkg_name, "pypi")
                            if key not in seen_pkgs:
                                seen_pkgs.add(key)
                                deps.append({"name": pkg_name, "version": "*", "_ecosystem": "pypi"})
                        break
            elif token.startswith("pkgs."):
                pkg_name = token[len("pkgs.") :]
                # Handle nested attribute accesses: pkgs.python3.pkgs.requests → take first segment
                pkg_name = pkg_name.split(".", 1)[0] if "." in pkg_name else pkg_name
                if pkg_name and pkg_name not in ("pkgs", "inputs", "self"):
                    key = (pkg_name, "nix")
                    if key not in seen_pkgs:
                        seen_pkgs.add(key)
                        deps.append({"name": pkg_name, "version": "*", "_ecosystem": "nix"})
            # Bare name (e.g., "hello" in buildInputs = [ hello ])
            elif token not in ("pkgs", "inputs", "self", "lib"):
                key = (token, "nix")
                if key not in seen_pkgs:
                    seen_pkgs.add(key)
                    deps.append({"name": token, "version": "*", "_ecosystem": "nix"})

    @staticmethod
    def parse_nix_lock(content: str) -> dict[str, dict[str, Any]]:
        """Parse flake.lock into a name -> {version} map."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return {}

        nodes = data.get("nodes", {})
        root = nodes.get("root", {})
        root_inputs = root.get("inputs", {})

        packages: dict[str, dict[str, Any]] = {}

        # root_inputs maps name → node_key (string reference), not a dict
        seen_nodes: set[str] = set()
        for input_name, node_key in root_inputs.items():
            if isinstance(node_key, dict):
                node_key = input_name
            if node_key in seen_nodes:
                continue
            seen_nodes.add(node_key)
            node = nodes.get(node_key, {})
            locked = node.get("locked", {})
            original_ref = node.get("original", {})
            version = locked.get("rev", locked.get("version", "latest"))
            if isinstance(version, str) and len(version) > 12:
                version = version[:12]
            nar_hash = locked.get("narHash", "")

            # Determine display name
            display = original_ref.get("id") or original_ref.get("path") or input_name

            info: dict[str, Any] = {
                "version": version,
            }
            if nar_hash:
                info["narHash"] = nar_hash
            packages[display] = info

        # Also include non-root nodes referenced by others
        for node_id, node in nodes.items():
            if node_id in ("root",) or node_id in seen_nodes:
                continue
            locked = node.get("locked", {})
            if locked.get("rev") or locked.get("version"):
                original_ref = node.get("original", {})
                display = original_ref.get("id") or original_ref.get("path") or node_id
                if display not in packages:
                    ver = locked.get("rev", locked.get("version", "latest"))
                    if isinstance(ver, str) and len(ver) > 12:
                        ver = ver[:12]
                    sub_info: dict[str, Any] = {
                        "version": ver,
                    }
                    if locked.get("narHash"):
                        sub_info["narHash"] = locked["narHash"]
                    packages[display] = sub_info

        return packages

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
            "ecosystem": "nix",
            "version": "latest",
            "versions": [{"version": "latest"}],
            "dependencies": {},
            "description": "Nix package (no remote metadata available)",
        }
