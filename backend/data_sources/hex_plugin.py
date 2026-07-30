"""Hex.pm (Elixir/Erlang) — EcosystemPlugin implementation."""

import asyncio
import logging
import re
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginLockFile,
    PluginManifest,
    register_ecosystem,
)
from ..core.utils import normalize_package_name

logger = logging.getLogger(__name__)


@register_ecosystem("hex", name="Hex.pm (Elixir/Erlang)", auth_prefix="HEX")
class HexPlugin(EcosystemPlugin):
    """Plugin for hex.pm — the Elixir/Erlang package registry."""

    ecosystem = "hex"

    manifests = [
        PluginManifest(glob="mix.exs", parser="parse_mix_exs"),
    ]

    lock_files = [
        PluginLockFile(glob="mix.lock", parser="parse_mix_lock"),
    ]

    # ------------------------------------------------------------------
    # Manifest parser (called by ManifestDetector via _get_parser)
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_hex_version(raw: str) -> str:
        """Extract operator + version from a hex dependency string.

        Handles ``~> 1.7.0``, ``>= 1.0.0``, ``\"1.7.0\"``, etc.
        """
        ver_raw = raw.strip().strip('"').strip("'")
        if not ver_raw or ver_raw == "*":
            return "*"
        m = re.match(r"(~>\s*|>=\s*|>\s*|<=\s*|<\s*|==\s*)?(.+)", ver_raw)
        if m:
            op = m.group(1) or ""
            ver = m.group(2).strip()
            return f"{op}{ver}".strip()
        return ver_raw

    @staticmethod
    def parse_mix_exs(content: str) -> list[dict]:
        """Parse a mix.exs file for dependencies."""
        deps = []
        in_deps = False
        paren_depth = 0
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith(("#", "//")):
                continue
            if "defp deps" in stripped or "def deps" in stripped:
                in_deps = True
                continue
            if in_deps:
                if "end" in stripped:
                    break
                if stripped.startswith("{:"):
                    parts = stripped.strip().strip(",").split(",")
                    if len(parts) >= 1:
                        name = parts[0].strip("{:").strip()
                        version = HexPlugin._parse_hex_version(parts[1]) if len(parts) > 1 else "*"
                        deps.append({"name": name, "version": version})
                elif ":" in stripped and not stripped.startswith("["):
                    for char in stripped:
                        if char == "(":
                            paren_depth += 1
                        elif char == ")":
                            paren_depth -= 1
                    if paren_depth == 0 and stripped.endswith(","):
                        eq_idx = stripped.find(":")
                        if eq_idx > 0:
                            name = stripped[:eq_idx].strip()
                            rest = stripped[eq_idx + 1 :].strip().strip(",")
                            version = HexPlugin._parse_hex_version(rest)
                            deps.append({"name": name, "version": version})
        return deps

    # ------------------------------------------------------------------
    # Lock-file parser
    # ------------------------------------------------------------------
    @staticmethod
    def parse_mix_lock(content: str) -> dict[str, dict[str, Any]]:
        """Parse a mix.lock file into a name -> {version} map."""
        import re

        packages: dict[str, dict[str, Any]] = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("%"):
                continue
            line = line.rstrip(",")
            m = re.match(r'["\']([^"\']+)["\']\s*:', line)
            if not m:
                continue
            name = m.group(1)
            inner = line[m.end() :].strip().lstrip("{").strip()
            parts = inner.split(",")
            if len(parts) >= 3:
                ver_m = re.search(r'["\']([^"\']+)["\']', parts[2])
                if ver_m:
                    packages[name] = {"version": ver_m.group(1)}
                    # Extract deps from the list at parts index 4 (if present)
                    dep_list = (
                        re.findall(r'["\']([^"\']+)["\']', parts[4]) if len(parts) > 4 else []
                    )
                    if dep_list:
                        packages[name]["dependencies"] = dict.fromkeys(dep_list)
        return packages

    # ------------------------------------------------------------------
    # Manifest updater
    # ------------------------------------------------------------------
    @staticmethod
    def update_mix_exs(content: str, package_name: str, resolved_version: str) -> str | None:
        """Update a version constraint in mix.exs for *package_name*."""
        import re

        pattern = re.compile(
            r'(:\s*)("?)' + re.escape(package_name) + r'("?\s*,?\s*")([^"]+)(")',
            re.MULTILINE,
        )
        new_content, count = pattern.subn(
            lambda m: (
                m.group(1) + m.group(2) + package_name + m.group(3) + resolved_version + m.group(5)
            ),
            content,
        )
        if count == 0:
            alt_pattern = re.compile(
                r'(:\s*)([a-zA-Z_]+)\s*,?\s*"([^"]+)"',
                re.MULTILINE,
            )
            match = alt_pattern.search(content)
            if match and match.group(2) == package_name:
                start, end = match.start(3), match.end(3)
                new_content = content[:start] + resolved_version + content[end:]
                count = 1
        return new_content if count > 0 else None

    # ------------------------------------------------------------------
    # Data source
    # ------------------------------------------------------------------
    @staticmethod
    def _default_base_url() -> str:
        return "https://hex.pm/api"

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        """Fetch package metadata from the registry."""
        pkg = normalize_package_name(package_name)
        try:
            data = await self._get(f"{self.base_url}/packages/{pkg}")
            if not data:
                return None
            releases = data.get("releases", [])
            versions = []
            for r in releases:
                v = r.get("version", "") if isinstance(r, dict) else str(r)
                versions.append({"version": v})
            latest = versions[0]["version"] if versions else "unknown"

            # Fetch per-version deps from the release-level API.
            # Each version's /releases/{version} endpoint includes a
            # "requirements" dict with per-version dependency data.
            deps: dict[str, dict[str, str]] = {"dependencies": {}, "optional_dependencies": {}}
            if include_dependencies and versions:
                _hex_sem = asyncio.Semaphore(5)

                async def _fetch_version_deps(ver: str) -> tuple[str, dict, dict]:
                    async with _hex_sem:
                        try:
                            rd = await self._get(f"{self.base_url}/packages/{pkg}/releases/{ver}")
                            reqs = {}
                            opt_flags = {}
                            if rd and "requirements" in rd:
                                for dn, di in rd["requirements"].items():
                                    if isinstance(di, dict):
                                        reqs[dn] = di.get("requirement", "*")
                                        if di.get("optional"):
                                            opt_flags[dn] = True
                            return ver, reqs, opt_flags
                        except Exception:
                            return ver, {}, {}

                # Fetch deps for latest N versions to bound API calls.
                # The pipeline picks the newest constraint-matched version's
                # deps, so covering the latest ~10 is sufficient.
                targets = [v["version"] for v in versions[:10]]
                version_deps_results = await asyncio.gather(
                    *[_fetch_version_deps(v) for v in targets],
                    return_exceptions=True,
                )
                ver_deps_map: dict[str, dict[str, str]] = {}
                ver_opt_map: dict[str, dict[str, bool]] = {}
                for vd in version_deps_results:
                    if isinstance(vd, tuple) and len(vd) == 3:
                        ver, reqs, opts = vd
                        ver_deps_map[ver] = reqs
                        if opts:
                            ver_opt_map[ver] = opts

                # Store per-version deps in each version entry,
                # separating optional deps so the solver doesn't
                # try to resolve them as required dependencies.
                for v in versions:
                    vstr = v["version"]
                    if ver_deps_map.get(vstr):
                        req_deps = {}
                        all_deps = ver_deps_map[vstr]
                        opt_set = set(ver_opt_map.get(vstr, {}))
                        for dn, req in all_deps.items():
                            if dn not in opt_set:
                                req_deps[dn] = req
                        if req_deps:
                            v["dependencies"] = req_deps
                        if opt_set:
                            v["optional_dependencies"] = {
                                dn: all_deps[dn] for dn in opt_set if dn in all_deps
                            }

                # Top-level deps — use the latest version's requirements,
                # separating optional deps so the pipeline marks them correctly.
                latest_opt = ver_opt_map.get(latest, {})
                latest_deps = ver_deps_map.get(latest, {})
                for dep_name, req in latest_deps.items():
                    if latest_opt.get(dep_name):
                        deps["optional_dependencies"][dep_name] = req
                    else:
                        deps["dependencies"][dep_name] = req

            return {
                "name": pkg,
                "version": latest,
                "versions": versions,
                "dependencies": deps,
            }
        except Exception as e:
            logger.error(f"Hex error for {package_name}: {e}")
            return None

    async def get_package_versions(
        self,
        package_name: str,
        filters: dict | None = None,
    ) -> list[dict]:
        """Use dedicated Hex.pm /packages/{name} endpoint for versions."""
        pkg = normalize_package_name(package_name)
        try:
            data = await self._get(f"{self.base_url}/packages/{pkg}")
            if not data:
                return []
            releases = data.get("releases", [])
            return [
                {"version": r.get("version", "") if isinstance(r, dict) else str(r)}
                for r in releases
            ]
        except Exception as e:
            logger.error(f"Hex get_package_versions error for {package_name}: {e}")
            return []

    async def search_packages(self, query: str, limit: int = 20) -> list[dict]:
        """Search for packages matching the query."""
        data = await self._get(
            f"{self.base_url}/packages",
            params={"sort": "name", "search": query, "per_page": limit},
        )
        if not data:
            return []
        return data.get("packages", data) if isinstance(data, dict) else data
