"""
Manifest file discovery and parsing for `udr lock`.

Auto-detects known dependency manifests in a directory,
parses them into a uniform package list, and maps each
package to its ecosystem for resolution.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


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
]


class ManifestDetector:
    """Scans a directory for dependency manifests and parses them."""

    def __init__(self, directory: str | Path = "."):
        self.directory = Path(directory).resolve()

    def detect(self) -> List[Dict]:
        """Scan directory for known manifests. Returns list of manifest info dicts."""
        found = []
        seen = set()
        for fname, ecosystem, parser_key in MANIFEST_PATTERNS:
            fp = self.directory / fname
            if fp.is_file() and fname not in seen:
                seen.add(fname)
                found.append({
                    "path": str(fp),
                    "filename": fname,
                    "ecosystem": ecosystem,
                    "parser": parser_key,
                })
        return found

    def parse(self, manifest: Dict) -> List[Dict]:
        """Parse a single manifest file. Returns list of {name, version, ...} dicts."""
        path = Path(manifest["path"])
        content = path.read_text(encoding="utf-8", errors="replace")
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
                pkg["_manifest"] = m["filename"]
                pkg["_ecosystem"] = m["ecosystem"]
            all_packages.extend(packages)
        return all_packages

    def normalize(self, packages: List[Dict]) -> List[Dict]:
        """Normalize parsed packages to {name, ecosystem, constraint} format."""
        normalized = []
        for pkg in packages:
            name = pkg.get("name", "").strip()
            if not name:
                continue
            constraint = pkg.get("version", "*") or "*"
            normalized.append({
                "name": name,
                "ecosystem": pkg.get("_ecosystem", "pypi"),
                "constraint": constraint,
                "source": pkg.get("_manifest", "unknown"),
            })
        return normalized

    # --- Private parsers ---

    def _get_parser(self, key: str):
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
        }
        return parsers[key]

    def _parse_requirements(self, content: str) -> List[Dict]:
        packages = []
        try:
            from packaging.requirements import Requirement
        except ImportError:
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
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(("-r ", "-e ", "-i ", "--")):
                continue
            try:
                req = Requirement(line)
                packages.append({
                    "name": req.name,
                    "version": str(req.specifier) if req.specifier else "*",
                })
            except Exception:
                packages.append({"name": line, "version": "*"})
        return packages

    def _parse_pipfile(self, content: str) -> List[Dict]:
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
        try:
            import json
            data = json.loads(content)
        except Exception:
            return []
        packages = []
        for section in ["default", "develop"]:
            deps = data.get(section, {})
            for name, info in deps.items():
                packages.append({
                    "name": name,
                    "version": info.get("version", "*"),
                })
        return packages

    def _parse_pyproject(self, content: str) -> List[Dict]:
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
                    packages.append({
                        "name": req.name,
                        "version": str(req.specifier) if req.specifier else "*",
                    })
                except Exception:
                    packages.append({"name": dep, "version": "*"})
        return packages

    def _parse_package_json(self, content: str) -> List[Dict]:
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
        try:
            data = json.loads(content)
        except Exception:
            return []
        packages = []
        for name, info in data.get("packages", {}).items():
            if name == "":
                continue
            packages.append({
                "name": name.lstrip("node_modules/"),
                "version": info.get("version", "*"),
            })
        return packages

    def _parse_yarn_lock(self, content: str) -> List[Dict]:
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
                    packages.append({
                        "name": parts[0],
                        "version": parts[-1],
                    })
        return packages

    def _parse_cargo_toml(self, content: str) -> List[Dict]:
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
        try:
            import tomllib
            data = tomllib.loads(content)
        except Exception:
            return []
        packages = []
        for pkg in data.get("package", []):
            packages.append({
                "name": pkg.get("name"),
                "version": pkg.get("version", "*"),
            })
        return packages

    def _parse_go_mod(self, content: str) -> List[Dict]:
        packages = []
        for line in content.split("\n"):
            line = line.strip()
            parts = line.split()
            if len(parts) >= 2 and "." in parts[0]:
                packages.append({
                    "name": parts[0],
                    "version": parts[1] if len(parts) > 1 else "*",
                })
        return packages

    def _parse_conda_env(self, content: str) -> List[Dict]:
        try:
            import yaml
            data = yaml.safe_load(content)
        except Exception:
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

    def _parse_gemfile(self, content: str) -> List[Dict]:
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
        try:
            import yaml
            data = yaml.safe_load(content)
        except Exception:
            return []
        packages = []
        for name, info in data.get("packages", {}).items():
            if name == ".":
                continue
            short_name = name.lstrip("@npm/").split("/")[-1] if name.startswith("/") else name
            packages.append({
                "name": short_name,
                "version": info.get("version", "*"),
            })
        return packages

    def _parse_pubspec(self, content: str) -> List[Dict]:
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
