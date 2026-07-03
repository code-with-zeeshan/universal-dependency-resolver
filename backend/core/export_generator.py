import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from enum import Enum
from dataclasses import dataclass
import logging
from jinja2 import Environment, PackageLoader

logger = logging.getLogger(__name__)


class PackageEcosystem(Enum):
    """Supported package ecosystems."""

    PYPI = "pypi"
    NPM = "npm"
    CONDA = "conda"
    MAVEN = "maven"
    CARGO = "crates"
    GOMODULES = "gomodules"
    APT = "apt"
    APK = "apk"
    COCOAPODS = "cocoapods"
    RUBYGEMS = "rubygems"
    PACKAGIST = "packagist"
    NUGET = "nuget"
    HOMEBREW = "homebrew"
    SYSTEM = "system"
    UNKNOWN = "unknown"


@dataclass
class PackageInfo:
    """Structured package information."""

    name: str
    version: str
    ecosystem: PackageEcosystem
    extras: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, name: str, info: Dict[str, Any]) -> "PackageInfo":
        """Create PackageInfo from dictionary."""
        ecosystem_str = info.get("ecosystem", "unknown")
        try:
            ecosystem = PackageEcosystem(ecosystem_str)
        except ValueError:
            ecosystem = PackageEcosystem.UNKNOWN

        return cls(
            name=name,
            version=info.get("version", ""),
            ecosystem=ecosystem,
            extras=info.get("extras", {}) or {},
        )


