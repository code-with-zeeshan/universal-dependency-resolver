"""Manifest file discovery and parsing for `udr lock`.

Auto-detects known dependency manifests in a directory,
parses them into a uniform package list, and maps each
package to its ecosystem for resolution.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
from .core.utils import normalize_package_name

logger = logging.getLogger(__name__)


# Map filename patterns → (ecosystem, parser_func)
MANIFEST_PATTERNS: List[Tuple[str, str, str]] = [
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
    ("go.sum", "go", "go_sum"),
    ("composer.lock", "packagist", "composer_lock"),
    ("Gemfile.lock", "rubygems", "gemfile_lock"),
    ("mix.lock", "hex", "mix_lock"),
    ("Package.resolved", "swift", "package_resolved"),
    ("udr.lock", "pypi", "udr_lock"),
]


class ManifestDetector:
    """Scans a directory for dependency manifests and parses them."""

    def __init__(self, directory: str | Path = "."):
        """Initialize."""
        self.directory = Path(directory).resolve()

    def detect(self) -> List[Dict]:
        """Scan directory recursively for known manifests. Returns list of manifest info dicts."""
        found = []
        seen_paths = set()
        for fname, raw_ecosystem, parser_key in MANIFEST_PATTERNS:
            ecosystem = self.ECOSYSTEM_ALIASES.get(raw_ecosystem, raw_ecosystem)
            for fp in self.directory.rglob(fname):
                if fp.is_file() and str(fp) not in seen_paths:
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

    def parse(self, manifest: Dict) -> List[Dict]:
        """Parse a single manifest file. Returns list of {name, version, ...} dicts."""
        path = Path(manifest["path"])
        content = self._read_with_encoding_fallback(path)
        parser_key = manifest["parser"]
        parser = self._get_parser(parser_key)
        try:
            return parser(content)
        except Exception:
            return []

    def parse_all(self, manifests: List[Dict]) -> List[Dict]:
        """Parse all manifests and return a unified package list with ecosystem info."""
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

    def normalize(self, packages: List[Dict]) -> List[Dict]:
        """Normalize parsed packages to {name, ecosystem, constraint} format."""
        normalized = []
        for pkg in packages:
            raw_name = pkg.get("name", "").strip()
            if not raw_name:
                continue
            name = (
                normalize_package_name(raw_name)
                if normalize_package_name(raw_name)
                else raw_name
            )
            raw_eco = pkg.get("_ecosystem", "pypi")
            ecosystem = self.ECOSYSTEM_ALIASES.get(raw_eco, raw_eco)
            constraint = pkg.get("version", "*") or "*"
            normalized.append(
                {
                    "name": name,
                    "ecosystem": ecosystem,
                    "constraint": constraint,
                    "source": pkg.get("_manifest", "unknown"),
                }
            )
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
        }
        return parsers[key]

    def _parse_requirements(self, content: str) -> List[Dict]:
        """Parse requirements."""
        packages = []
        try:
            from packaging.requirements import Requirement

            has_requirement = True
        except ImportError:
            has_requirement = False

        for line in content.split("\n"):
            line = line.strip()
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
                    packages.append({"name": line, "version": "*"})
            else:
                for op in ["==", ">=", "<=", ">", "<", "~=", "!="]:
                    if op in line:
                        n, v = line.split(op, 1)
                        packages.append(
                            {"name": n.strip(), "version": f"{op}{v.strip()}"}
                        )
                        break
                else:
                    packages.append({"name": line, "version": "*"})
        return packages

    def _parse_gradle(self, content: str) -> List[Dict]:
        """Parse Gradle build file."""
        packages = []
        for line in content.split("\n"):
            line = line.strip()
            # Match: implementation 'group:name:version' or "group:name:version"
            m = re.match(r"(implementation|api|compile|runtimeOnly)\s+['\"]([^'\"]+)['\"]", line)
            if m:
                parts = m.group(2).split(":")
                if len(parts) >= 3:
                    packages.append({"name": f"{parts[0]}:{parts[1]}", "version": parts[2]})
        return packages

    def _parse_swift(self, content: str) -> List[Dict]:
        """Parse Swift Package Manager file."""
        packages = []
        for line in content.split("\n"):
            line = line.strip()
            m = re.search(r'\.package\(url:\s*["\']([^"\']+)["\']', line)
            if m:
                url = m.group(1)
                name = url.rstrip("/").split("/")[-1].removesuffix(".git")
                packages.append({"name": name, "version": "*"})
        return packages

    def _parse_hex(self, content: str) -> List[Dict]:
        """Parse Elixir mix.exs file."""
        packages = []
        for line in content.split("\n"):
            line = line.strip()
            m = re.match(r'\{\s*:(\w+)\s*,\s*["\']([^"\']+)["\']', line)
            if m:
                packages.append({"name": m.group(1), "version": m.group(2)})
        return packages

    def _parse_maven(self, content: str) -> List[Dict]:
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
            pass
        return packages

    def _parse_cocoapods(self, content: str) -> List[Dict]:
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

    def _parse_nuget(self, content: str) -> List[Dict]:
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
            pass
        return packages

    def _parse_simple(self, content: str) -> List[Dict]:
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

    def _parse_homebrew(self, content: str) -> List[Dict]:
        """Parse Homebrew Brewfile or Brewfile.lock.json."""
        packages = []
        stripped = content.strip()
        if stripped.startswith("{"):
            try:
                data = json.loads(stripped)
                entries = data.get("entries", data)
                if isinstance(entries, list):
                    for e in entries:
                        if isinstance(e, dict):
                            name = e.get("name", e.get("package", ""))
                            version = e.get("version", "*")
                            if name:
                                packages.append({"name": name, "version": version})
            except Exception:
                pass
            return packages
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            m = re.match(r'(brew|cask)\s+["\']([^"\']+)["\']', line)
            if m:
                packages.append({"name": m.group(2), "version": "*"})
        return packages

    def _parse_cabal(self, content: str) -> List[Dict]:
        """Parse Cabal build file."""
        packages = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("build-depends:"):
                rest = line[len("build-depends:"):].strip()
                for part in re.split(r",\s*", rest):
                    m = re.match(r"(\S+)\s*(.*)", part)
                    if m:
                        name = m.group(1)
                        version_spec = m.group(2).strip() or "*"
                        packages.append({"name": name, "version": version_spec})
        return packages
        for line in content.split("\n"):
            line = line.strip()
            if (
                not line
                or line.startswith("#")
                or line.startswith(("-r ", "-e ", "-i ", "--"))
            ):
                continue
            try:
                req = Requirement(line)
                packages.append(
                    {
                        "name": req.name,
                        "version": str(req.specifier) if req.specifier else "*",
                    }
                )
            except Exception:
                packages.append({"name": line, "version": "*"})
        return packages

    def _parse_pipfile(self, content: str) -> List[Dict]:
        """Parse pipfile."""
        try:
            import tomllib

            data = tomllib.loads(content)
        except Exception:
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

    def _parse_pipfile_lock(self, content: str) -> List[Dict]:
        """Parse pipfile lock."""
        try:
            import json

            data = json.loads(content)
        except Exception:
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

    def _parse_pyproject(self, content: str) -> List[Dict]:
        """Parse pyproject."""
        try:
            import tomllib

            data = tomllib.loads(content)
        except Exception:
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
        elif "project" in data:
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
                    packages.append({"name": dep, "version": "*"})
        return packages

    def _parse_package_json(self, content: str) -> List[Dict]:
        """Parse package json."""
        try:
            data = json.loads(content)
        except Exception:
            return []
        packages = []
        for section in ["dependencies", "devDependencies", "peerDependencies"]:
            deps = data.get(section, {})
            for name, version in deps.items():
                packages.append({"name": name, "version": version})
        return packages

    def _parse_package_lock(self, content: str) -> List[Dict]:
        """Parse package lock."""
        try:
            data = json.loads(content)
        except Exception:
            return []
        packages = []
        for name, info in data.get("packages", {}).items():
            if name == "":
                continue
            packages.append(
                {
                    "name": name.lstrip("node_modules/"),
                    "version": info.get("version", "*"),
                }
            )
        return packages

    def _parse_yarn_lock(self, content: str) -> List[Dict]:
        """Parse yarn lock."""
        packages = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith('"') and line.endswith('":'):
                name_version = line.strip('":').strip('"')
                if "," in name_version:
                    continue
                if name_version.startswith("@"):
                    continue
                parts = name_version.split("@")
                if len(parts) >= 2 and parts[0]:
                    packages.append(
                        {
                            "name": parts[0],
                            "version": parts[-1],
                        }
                    )
        return packages

    def _parse_cargo_toml(self, content: str) -> List[Dict]:
        """Parse cargo toml."""
        try:
            import tomllib

            data = tomllib.loads(content)
        except Exception:
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

    def _parse_cargo_lock(self, content: str) -> List[Dict]:
        """Parse cargo lock."""
        try:
            import tomllib

            data = tomllib.loads(content)
        except Exception:
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

    def _parse_go_mod(self, content: str) -> List[Dict]:
        """Parse go mod."""
        packages = []
        for line in content.split("\n"):
            line = line.strip()
            parts = line.split()
            if len(parts) >= 2 and "." in parts[0]:
                packages.append(
                    {
                        "name": parts[0],
                        "version": parts[1] if len(parts) > 1 else "*",
                    }
                )
        return packages

    def _parse_conda_env(self, content: str) -> List[Dict]:
        """Parse conda env."""
        try:
            import yaml  # type: ignore[import-untyped]

            data = yaml.safe_load(content)
        except Exception:
            return []
        packages = []
        for dep in data.get("dependencies", []):
            if isinstance(dep, str):
                for op in ["==", ">=", "<=", ">", "<", "="]:
                    if op in dep:
                        n, v = dep.split(op, 1)
                        packages.append(
                            {"name": n.strip(), "version": f"{op}{v.strip()}"}
                        )
                        break
                else:
                    packages.append({"name": dep, "version": "*"})
            elif isinstance(dep, dict):
                for key in ("pip",):
                    for pip_dep in dep.get(key, []):
                        for op in ["==", ">=", "<=", ">", "<"]:
                            if op in pip_dep:
                                n, v = pip_dep.split(op, 1)
                                packages.append(
                                    {"name": n.strip(), "version": f"{op}{v.strip()}"}
                                )
                                break
                        else:
                            packages.append({"name": pip_dep, "version": "*"})
        return packages

    def _parse_gemfile(self, content: str) -> List[Dict]:
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

    def _parse_pnpm_lock(self, content: str) -> List[Dict]:
        """Parse pnpm lock."""
        try:
            import yaml

            data = yaml.safe_load(content)
        except Exception:
            return []
        packages = []
        for name, info in data.get("packages", {}).items():
            if name == ".":
                continue
            short_name = (
                name.lstrip("@npm/").split("/")[-1] if name.startswith("/") else name
            )
            packages.append(
                {
                    "name": short_name,
                    "version": info.get("version", "*"),
                }
            )
        return packages

    def _parse_pubspec(self, content: str) -> List[Dict]:
        """Parse pubspec."""
        try:
            import yaml

            data = yaml.safe_load(content)
        except Exception:
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

    def _parse_composer_json(self, content: str) -> List[Dict]:
        """Parse composer json."""
        try:
            data = json.loads(content)
        except Exception:
            return []
        packages = []
        for section in ["require", "require-dev"]:
            deps = data.get(section, {})
            for name, version in deps.items():
                if name == "php":
                    continue
                packages.append({"name": name, "version": version})
        return packages

    def _parse_poetry_lock(self, content: str) -> List[Dict]:
        """Parse poetry.lock (TOML format)."""
        try:
            import tomllib
            data = tomllib.loads(content)
        except Exception:
            return []
        packages = []
        for entry in data.get("package", []):
            name = entry.get("name")
            version = entry.get("version", "*")
            if name:
                packages.append({"name": name, "version": version})
        return packages

    def _parse_uv_lock(self, content: str) -> List[Dict]:
        """Parse uv.lock (TOML format)."""
        try:
            import tomllib
            data = tomllib.loads(content)
        except Exception:
            return []
        packages = []
        for entry in data.get("package", []):
            name = entry.get("name")
            source = entry.get("source", {})
            version = source.get("version") if isinstance(source, dict) else entry.get("version", "*")
            if name:
                packages.append({"name": name, "version": version or "*"})
        return packages

    def _parse_go_sum(self, content: str) -> List[Dict]:
        """Parse go.sum."""
        packages = []
        seen = set()
        for line in content.split("\n"):
            line = line.strip()
            parts = line.split()
            if len(parts) >= 2 and "/" in parts[0]:
                name = parts[0]
                ver = parts[1] if parts[1] else "*"
                if name.startswith("go.mod"):
                    continue
                if name not in seen:
                    seen.add(name)
                    packages.append({"name": name, "version": ver})
        return packages

    def _parse_composer_lock(self, content: str) -> List[Dict]:
        """Parse composer.lock (JSON format)."""
        try:
            data = json.loads(content)
        except Exception:
            return []
        packages = []
        for section in ["packages", "packages-dev"]:
            for entry in data.get(section, []):
                name = entry.get("name")
                version = entry.get("version", "*")
                if name:
                    packages.append({"name": name, "version": version})
        return packages

    def _parse_gemfile_lock(self, content: str) -> List[Dict]:
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

    def _parse_mix_lock(self, content: str) -> List[Dict]:
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
            inner = line[m.end():].strip().lstrip("{").strip()
            parts = inner.split(",")
            if len(parts) >= 3:
                ver_m = re.search(r'["\']([^"\']+)["\']', parts[2])
                if ver_m:
                    packages.append({"name": name, "version": ver_m.group(1)})
        return packages

    def _parse_package_resolved(self, content: str) -> List[Dict]:
        """Parse Package.resolved (Swift)."""
        try:
            data = json.loads(content)
        except Exception:
            return []
        packages = []
        pins = data.get("pins", data.get("object", {}).get("pins", []))
        for entry in pins:
            name = entry.get("identity", entry.get("package", ""))
            version = entry.get("version", entry.get("state", {}).get("version", "*"))
            if name:
                packages.append({"name": name, "version": version})
        return packages

    def _parse_udr_lock(self, content: str) -> List[Dict]:
        """Parse udr.lock — UDR's own lock file format."""
        try:
            data = json.loads(content)
        except Exception:
            return []
        packages = []
        for entry in data.get("packages", []):
            name = entry.get("name")
            version = entry.get("version", "*")
            if name:
                packages.append({"name": name, "version": version})
        return packages
