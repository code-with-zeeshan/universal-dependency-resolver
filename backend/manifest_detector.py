"""Manifest file discovery and parsing for `udr lock`.

Auto-detects known dependency manifests in a directory,
parses them into a uniform package list, and maps each
package to its ecosystem for resolution.
"""

import logging
import re
from pathlib import Path
from typing import Any

from .core._json import loads
from .core.utils import normalize_package_name

logger = logging.getLogger(__name__)


def _strip_inline_comment(line: str) -> str:
    """Remove inline # comments from a dependency line, respecting quotes."""
    in_quote = None
    for i, ch in enumerate(line):
        if ch in ("'", '"') and in_quote is None:
            in_quote = ch
        elif ch == in_quote:
            in_quote = None
        elif ch == "#" and in_quote is None:
            return line[:i].rstrip()
    return line


# Directories to exclude from manifest detection
EXCLUDED_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "dist",
    "build",
    ".tox",
    ".eggs",
    "env",
    ".env",
    "examples",
    "example",
    "test",
    "tests",
    "docs",
    "documentation",
}


# Map filename patterns → (ecosystem, parser_func)
# Start with built-in manifests, then extend with plugin manifests
MANIFEST_PATTERNS: list[tuple[str, str, str]] = [
    ("requirements.txt", "pypi", "requirements"),
    ("requirements.in", "pypi", "requirements"),
    ("requirements-dev.txt", "pypi", "requirements"),
    ("Pipfile", "pypi", "pipfile"),
    ("Pipfile.lock", "pypi", "pipfile_lock"),
    ("pyproject.toml", "pypi", "pyproject"),
    ("package.json", "npm", "package_json"),
    ("package-lock.json", "npm", "package_lock"),
    ("yarn.lock", "npm", "yarn_lock"),
    ("Cargo.toml", "cargo", "cargo_toml"),
    ("Cargo.lock", "cargo", "cargo_lock"),
    ("go.mod", "go", "go_mod"),
    ("environment.yml", "conda", "conda_env"),
    ("environment.yaml", "conda", "conda_env"),
    ("Gemfile", "rubygems", "gemfile"),
    ("composer.json", "packagist", "composer_json"),
    ("pnpm-lock.yaml", "npm", "pnpm_lock"),
    ("pubspec.yaml", "pub", "pubspec"),
    ("*-requirements.txt", "pypi", "requirements"),
    ("requirements/*.txt", "pypi", "requirements"),
    ("requirements/*.in", "pypi", "requirements"),
    ("coordinator/*.txt", "pypi", "requirements"),
    ("coordinator/*.in", "pypi", "requirements"),
    ("dependencies/*.txt", "pypi", "requirements"),
    ("dependencies/*.in", "pypi", "requirements"),
    ("build.gradle", "gradle", "gradle"),
    ("build.gradle.kts", "gradle", "gradle"),
    ("Package.swift", "swift", "swift"),
    ("mix.exs", "hex", "hex"),
    ("*.cabal", "haskell", "cabal"),
    ("pom.xml", "maven", "maven"),
    ("Podfile", "cocoapods", "cocoapods"),
    ("Podfile.lock", "cocoapods", "cocoapods"),
    ("packages.config", "nuget", "nuget"),
    ("Brewfile", "homebrew", "homebrew"),
    ("Brewfile.lock.json", "homebrew", "homebrew"),
    ("apt-packages.txt", "apt", "simple"),
    ("apk-packages.txt", "apk", "simple"),
    ("poetry.lock", "pypi", "poetry_lock"),
    ("uv.lock", "pypi", "uv_lock"),
    ("composer.lock", "packagist", "composer_lock"),
    ("Gemfile.lock", "rubygems", "gemfile_lock"),
    ("mix.lock", "hex", "mix_lock"),
    ("Package.resolved", "swift", "package_resolved"),
    ("udr.lock", "pypi", "udr_lock"),
]

# Extend with plugin-defined manifest patterns
try:
    from backend.core.plugin import list_plugin_manifests

    MANIFEST_PATTERNS.extend(list_plugin_manifests())
except ImportError:
    pass