class ExportGenerator:
    """Main export generator using Jinja2 templates."""

    def __init__(self):
        """Initialize."""
        self.env = Environment(
            loader=PackageLoader("backend.core", "templates"),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._add_template_filters()

        self.template_map: Dict[str, str] = {
            "requirements.txt": "requirements.txt.j2",
            "package.json": "package.json.j2",
            "Dockerfile": "Dockerfile.j2",
            "Gemfile": "Gemfile.j2",
            "composer.json": "composer.json.j2",
            "go.mod": "go.mod.j2",
            "environment.yml": "environment.yml.j2",
            "pyproject.toml": "pyproject.toml.j2",
            "docker-compose.yml": "docker-compose.yml.j2",
            "install.sh": "install.sh.j2",
            "install.bat": "install.bat.j2",
            "CMakeLists.txt": "CMakeLists.txt.j2",
            "Cargo.toml": "Cargo.toml.j2",
            "build.gradle": "build.gradle.j2",
            "pom.xml": "pom.xml.j2",
        }

        self.formats: Dict[str, Any] = {}

    def _add_template_filters(self):
        """Add template filters."""
        @staticmethod
        def to_package_str(pkg: dict, pin_versions: bool = True) -> str:
            """Format a package dict into a dependency string."""
            spec = (
                f"{pkg['name']}=={pkg['version']}"
                if pin_versions
                else f"{pkg['name']}>={pkg['version']}"
            )
            extras = pkg.get("extras", {}) or {}
            if extras.get("extras"):
                spec = f"{pkg['name']}[{','.join(extras['extras'])}]=={pkg['version']}"
            if extras.get("markers"):
                spec += f" ; {extras['markers']}"
            return spec

        self.env.filters["to_package_str"] = to_package_str

        def tojson_no_sort(obj, indent=None):
            """Serialize to JSON without sorting keys."""
            return json.dumps(obj, indent=indent, sort_keys=False, ensure_ascii=True)

        self.env.filters["tojson"] = tojson_no_sort

    def register_format(self, name: str, format_handler: Any) -> None:
        """Register a new export format."""
        self.formats[name] = format_handler

    def generate(
        self,
        resolved_packages: Dict[str, Any],
        format: str,
        system_info: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate output in specified format."""
        if not resolved_packages:
            raise ValueError("No packages provided")

        options = options or {}
        system_info = system_info or {}

        if format in self.formats:
            packages = self._parse_packages(resolved_packages)
            return self.formats[format].generate(packages, system_info, options)

        template_name = self.template_map.get(format)
        if not template_name:
            raise ValueError(f"Unsupported format: {format}")

        template = self.env.get_template(template_name)
        context = self._build_context(resolved_packages, system_info, options, format)

        return template.render(**context)

    def generate_multiple(
        self,
        resolved_packages: Dict[str, Any],
        formats: List[str],
        system_info: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Generate multiple export formats."""
        results = {}
        for fmt in formats:
            try:
                results[fmt] = self.generate(
                    resolved_packages, fmt, system_info, options
                )
            except Exception as e:
                logger.error(f"Failed to generate {fmt}: {e}")
                results[fmt] = f"# Error generating {fmt}: {str(e)}"
        return results

    def save_to_file(self, content: str, filepath: Path, format: str) -> None:
        """Save generated content to file."""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        if format in ["install.sh"]:
            filepath.write_text(content)
            filepath.chmod(0o755)
        else:
            filepath.write_text(content)

    def _parse_packages(self, resolved_packages: Dict[str, Any]) -> List[PackageInfo]:
        """Parse resolved packages into structured format."""
        packages = []
        package_dict = resolved_packages.get("resolved_packages", resolved_packages)
        for name, info in package_dict.items():
            if isinstance(info, dict):
                packages.append(PackageInfo.from_dict(name, info))
            else:
                logger.warning(f"Invalid package info for {name}: {info}")
        return packages

    def _build_context(
        self,
        resolved_packages: Dict[str, Any],
        system_info: Dict[str, Any],
        options: Dict[str, Any],
        format: str,
    ) -> Dict[str, Any]:
        """Build template context from packages, system_info, and options."""
        packages = self._parse_packages(resolved_packages)

        timestamp = datetime.now().isoformat()

        ecosystems: Dict[str, List[Dict[str, Any]]] = {}
        for pkg in packages:
            eco = pkg.ecosystem.value
            if eco not in ecosystems:
                ecosystems[eco] = []
            ecosystems[eco].append(
                {
                    "name": pkg.name,
                    "version": pkg.version,
                    "ecosystem": eco,
                    "extras": pkg.extras or {},
                }
            )

        context: Dict[str, Any] = {
            "packages": [
                {
                    "name": p.name,
                    "version": p.version,
                    "ecosystem": p.ecosystem.value,
                    "extras": p.extras or {},
                }
                for p in packages
            ],
            "system_info": system_info,
            "options": options,
            "timestamp": timestamp,
            "ecosystems": ecosystems,
            "hashes": {},
        }

        if format == "requirements.txt":
            self._add_requirements_context(context, packages, options)
        elif format == "Dockerfile":
            self._add_dockerfile_context(context, packages, system_info, options)
        elif format == "package.json":
            self._add_package_json_context(context, packages, system_info, options)
        elif format == "composer.json":
            self._add_composer_json_context(context, packages, system_info, options)

        return context

    def _add_requirements_context(
        self,
        context: Dict[str, Any],
        packages: List["PackageInfo"],
        options: Dict[str, Any],
    ) -> None:
        """Pre-process packages for requirements.txt template."""
        python_pkgs = [p for p in packages if p.ecosystem == PackageEcosystem.PYPI]

        pin_versions = options.get("pin_versions", True)

        sorted_pkgs = sorted(python_pkgs, key=lambda p: (p.name.lower(), p.version))

        if options.get("deduplicate", True):
            seen = {}
            for pkg in sorted_pkgs:
                if pkg.name not in seen:
                    seen[pkg.name] = pkg
            sorted_pkgs = sorted(seen.values(), key=lambda p: p.name.lower())

        raw_pkgs = [{"name": p.name, "version": p.version} for p in sorted_pkgs]

        formatted = []
        for pkg in sorted_pkgs:
            spec = (
                f"{pkg.name}=={pkg.version}"
                if pin_versions
                else f"{pkg.name}>={pkg.version}"
            )
            extras_dict = pkg.extras or {}
            if extras_dict.get("extras"):
                spec = f"{pkg.name}[{','.join(extras_dict['extras'])}]=={pkg.version}"
            if extras_dict.get("markers"):
                spec += f" ; {extras_dict['markers']}"
            formatted.append(spec)

        categorized = None
        if options.get("group_by_category"):
            cats: Dict[str, List[str]] = {
                "Core Dependencies": [],
                "Development Tools": [],
                "Testing": [],
                "Documentation": [],
                "Other": [],
            }
            dev_p = ["dev", "debug", "lint", "format", "black", "flake8", "mypy"]
            test_p = ["test", "pytest", "unittest", "mock", "coverage"]
            doc_p = ["sphinx", "doc", "mkdocs"]
            for spec, pkg in zip(formatted, sorted_pkgs):
                nl = pkg.name.lower()
                if any(pat in nl for pat in dev_p):
                    cats["Development Tools"].append(spec)
                elif any(pat in nl for pat in test_p):
                    cats["Testing"].append(spec)
                elif any(pat in nl for pat in doc_p):
                    cats["Documentation"].append(spec)
                else:
                    cats["Core Dependencies"].append(spec)
            categorized = {k: v for k, v in cats.items() if v}

        context["python_packages"] = formatted
        context["python_packages_raw"] = raw_pkgs
        context["python_packages_categorized"] = categorized

    def _add_dockerfile_context(
        self,
        context: Dict[str, Any],
        packages: List["PackageInfo"],
        system_info: Dict[str, Any],
        options: Dict[str, Any],
    ) -> None:
        """Pre-compute Dockerfile-specific values."""
        custom_base = options.get("base_image")
        if custom_base:
            context["base_image"] = custom_base
        else:
            gpu_info = system_info.get("gpu", {})
            if gpu_info.get("available") and gpu_info.get("cuda"):
                context["base_image"] = (
                    f"nvidia/cuda:{gpu_info['cuda']}-cudnn8-runtime-ubuntu22.04"
                )
            else:
                has_python = any(p.ecosystem == PackageEcosystem.PYPI for p in packages)
                has_node = any(p.ecosystem == PackageEcosystem.NPM for p in packages)
                has_ruby = any(
                    p.ecosystem == PackageEcosystem.RUBYGEMS for p in packages
                )
                has_php = any(
                    p.ecosystem == PackageEcosystem.PACKAGIST for p in packages
                )
                has_dotnet = any(
                    p.ecosystem == PackageEcosystem.NUGET for p in packages
                )
                has_go = any(
                    p.ecosystem == PackageEcosystem.GOMODULES for p in packages
                )

                if has_python and has_node:
                    context["base_image"] = "python:3.11-slim"
                elif has_python:
                    context["base_image"] = "python:3.11-slim"
                elif has_node:
                    context["base_image"] = "node:18-alpine"
                elif has_ruby:
                    context["base_image"] = "ruby:3.2-slim"
                elif has_php:
                    context["base_image"] = "php:8.2-cli"
                elif has_dotnet:
                    context["base_image"] = "mcr.microsoft.com/dotnet/sdk:7.0"
                elif has_go:
                    context["base_image"] = "golang:1.21-alpine"
                else:
                    context["base_image"] = "ubuntu:22.04"

        runtime_deps = []
        if any("numpy" in p.name for p in packages):
            runtime_deps.append("libopenblas-base")
        if any("pillow" in p.name.lower() for p in packages):
            runtime_deps.append("libjpeg62-turbo")
        context["runtime_deps"] = runtime_deps

    def _add_package_json_context(
        self,
        context: Dict[str, Any],
        packages: List["PackageInfo"],
        system_info: Dict[str, Any],
        options: Dict[str, Any],
    ) -> None:
        """Build full package.json dict for template."""
        npm_pkgs = context["ecosystems"].get("npm", [])
        pin = options.get("pin_versions", True)
        use_caret = options.get("use_caret", True)

        def fmt_version(v):
            """Fmt version."""
            if pin:
                return v
            return f"^{v}" if use_caret else f"~{v}"

        package_json: Dict[str, Any] = {}
        package_json["name"] = options.get("project_name", "my-project")
        package_json["version"] = options.get("project_version", "1.0.0")
        package_json["description"] = options.get(
            "description", "Generated by Universal Dependency Resolver"
        )
        package_json["main"] = options.get("main", "index.js")

        scripts: Dict[str, str] = {}
        scripts["test"] = options.get(
            "test_command", 'echo "Error: no test specified" && exit 1'
        )
        if options.get("include_standard_scripts", True):
            scripts.update(
                {
                    "start": "node index.js",
                    "build": "echo 'No build step'",
                    "lint": "eslint .",
                    "format": "prettier --write .",
                }
            )
        package_json["scripts"] = scripts

        package_json["keywords"] = options.get("keywords", [])
        package_json["author"] = options.get("author", "")
        package_json["license"] = options.get("license", "MIT")

        deps: Dict[str, str] = {}
        dev_deps: Dict[str, str] = {}
        peer_deps: Dict[str, str] = {}

        for pkg in npm_pkgs:
            ver = fmt_version(pkg["version"])
            extras = pkg.get("extras", {})
            if extras.get("dev"):
                dev_deps[pkg["name"]] = ver
            elif extras.get("peer"):
                peer_deps[pkg["name"]] = ver
            else:
                deps[pkg["name"]] = ver

        package_json["dependencies"] = deps
        package_json["devDependencies"] = dev_deps
        package_json["peerDependencies"] = peer_deps

        engines: Dict[str, str] = {}
        node_info = system_info.get("runtime_versions", {}).get("node", {})
        npm_info = system_info.get("runtime_versions", {}).get("npm", {})
        if node_info.get("version"):
            engines["node"] = f">={node_info['version']}"
        if npm_info.get("version"):
            engines["npm"] = f">={npm_info['version']}"
        package_json["engines"] = engines

        if options.get("repository"):
            package_json["repository"] = options["repository"]
        if options.get("bugs"):
            package_json["bugs"] = options["bugs"]
        if options.get("homepage"):
            package_json["homepage"] = options["homepage"]
        if options.get("include_npm_config"):
            package_json["publishConfig"] = {"registry": "https://registry.npmjs.org/"}

        package_json = {
            k: v
            for k, v in package_json.items()
            if v or k in ["dependencies", "devDependencies"]
        }

        context["package_json"] = package_json

    def _add_composer_json_context(
        self,
        context: Dict[str, Any],
        packages: List["PackageInfo"],
        system_info: Dict[str, Any],
        options: Dict[str, Any],
    ) -> None:
        """Build full composer.json dict for template."""
        php_pkgs = context["ecosystems"].get("packagist", [])

        composer: Dict[str, Any] = {
            "name": f"{options.get('vendor_name', 'vendor')}/{options.get('project_name', 'project')}",
            "description": options.get(
                "description", "Generated by Universal Dependency Resolver"
            ),
            "type": options.get("type", "library"),
            "license": options.get("license", "MIT"),
            "authors": [
                {
                    "name": options.get("author_name", "Your Name"),
                    "email": options.get("author_email", "you@example.com"),
                }
            ],
            "minimum-stability": options.get("minimum_stability", "stable"),
            "require": {},
            "require-dev": {},
            "autoload": {"psr-4": {f"{options.get('namespace', 'App')}\\": "src/"}},
        }

        php_info = system_info.get("runtime_versions", {}).get("php", {})
        if php_info.get("version"):
            composer["require"]["php"] = f">={php_info['version']}"

        pin = options.get("pin_versions", True)
        for pkg in php_pkgs:
            ver = pkg["version"] if pin else f"^{pkg['version']}"
            extras = pkg.get("extras", {})
            if extras.get("dev"):
                composer["require-dev"][pkg["name"]] = ver
            else:
                composer["require"][pkg["name"]] = ver

        context["composer_json"] = composer


def create_export_generator() -> ExportGenerator:
    """Create and return an ExportGenerator instance."""
    return ExportGenerator()