class ManifestDetector:
    """Scans a directory for dependency manifests and parses them."""

    def __init__(self, directory: str | Path = "."):
        """Initialize."""
        self.directory = Path(directory).resolve()

    def _load_workspace_config(self) -> tuple[dict[str, str], dict[str, str], bool]:
        """Load pnpm-workspace.yaml and resolve workspace packages + catalog entries.

        Returns (workspace_version_map, catalog_map, found) where:
        - workspace_version_map: package_name -> exact_version (from workspace package.json)
        - catalog_map: catalog_name_or_default -> version_constraint (from pnpm-workspace.yaml)
        - found: True if pnpm-workspace.yaml existed and was parsed
        """
        ws_path = self.directory / "pnpm-workspace.yaml"
        if not ws_path.exists():
            return {}, {}, False

        try:
            import yaml
        except ImportError:
            return {}, {}

        try:
            raw = ws_path.read_text(encoding="utf-8")
            ws_config = yaml.safe_load(raw) or {}
        except Exception:
            return {}, {}

        workspace_version_map: dict[str, str] = {}
        catalog_map: dict[str, dict[str, str]] = {}  # named_catalogs -> {pkg_name: constraint}

        # Parse catalog entries (singular — simple pkg -> version)
        catalog_raw = ws_config.get("catalog", {}) or {}
        if isinstance(catalog_raw, dict):
            for k, v in catalog_raw.items():
                catalog_map.setdefault("_default", {})[k] = str(v)

        # Parse catalogs entries (plural — named catalogs per package)
        catalogs_raw = ws_config.get("catalogs", {}) or {}
        if isinstance(catalogs_raw, dict):
            for catalog_name, catalog_pkgs in catalogs_raw.items():
                if isinstance(catalog_pkgs, dict):
                    catalog_map.setdefault(catalog_name, {}).update(
                        {k: str(v) for k, v in catalog_pkgs.items()}
                    )

        # Parse workspace packages to find actual versions
        packages_globs = ws_config.get("packages", []) or []
        if isinstance(packages_globs, str):
            packages_globs = [packages_globs]

        for glob_pattern in packages_globs:
            matched = sorted(self.directory.glob(glob_pattern))
            for pkg_dir in matched:
                if not pkg_dir.is_dir():
                    continue
                pkg_json_path = pkg_dir / "package.json"
                if not pkg_json_path.exists():
                    continue
                try:
                    pkg_data = loads(pkg_json_path.read_text(encoding="utf-8"))
                    pkg_name = pkg_data.get("name", "")
                    pkg_version = pkg_data.get("version", "")
                    if pkg_name and pkg_version:
                        workspace_version_map[pkg_name] = pkg_version
                except Exception as exc:
                    logger.debug("Error reading workspace package %s: %s", pkg_json_path, exc)

        return workspace_version_map, catalog_map, True

    def detect(self, include_dev: bool = False) -> list[dict]:
        """Scan directory recursively for known manifests. Returns list of manifest info dicts.

        Args:
            include_dev: If True, include manifests from excluded dirs (examples, test, docs, etc.)

        """
        found = []
        seen_paths = set()
        excluded = set() if include_dev else EXCLUDED_DIRS
        for fname, raw_ecosystem, parser_key in MANIFEST_PATTERNS:
            ecosystem = self.ECOSYSTEM_ALIASES.get(raw_ecosystem, raw_ecosystem)
            for fp in self.directory.rglob(fname):
                if not fp.is_file() or str(fp) in seen_paths:
                    continue
                rel = fp.relative_to(self.directory)
                if any(part in excluded for part in rel.parts):
                    continue
                seen_paths.add(str(fp))
                found.append(
                    {
                        "path": str(fp),
                        "filename": fname,
                        "ecosystem": ecosystem,
                        "parser": parser_key,
                    }
                )
        unique_ecosystems = set(m["ecosystem"] for m in found)
        if len(unique_ecosystems) > 1:
            logger.warning(
                f"Multiple ecosystem manifests detected: {', '.join(sorted(unique_ecosystems))}. "
                "All packages will be resolved together; use --manifest to target a single file."
            )
        return found

    def _read_with_encoding_fallback(self, path: Path) -> str:
        """Read with encoding fallback."""
        raw: Any = path.read_bytes()
        if raw[:3] == b"\xef\xbb\xbf":
            raw = raw[3:]
        elif raw[:2] == b"\xff\xfe":
            return (
                raw.decode("utf-16-le", errors="replace")
                .encode("utf-8", errors="replace")
                .decode("utf-8", errors="replace")
            )
        elif raw[:2] == b"\xfe\xff":
            return (
                raw.decode("utf-16-be", errors="replace")
                .encode("utf-8", errors="replace")
                .decode("utf-8", errors="replace")
            )
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")

    def parse(self, manifest: dict) -> list[dict]:
        """Parse a single manifest file. Returns list of {name, version, ...} dicts."""
        path = Path(manifest["path"])
        content = self._read_with_encoding_fallback(path)
        parser_key = manifest["parser"]
        parser = self._get_parser(parser_key)
        try:
            return parser(content)
        except Exception:
            logger.warning("Failed to parse %s using %s", path, parser_key, exc_info=True)
            return []

    def _get_plugin_parser(self, key: str):
        """Look up a parser method from registered plugins.

        Returns a callable ``(content: str) -> list[dict]`` or ``None``.
        """
        from backend.core.plugin import get_all_plugins

        for eco, cls in get_all_plugins().items():
            for mf in cls.manifests:
                if mf.parser == key:
                    method = getattr(cls, mf.parser, None)
                    if method is not None:
                        return method
            for lf in cls.lock_files:
                if lf.parser == key:
                    method = getattr(cls, lf.parser, None)
                    if method is not None:
                        return method
        return None

    def parse_all(self, manifests: list[dict]) -> list[dict]:
        """Parse all manifests and return a unified package list with ecosystem info."""
        # Pre-load workspace config for workspace:* / catalog: resolution
        self._workspace_versions, self._catalog_versions, self._workspace_found = (
            self._load_workspace_config()
        )
        all_packages = []
        for m in manifests:
            packages = self.parse(m)
            for pkg in packages:
                rel = Path(m["path"]).relative_to(self.directory)
                pkg["_manifest"] = str(rel)
                pkg["_ecosystem"] = m["ecosystem"]
            all_packages.extend(packages)
        return all_packages

    ECOSYSTEM_ALIASES = {
        "cargo": "crates",
        "go": "gomodules",
    }

    def normalize(self, packages: list[dict]) -> list[dict]:
        """Normalize parsed packages to {name, ecosystem, constraint} format.
        Resolves workspace:* and catalog: constraints using workspace config."""
        normalized = []
        for pkg in packages:
            raw_name = pkg.get("name", "").strip()
            if not raw_name:
                continue
            raw_eco = pkg.get("_ecosystem", "pypi")
            ecosystem = self.ECOSYSTEM_ALIASES.get(raw_eco, raw_eco)
            # Only normalize names for case-insensitive ecosystems (PyPI, npm, crates)
            # All others preserve original case and separators
            if raw_eco in ("pypi", "pip", "npm", "node", "crates", "cargo", "rust"):
                name = (
                    normalize_package_name(raw_name)
                    if normalize_package_name(raw_name)
                    else raw_name
                )
            else:
                name = raw_name
            constraint = pkg.get("version", "*") or "*"

            # Resolve catalog: or catalog:<name> from pnpm-workspace.yaml catalog
            if constraint.startswith("catalog:") and getattr(self, "_workspace_found", False):
                catalog_name = constraint[len("catalog:") :].strip()
                if catalog_name and catalog_name in self._catalog_versions:
                    named = self._catalog_versions.get(catalog_name, {})
                    catalog_ver = named.get(name) if isinstance(named, dict) else None
                else:
                    default = self._catalog_versions.get("_default", {})
                    catalog_ver = (
                        default.get(catalog_name or name) if isinstance(default, dict) else None
                    )
                if catalog_ver:
                    pkg["_workspace_resolved"] = False
                    constraint = catalog_ver

            # Resolve workspace: protocols (workspace:*, workspace:^, workspace:~, etc.)
            # to exact version from workspace package.json
            if constraint.startswith("workspace:") and getattr(self, "_workspace_found", False):
                resolved_ver = self._workspace_versions.get(name)
                if resolved_ver:
                    pkg["_workspace_resolved"] = True
                    constraint = f"=={resolved_ver}"
                else:
                    pkg["_workspace_resolved"] = True
                    constraint = "==0.0.0"

            entry = {
                "name": name,
                "ecosystem": ecosystem,
                "constraint": constraint,
                "source": pkg.get("_manifest", "unknown"),
            }
            if "extras" in pkg:
                entry["extras"] = pkg["extras"]
            if "_workspace_resolved" in pkg:
                entry["_workspace_resolved"] = pkg["_workspace_resolved"]
            normalized.append(entry)
        return normalized

    # --- Private parsers ---

    def _get_parser(self, key: str):
        """Get parser."""
        parsers = {
            "requirements": self._parse_requirements,
            "pipfile": self._parse_pipfile,
            "pipfile_lock": self._parse_pipfile_lock,
            "pyproject": self._parse_pyproject,
            "package_json": self._parse_package_json,
            "package_lock": self._parse_package_lock,
            "yarn_lock": self._parse_yarn_lock,
            "cargo_toml": self._parse_cargo_toml,
            "cargo_lock": self._parse_cargo_lock,
            "go_mod": self._parse_go_mod,
            "conda_env": self._parse_conda_env,
            "gemfile": self._parse_gemfile,
            "composer_json": self._parse_composer_json,
            "pnpm_lock": self._parse_pnpm_lock,
            "pubspec": self._parse_pubspec,
            "gradle": self._parse_gradle,
            "swift": self._parse_swift,
            "hex": self._parse_hex,
            "cabal": self._parse_cabal,
            "maven": self._parse_maven,
            "cocoapods": self._parse_cocoapods,
            "nuget": self._parse_nuget,
            "homebrew": self._parse_homebrew,
            "simple": self._parse_simple,
            "poetry_lock": self._parse_poetry_lock,
            "uv_lock": self._parse_uv_lock,
            "go_sum": self._parse_go_sum,
            "composer_lock": self._parse_composer_lock,
            "gemfile_lock": self._parse_gemfile_lock,
            "mix_lock": self._parse_mix_lock,
            "package_resolved": self._parse_package_resolved,
            "udr_lock": self._parse_udr_lock,
            "parse_nix": self._parse_nix,
            "parse_nix_lock": self._parse_nix_lock,
            "parse_guix_scm": self._parse_guix_scm,
        }
        parser = parsers.get(key)
        if parser is None:
            parser = self._get_plugin_parser(key)
        if parser is None:
            raise KeyError(f"No parser found for {key!r}")
        return parser

    def _parse_requirements(self, content: str) -> list[dict]:
        """Parse requirements."""
        packages = []
        try:
            from packaging.requirements import Requirement

            has_requirement = True
        except ImportError:
            has_requirement = False

        for line in content.split("\n"):
            line = _strip_inline_comment(line.strip())
            if not line or line.startswith("#"):
                continue
            if line.startswith("-"):
                continue
            if has_requirement:
                try:
                    req = Requirement(line)
                    if req.extras:
                        packages.append(
                            {
                                "name": req.name,
                                "version": str(req.specifier) if req.specifier else "*",
                                "extras": list(req.extras),
                            }
                        )
                    else:
                        packages.append(
                            {
                                "name": req.name,
                                "version": str(req.specifier) if req.specifier else "*",
                            }
                        )
                except Exception:
                    logger.warning("Failed to parse requirement line: %s", line, exc_info=True)
                    packages.append({"name": line, "version": "*"})
            else:
                for op in ["==", ">=", "<=", ">", "<", "~=", "!="]:
                    if op in line:
                        n, v = line.split(op, 1)
                        packages.append({"name": n.strip(), "version": f"{op}{v.strip()}"})
                        break
                else:
                    packages.append({"name": line, "version": "*"})
        return packages

    def _parse_gradle(self, content: str) -> list[dict]:
        """Parse Gradle build file."""
        packages = []
        configs = (
            "implementation",
            "api",
            "compile",
            "runtimeOnly",
            "testImplementation",
            "kapt",
            "annotationProcessor",
            "compileOnly",
            "androidTestImplementation",
            "debugImplementation",
            "releaseImplementation",
        )
        config_pattern = "|".join(re.escape(c) for c in configs)
        string_pattern = rf"({config_pattern})\s+['\"]([^'\":]+):([^'\":]+):([^'\"]+)['\"]"
        for line in content.split("\n"):
            line = line.strip()
            m = re.match(string_pattern, line)
            if m:
                packages.append({"name": f"{m.group(2)}:{m.group(3)}", "version": m.group(4)})
                continue
            map_pattern = rf"({config_pattern})\s+['\"]([^'\":]+):([^'\":]+)['\"]\s*{{"
            mm = re.match(map_pattern, line)
            if mm:
                ver_match = re.search(r'version\s*[=:]\s*["\']([^"\']+)["\']', line)
                if ver_match:
                    packages.append(
                        {"name": f"{mm.group(2)}:{mm.group(3)}", "version": ver_match.group(1)}
                    )
        return packages

    def _parse_swift(self, content: str) -> list[dict]:
        """Parse Swift Package Manager file."""
        from backend.core.swift_parser import parse_package_swift

        parsed = parse_package_swift(content)
        return [
            {"name": name, "version": constraint or "*"}
            for name, constraint in parsed["dependencies"].items()
        ]

    def _parse_hex(self, content: str) -> list[dict]:
        """Parse Elixir mix.exs file."""
        packages = []
        for line in content.split("\n"):
            line = line.strip()
            m = re.match(r'\{\s*:(\w+)\s*,\s*["\']([^"\']+)["\']', line)
            if m:
                packages.append({"name": m.group(1), "version": m.group(2)})
        return packages

    def _parse_maven(self, content: str) -> list[dict]:
        """Parse Maven pom.xml."""
        packages = []
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(content)
            ns = {"m": "http://maven.apache.org/POM/4.0.0"}
            for dep in root.findall(".//m:dependencies/m:dependency", ns):
                group = dep.find("m:groupId", ns)
                artifact = dep.find("m:artifactId", ns)
                version = dep.find("m:version", ns)
                if group is not None and artifact is not None:
                    name = f"{group.text}:{artifact.text}"
                    ver = version.text if version is not None else "*"
                    packages.append({"name": name, "version": ver})
        except Exception:
            logger.warning("Failed to parse Maven pom.xml", exc_info=True)
        return packages

    def _parse_cocoapods(self, content: str) -> list[dict]:
        """Parse CocoaPods Podfile."""
        packages = []
        for line in content.split("\n"):
            line = line.strip()
            m = re.match(r"pod\s+['\"]([^'\"]+)['\"](?:\s*,\s*['\"]([^'\"]+)['\"])?", line)
            if m:
                name = m.group(1)
                version = m.group(2) if m.group(2) else "*"
                packages.append({"name": name, "version": version})
        return packages

    def _parse_nuget(self, content: str) -> list[dict]:
        """Parse NuGet packages.config."""
        packages = []
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(content)
            for pkg in root.findall(".//package"):
                name = pkg.get("id")
                version = pkg.get("version", "*")
                if name:
                    packages.append({"name": name, "version": version})
        except Exception:
            logger.warning("Failed to parse NuGet packages.config", exc_info=True)
        return packages

    def _parse_simple(self, content: str) -> list[dict]:
        """Parse simple line-based manifest (apt-packages.txt, apk-packages.txt)."""
        packages = []
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for op in ["==", ">=", "<=", ">", "<", "~=", "!="]:
                if op in line:
                    n, v = line.split(op, 1)
                    packages.append({"name": n.strip(), "version": f"{op}{v.strip()}"})
                    break
            else:
                packages.append({"name": line, "version": "*"})
        return packages

    def _parse_homebrew(self, content: str) -> list[dict]:
        """Parse Homebrew Brewfile or Brewfile.lock.json."""
        packages = []
        stripped = content.strip()
        if stripped.startswith("{"):
            try:
                data = loads(stripped)
                entries = data.get("entries", data)
                if isinstance(entries, list):
                    for e in entries:
                        if isinstance(e, dict):
                            name = e.get("name", e.get("package", ""))
                            version = e.get("version", "*")
                            if name:
                                packages.append({"name": name, "version": version})
            except Exception:
                logger.warning("Failed to parse Homebrew JSON manifest", exc_info=True)
            return packages
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            m = re.match(r'(brew|cask)\s+["\']([^"\']+)["\']', line)
            if m:
                packages.append({"name": m.group(2), "version": "*"})
        return packages

    def _parse_cabal(self, content: str) -> list[dict]:
        """Parse Cabal build file, handling multi-line build-depends."""
        packages = []
        in_build_depends = False
        accum = ""
        for raw_line in content.split("\n"):
            line = raw_line.strip()
            if line.startswith("build-depends:"):
                in_build_depends = True
                accum = line[len("build-depends:") :].strip()
            elif in_build_depends and line.startswith((",", "             ")):
                accum += " " + line
            elif in_build_depends:
                in_build_depends = False
                for part in re.split(r",\s*", accum):
                    m = re.match(r"(\S+)\s*(.*)", part)
                    if m:
                        name = m.group(1)
                        version_spec = m.group(2).strip() or "*"
                        packages.append({"name": name, "version": version_spec})
                accum = ""
                if line and not line.startswith(("--", "#", "{-#")):
                    m2 = re.match(r"(\S+)\s*(.*)", line)
                    if m2:
                        packages.append(
                            {"name": m2.group(1), "version": m2.group(2).strip() or "*"}
                        )
        if in_build_depends and accum:
            for part in re.split(r",\s*", accum):
                m = re.match(r"(\S+)\s*(.*)", part)
                if m:
                    name = m.group(1)
                    version_spec = m.group(2).strip() or "*"
                    packages.append({"name": name, "version": version_spec})
        return packages

    def _parse_pipfile(self, content: str) -> list[dict]:
        """Parse pipfile."""
        try:
            import tomllib

            data = tomllib.loads(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for section in ["packages", "dev-packages"]:
            if section not in data:
                continue
            for name, spec in data[section].items():
                info = {"name": name}
                if isinstance(spec, str):
                    info["version"] = spec
                elif isinstance(spec, dict):
                    info["version"] = spec.get("version", "*")
                packages.append(info)
        return packages

    def _parse_pipfile_lock(self, content: str) -> list[dict]:
        """Parse pipfile lock."""
        try:
            data = loads(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for section in ["default", "develop"]:
            deps = data.get(section, {})
            for name, info in deps.items():
                packages.append(
                    {
                        "name": name,
                        "version": info.get("version", "*"),
                    }
                )
        return packages

    def _parse_pyproject(self, content: str) -> list[dict]:
        """Parse pyproject.toml — handles PEP 621, Poetry, optional dependencies, and PDM."""
        try:
            import tomllib

            data = tomllib.loads(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []

        if "tool" in data and "poetry" in data["tool"]:
            poetry = data["tool"]["poetry"]
            for section in ["dependencies", "dev-dependencies"]:
                if section not in poetry:
                    continue
                for name, spec in poetry[section].items():
                    if name == "python":
                        continue
                    info = {"name": name}
                    if isinstance(spec, str):
                        info["version"] = spec
                    elif isinstance(spec, dict):
                        info["version"] = spec.get("version", "*")
                    packages.append(info)

        if "project" in data:
            for dep in data.get("project", {}).get("dependencies", []):
                try:
                    from packaging.requirements import Requirement

                    req = Requirement(dep)
                    packages.append(
                        {
                            "name": req.name,
                            "version": str(req.specifier) if req.specifier else "*",
                        }
                    )
                except Exception:
                    logger.warning("Failed to parse pyproject dependency: %s", dep, exc_info=True)
                    packages.append({"name": dep, "version": "*"})

            for group_deps in data.get("project", {}).get("optional-dependencies", {}).values():
                for dep in group_deps:
                    try:
                        from packaging.requirements import Requirement

                        req = Requirement(dep)
                        packages.append(
                            {
                                "name": req.name,
                                "version": str(req.specifier) if req.specifier else "*",
                            }
                        )
                    except Exception:
                        logger.warning("Failed to parse optional dep: %s", dep, exc_info=True)
                        packages.append({"name": dep, "version": "*"})

        if "build-system" in data and "requires" in data["build-system"]:
            for dep in data["build-system"]["requires"]:
                try:
                    from packaging.requirements import Requirement

                    req = Requirement(dep)
                    name = req.name
                    if not any(p.get("name") == name for p in packages):
                        packages.append(
                            {
                                "name": name,
                                "version": str(req.specifier) if req.specifier else "*",
                            }
                        )
                except Exception:
                    pass

        return packages

    def _parse_package_json(self, content: str) -> list[dict]:
        """Parse package json."""
        try:
            data = loads(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for section in ["dependencies", "devDependencies", "peerDependencies"]:
            deps = data.get(section, {})
            for name, version in deps.items():
                packages.append({"name": name, "version": version})
        return packages

    def _parse_package_lock(self, content: str) -> list[dict]:
        """Parse package lock."""
        try:
            data = loads(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for name, info in data.get("packages", {}).items():
            if name == "":
                continue
            packages.append(
                {
                    "name": name.split("node_modules/")[-1],
                    "version": info.get("version", "*"),
                }
            )
        return packages

    @staticmethod
    def parse_package_lock_tree(lock_path: str | Path) -> dict[str, dict] | None:
        """Parse package-lock.json and return full dependency tree.

        Returns {package_name: {version, dependencies: {dep_name: constraint}}} or None.
        """
        try:
            content = Path(lock_path).read_text(encoding="utf-8")
            data = loads(content)
        except Exception:
            return None
        tree: dict[str, dict] = {}
        for path, info in data.get("packages", {}).items():
            if path == "":
                continue
            name = path.split("node_modules/")[-1]
            deps = {}
            for dep_name, dep_ver in info.get("dependencies", {}).items():
                deps[dep_name] = dep_ver
            tree[name] = {
                "version": info.get("version", "0.0.0"),
                "dependencies": deps,
            }
        return tree if tree else None

    @staticmethod
    def parse_cargo_lock_tree(lock_path: str | Path) -> dict[str, dict] | None:
        """Parse Cargo.lock and return full dependency tree.

        Returns {package_name: {version, dependencies: {dep_name: constraint}}} or None.
        """
        try:
            import tomllib

            content = Path(lock_path).read_text(encoding="utf-8")
            data = tomllib.loads(content)
        except Exception:
            return None
        tree: dict[str, dict] = {}
        for pkg in data.get("package", []):
            name = pkg.get("name", "")
            version = pkg.get("version", "0.0.0")
            deps: dict[str, str] = {}
            for dep in pkg.get("dependencies", []):
                dep_name = dep.split(" ")[0]
                deps[dep_name] = "*"
            tree[name] = {"version": version, "dependencies": deps}
        return tree if tree else None

    @staticmethod
    def parse_composer_lock_tree(lock_path: str | Path) -> dict[str, dict] | None:
        """Parse composer.lock and return full dependency tree.

        Returns {package_name: {version, dependencies: {dep_name: constraint}}} or None.
        """
        try:
            content = Path(lock_path).read_text(encoding="utf-8")
            data = loads(content)
        except Exception:
            return None
        tree: dict[str, dict] = {}
        for section in ("packages", "packages-dev"):
            for entry in data.get(section, []):
                name = entry.get("name", "")
                version = entry.get("version", "0.0.0")
                deps: dict[str, str] = {}
                for dep_name, dep_ver in entry.get("require", {}).items():
                    deps[dep_name] = dep_ver
                tree[name] = {"version": version, "dependencies": deps}
        return tree if tree else None

    @staticmethod
    def parse_poetry_lock_tree(lock_path: str | Path) -> dict[str, dict] | None:
        """Parse poetry.lock and return full dependency tree.

        Returns {package_name: {version, dependencies: {dep_name: constraint}}} or None.
        """
        try:
            import tomllib

            content = Path(lock_path).read_text(encoding="utf-8")
            data = tomllib.loads(content)
        except Exception:
            return None
        tree: dict[str, dict] = {}
        for entry in data.get("package", []):
            name = entry.get("name", "")
            version = entry.get("version", "0.0.0")
            deps: dict[str, str] = {}
            deps_raw = entry.get("dependencies", {})
            if isinstance(deps_raw, dict):
                for dep_name, dep_spec in deps_raw.items():
                    if isinstance(dep_spec, str):
                        deps[dep_name] = dep_spec
                    elif isinstance(dep_spec, dict):
                        deps[dep_name] = dep_spec.get("version", "*")
                    else:
                        deps[dep_name] = "*"
            tree[name] = {"version": version, "dependencies": deps}
        return tree if tree else None

    @staticmethod
    def parse_gemfile_lock_tree(lock_path: str | Path) -> dict[str, dict] | None:
        """Parse Gemfile.lock and return full dependency tree.

        Returns {package_name: {version, dependencies: {dep_name: constraint}}} or None.
        """
        try:
            content = Path(lock_path).read_text(encoding="utf-8")
        except Exception:
            return None
        tree: dict[str, dict] = {}
        in_specs = False
        current_gem: str | None = None
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped == "specs:":
                in_specs = True
                continue
            if not in_specs:
                continue
            if stripped == "":
                continue
            indent = len(line) - len(line.lstrip())
            if indent == 0:
                break
            if indent == 4:
                m = re.match(r"(\S+)\s+\(([^)]+)\)", stripped)
                if m:
                    current_gem = m.group(1)
                    tree[current_gem] = {"version": m.group(2), "dependencies": {}}
            elif indent >= 6 and current_gem:
                dep_m = re.match(r"(\S+)\s*(?:\((.+)\))?", stripped)
                if dep_m:
                    dep_name = dep_m.group(1)
                    dep_ver = dep_m.group(2) or ">= 0"
                    tree[current_gem]["dependencies"][dep_name] = dep_ver
        return tree if tree else None

    @staticmethod
    def parse_pnpm_lock_tree(lock_path: str | Path) -> dict[str, dict] | None:
        """Parse pnpm-lock.yaml and return full dependency tree.

        Returns {package_name: {version, dependencies: {dep_name: constraint}}} or None.
        """
        try:
            import yaml

            content = Path(lock_path).read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except Exception:
            return None
        tree: dict[str, dict] = {}
        for key, info in data.get("packages", {}).items():
            if key == ".":
                continue
            entry = key[1:] if key.startswith("/") else key
            at_pos = entry.rfind("@")
            if at_pos <= 0:
                continue
            name = entry[:at_pos]
            version = entry[at_pos + 1 :]
            deps: dict[str, str] = {}
            for dep_name, dep_ver in info.get("dependencies", {}).items():
                deps[dep_name] = dep_ver
            tree[name] = {"version": version, "dependencies": deps}
        return tree if tree else None

    def _parse_yarn_lock(self, content: str) -> list[dict]:
        """Parse yarn lock — handles @scoped packages correctly."""
        packages = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith('"') and line.endswith('":'):
                name_version = line.strip('":').strip('"')
                if "," in name_version:
                    continue
                parts = name_version.rsplit("@", 1)
                if len(parts) == 2 and parts[0]:
                    packages.append(
                        {
                            "name": parts[0],
                            "version": parts[1],
                        }
                    )
        return packages

    def _parse_cargo_toml(self, content: str) -> list[dict]:
        """Parse cargo toml."""
        try:
            import tomllib

            data = tomllib.loads(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for section in ["dependencies", "dev-dependencies", "build-dependencies"]:
            deps = data.get(section, {})
            for name, spec in deps.items():
                info = {"name": name}
                if isinstance(spec, str):
                    info["version"] = spec
                elif isinstance(spec, dict):
                    info["version"] = spec.get("version", "*")
                packages.append(info)
        return packages

    def _parse_cargo_lock(self, content: str) -> list[dict]:
        """Parse cargo lock."""
        try:
            import tomllib

            data = tomllib.loads(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for pkg in data.get("package", []):
            packages.append(
                {
                    "name": pkg.get("name"),
                    "version": pkg.get("version", "*"),
                }
            )
        return packages

    def _parse_go_mod(self, content: str) -> list[dict]:
        """Parse go.mod — handles require(), single-line require, skips replace/exclude/go."""
        packages = []
        require_block = False
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            if line.startswith("require ("):
                require_block = True
                continue
            if line == ")" and require_block:
                require_block = False
                continue
            if require_block or line.startswith("require "):
                match = re.match(r"(?:require\s+)?([^\s]+)\s+([^\s]+)(?:\s+//\s+indirect)?", line)
                if match:
                    dep_name = match.group(1)
                    dep_version = match.group(2)
                    if (
                        dep_version.startswith("v")
                        and len(dep_version) > 1
                        and dep_version[1].isdigit()
                    ):
                        dep_version = dep_version[1:]
                    packages.append({"name": dep_name, "version": dep_version})
        return packages

    def _parse_conda_env(self, content: str) -> list[dict]:
        """Parse conda env."""
        try:
            import yaml  # type: ignore[import-untyped]

            data = yaml.safe_load(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for dep in data.get("dependencies", []):
            if isinstance(dep, str):
                for op in ["==", ">=", "<=", ">", "<", "="]:
                    if op in dep:
                        n, v = dep.split(op, 1)
                        packages.append({"name": n.strip(), "version": f"{op}{v.strip()}"})
                        break
                else:
                    packages.append({"name": dep, "version": "*"})
            elif isinstance(dep, dict):
                for key in ("pip",):
                    for pip_dep in dep.get(key, []):
                        for op in ["==", ">=", "<=", ">", "<"]:
                            if op in pip_dep:
                                n, v = pip_dep.split(op, 1)
                                packages.append({"name": n.strip(), "version": f"{op}{v.strip()}"})
                                break
                        else:
                            packages.append({"name": pip_dep, "version": "*"})
        return packages

    def _parse_gemfile(self, content: str) -> list[dict]:
        """Parse gemfile."""
        packages = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("gem "):
                parts = re.findall(r'["\']([^"\']+)["\']', line)
                if parts:
                    info = {"name": parts[0]}
                    if len(parts) > 1:
                        info["version"] = parts[1]
                    packages.append(info)
        return packages

    def _parse_pnpm_lock(self, content: str) -> list[dict]:
        """Parse pnpm lock."""
        try:
            import yaml

            data = yaml.safe_load(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for name, info in data.get("packages", {}).items():
            if name == ".":
                continue
            entry = name[1:] if name.startswith("/") else name
            at_pos = entry.rfind("@")
            if at_pos > 0:
                pkg_name = entry[:at_pos]
                pkg_ver = entry[at_pos + 1 :]
            else:
                pkg_name = entry
                pkg_ver = info.get("version", "*")
            packages.append({"name": pkg_name, "version": pkg_ver})
        return packages

    def _parse_pubspec(self, content: str) -> list[dict]:
        """Parse pubspec."""
        try:
            import yaml

            data = yaml.safe_load(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for section in ["dependencies", "dev_dependencies"]:
            deps = data.get(section, {})
            for name, spec in deps.items():
                if name == "flutter" or name == "sdk":
                    continue
                info = {"name": name}
                if isinstance(spec, str):
                    info["version"] = spec
                elif isinstance(spec, dict):
                    info["version"] = spec.get("version", "*")
                packages.append(info)
        return packages

    def _parse_composer_json(self, content: str) -> list[dict]:
        """Parse composer json."""
        try:
            data = loads(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for section in ["require", "require-dev"]:
            deps = data.get(section, {})
            for name, version in deps.items():
                if name == "php":
                    continue
                packages.append({"name": name, "version": version})
        return packages

    def _parse_poetry_lock(self, content: str) -> list[dict]:
        """Parse poetry.lock (TOML format)."""
        try:
            import tomllib

            data = tomllib.loads(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for entry in data.get("package", []):
            name = entry.get("name")
            version = entry.get("version", "*")
            if name:
                packages.append({"name": name, "version": version})
        return packages

    def _parse_uv_lock(self, content: str) -> list[dict]:
        """Parse uv.lock (TOML format)."""
        try:
            import tomllib

            data = tomllib.loads(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for entry in data.get("package", []):
            name = entry.get("name")
            source = entry.get("source", {})
            version = (
                source.get("version") if isinstance(source, dict) else entry.get("version", "*")
            )
            if name:
                packages.append({"name": name, "version": version or "*"})
        return packages

    def _parse_go_sum(self, content: str) -> list[dict]:
        """Parse go.sum."""
        packages = []
        seen = set()
        for line in content.split("\n"):
            line = line.strip()
            parts = line.split()
            if len(parts) >= 2 and "/" in parts[0]:
                name = parts[0]
                ver = parts[1] if parts[1] else "*"
                if ver.startswith("v") and len(ver) > 1 and ver[1].isdigit():
                    ver = ver[1:]
                if name.startswith("go.mod"):
                    continue
                if name not in seen:
                    seen.add(name)
                    packages.append({"name": name, "version": ver})
        return packages

    def _parse_composer_lock(self, content: str) -> list[dict]:
        """Parse composer.lock (JSON format)."""
        try:
            data = loads(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for section in ["packages", "packages-dev"]:
            for entry in data.get(section, []):
                name = entry.get("name")
                version = entry.get("version", "*")
                if name:
                    packages.append({"name": name, "version": version})
        return packages

    def _parse_gemfile_lock(self, content: str) -> list[dict]:
        """Parse Gemfile.lock."""
        packages = []
        in_specs = False
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped == "specs:":
                in_specs = True
                continue
            if in_specs:
                if stripped == "":
                    continue
                indent = len(line) - len(line.lstrip())
                if indent < 4:
                    break
                if indent >= 4 and "(" in stripped:
                    m = re.match(r"(\S+)\s+\(([^)]+)\)", stripped)
                    if m:
                        packages.append({"name": m.group(1), "version": m.group(2)})
        return packages

    def _parse_mix_lock(self, content: str) -> list[dict]:
        """Parse mix.lock."""
        packages = []
        for line in content.split("\n"):
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
                    packages.append({"name": name, "version": ver_m.group(1)})
        return packages

    def _parse_package_resolved(self, content: str) -> list[dict]:
        """Parse Package.resolved (Swift)."""
        try:
            data = loads(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        pins = data.get("pins", data.get("object", {}).get("pins", []))
        for entry in pins:
            name = entry.get("identity", entry.get("package", ""))
            version = entry.get("version", entry.get("state", {}).get("version", "*"))
            if name:
                packages.append({"name": name, "version": version})
        return packages

    def _parse_udr_lock(self, content: str) -> list[dict]:
        """Parse udr.lock — UDR's own lock file format."""
        try:
            data = loads(content)
        except Exception:
            logger.warning("Manifest parser error", exc_info=True)
            return []
        packages = []
        for entry in data.get("packages", []):
            name = entry.get("name")
            version = entry.get("version", "*")
            if name:
                packages.append({"name": name, "version": version})
        return packages

    def _parse_nix(self, content: str) -> list[dict]:
        """Parse a Nix expression for buildInputs / propagatedBuildInputs."""
        deps: list[dict] = []
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
                            idx = remainder.index("]")
                            block_parts.append(remainder[:idx])
                            self._extract_nix_pkgs(" ".join(block_parts), deps)
                            block_parts = []
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
                    self._extract_nix_pkgs(" ".join(block_parts), deps)
                    block_parts = []
                    continue
                block_parts.append(stripped)
        if block_parts:
            self._extract_nix_pkgs(" ".join(block_parts), deps)
        return deps

    @staticmethod
    def _extract_nix_pkgs(text: str, deps: list[dict]) -> None:
        """Extract package references from Nix expression text."""
        for token in re.findall(r"[a-zA-Z_][\w.]*(?:\.[a-zA-Z_][\w.]+)*", text):
            if not token or token in ("pkgs", "inputs", "self"):
                continue
            if (
                "python3Packages." in token
                or "python310Packages." in token
                or "python311Packages." in token
                or "python312Packages." in token
            ):
                for prefix in (
                    "python3Packages.",
                    "python310Packages.",
                    "python311Packages.",
                    "python312Packages.",
                ):
                    if token.startswith(prefix):
                        pkg_name = token[len(prefix) :]
                        if pkg_name and pkg_name not in ("pkgs", "inputs", "self"):
                            deps.append({"name": pkg_name, "version": "*", "_ecosystem": "pypi"})
                        break
            elif token.startswith("pkgs."):
                pkg_name = token[len("pkgs.") :]
                pkg_name = pkg_name.split(".", 1)[0] if "." in pkg_name else pkg_name
                if pkg_name and pkg_name not in ("pkgs", "inputs", "self"):
                    deps.append({"name": pkg_name, "version": "*", "_ecosystem": "nix"})
            elif token not in ("pkgs", "inputs", "self", "lib"):
                deps.append({"name": token, "version": "*", "_ecosystem": "nix"})

    def _parse_nix_lock(self, content: str) -> list[dict]:
        """Parse flake.lock."""
        try:
            data = loads(content)
        except Exception:
            logger.warning("flake.lock parse error", exc_info=True)
            return []
        nodes = data.get("nodes", {})
        root = nodes.get("root", {})
        root_inputs = root.get("inputs", {})
        packages = []
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
            display = original_ref.get("id") or original_ref.get("path") or input_name
            version = locked.get("rev", locked.get("version", "latest"))
            if isinstance(version, str) and len(version) > 12:
                version = version[:12]
            packages.append({"name": display, "version": version, "_ecosystem": "nix"})
        # Include non-root referenced nodes
        for node_id, node in nodes.items():
            if node_id in ("root",) or node_id in seen_nodes:
                continue
            locked = node.get("locked", {})
            if locked.get("rev") or locked.get("version"):
                original_ref = node.get("original", {})
                display = original_ref.get("id") or original_ref.get("path") or node_id
                if not any(p["name"] == display for p in packages):
                    version = locked.get("rev", locked.get("version", "latest"))
                    if isinstance(version, str) and len(version) > 12:
                        version = version[:12]
                    packages.append({"name": display, "version": version, "_ecosystem": "nix"})
        return packages

    def _parse_guix_scm(self, content: str) -> list[dict]:
        """Parse a Guix manifest for package references."""
        deps: list[dict] = []
        seen: set[str] = set()
        for m in re.finditer(
            r'"([a-zA-Z][a-zA-Z0-9@+\-_.]*(?:/[a-zA-Z][a-zA-Z0-9+\-_.]*)*)"', content
        ):
            name = m.group(1)
            if not name or name in seen:
                continue
            if name.startswith(("/", ".", "http")):
                continue
            if re.match(r"^\d+[\d.]*\d$", name):
                continue
            seen.add(name)
            deps.append({"name": name, "version": "*", "_ecosystem": "guix"})
        return deps
