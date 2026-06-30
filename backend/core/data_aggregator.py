# data_aggregator.py
from typing import Dict, List, Optional, Any, Union
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import re
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from backend.core.cache import cache_manager
from backend.core.utils import (
    normalize_package_name,
    sanitize_ecosystem_name,
    hash_system_info,
)
import json
import hashlib
from collections import defaultdict
import importlib
import aiohttp


from backend.settings import OSV_API_URL

logger = logging.getLogger(__name__)


class Ecosystem(Enum):
    PYPI = "pypi"
    NPM = "npm"
    CONDA = "conda"
    MAVEN = "maven"
    CRATES = "crates"
    GOMODULES = "gomodules"
    APT = "apt"
    APK = "apk"
    COCOAPODS = "cocoapods"
    HOMEBREW = "homebrew"
    NUGET = "nuget"
    PACKAGIST = "packagist"
    RUBYGEMS = "rubygems"
    DOCS = "docs"
    CUSTOM_DB = "custom_db"
    PUB = "pub"


class ConflictSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PackageVersion:
    """Unified package version representation"""

    version: str
    ecosystem: Ecosystem
    release_date: Optional[datetime] = None
    deprecated: bool = False
    yanked: bool = False
    prerelease: bool = False


@dataclass
class Dependency:
    """Unified dependency representation"""

    name: str
    version_spec: str
    ecosystem: Ecosystem
    optional: bool = False
    dev_only: bool = False
    resolved_version: Optional[str] = None


@dataclass
class SystemRequirement:
    """Unified system requirement"""

    type: str  # 'runtime', 'compiler', 'os', 'arch', etc.
    name: str
    version_spec: Optional[str] = None
    optional: bool = False


@dataclass
class CompatibilityIssue:
    """Represents a compatibility issue"""

    severity: ConflictSeverity
    ecosystem: Ecosystem
    description: str
    affected_versions: List[str] = field(default_factory=list)
    resolution: Optional[str] = None


_CLIENT_BUILDERS: Dict[Ecosystem, Any] = {}


def _register_client(ecosystem: Ecosystem, module: str, class_name: str):
    """Register a lazy-loaded data source client builder."""
    _CLIENT_BUILDERS[ecosystem] = lambda: getattr(
        importlib.import_module(module), class_name
    )()


_register_client(Ecosystem.PYPI, "backend.data_sources.pypi_client", "PyPIClient")
_register_client(Ecosystem.NPM, "backend.data_sources.npm_client", "NPMClient")
_register_client(Ecosystem.CONDA, "backend.data_sources.conda_client", "CondaClient")
_register_client(Ecosystem.MAVEN, "backend.data_sources.maven_client", "MavenClient")
_register_client(Ecosystem.CRATES, "backend.data_sources.crates_client", "CratesClient")
_register_client(
    Ecosystem.GOMODULES, "backend.data_sources.gomodules_client", "GoModulesClient"
)
_register_client(Ecosystem.APT, "backend.data_sources.apt_client", "APTClient")
_register_client(Ecosystem.APK, "backend.data_sources.apk_client", "APKClient")
_register_client(
    Ecosystem.COCOAPODS, "backend.data_sources.cocoapods_client", "CocoaPodsClient"
)
_register_client(
    Ecosystem.HOMEBREW, "backend.data_sources.homebrew_client", "HomebrewClient"
)
_register_client(Ecosystem.NUGET, "backend.data_sources.nuget_client", "NuGetClient")
_register_client(
    Ecosystem.PACKAGIST, "backend.data_sources.packagist_client", "PackagistClient"
)
_register_client(
    Ecosystem.RUBYGEMS, "backend.data_sources.rubygems_client", "RubyGemsClient"
)
_register_client(
    Ecosystem.DOCS, "backend.data_sources.documentation_scraper", "DocumentationScraper"
)
_register_client(
    Ecosystem.CUSTOM_DB, "backend.database.compatibility_db", "CompatibilityDB"
)
_register_client(Ecosystem.PUB, "backend.data_sources.pub_client", "PubClient")


class DataAggregator:
    def __init__(
        self, cache_ttl: int = 3600, max_workers: int = 10, enable_caching: bool = True
    ):
        self._sources: Dict[Ecosystem, Any] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.cache_ttl = cache_ttl
        self.enable_caching = enable_caching
        self._ecosystem_cache: Dict[str, List[Ecosystem]] = {}

    @property
    def sources(self) -> Dict[str, Any]:
        """Expose lazy-initialized sources keyed by ecosystem name."""
        return {eco.value: client for eco, client in self._sources.items()}

    def _get_client(self, ecosystem: Ecosystem) -> Any:
        """Lazily create and cache a data source client."""
        client = self._sources.get(ecosystem)
        if client is None:
            builder = _CLIENT_BUILDERS.get(ecosystem)
            if builder is None:
                raise ValueError(f"Unknown ecosystem: {ecosystem}")
            client = builder()
            self._sources[ecosystem] = client
        return client

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    async def close(self):
        """Cleanup resources"""
        self.executor.shutdown(wait=True)
        for client in self._sources.values():
            if hasattr(client, "close"):
                await client.close()

    def _get_cache_key(self, method: str, *args, **kwargs) -> str:
        """Generate cache key"""
        key_data = {"method": method, "args": args, "kwargs": kwargs}

        # If system_info is in kwargs, use hash_system_info
        if "system_info" in kwargs:
            system_info = kwargs["system_info"]
            kwargs = kwargs.copy()
            kwargs["system_info"] = hash_system_info(system_info)

        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()

    async def get_package_info(
        self,
        package_name: str,
        ecosystem: Optional[Union[str, Ecosystem]] = None,
        version: Optional[str] = None,
        include_dependencies: bool = True,
        include_versions: bool = True,
        include_documentation: bool = True,
    ) -> Dict[str, Any]:
        """Get comprehensive package information from all sources"""
        if ecosystem and isinstance(ecosystem, str):
            eco_str = ecosystem
        elif ecosystem and isinstance(ecosystem, Ecosystem):
            eco_str = ecosystem.value
        else:
            eco_str = ""
        # Only normalize for PyPI-style ecosystems where dots/underscores
        # are equivalent to hyphens.  gomodules, nuget, maven, cocoapods
        # use dots as semantic separators.
        _dot_sensitive = {"gomodules", "nuget", "maven", "cocoapods"}
        if eco_str not in _dot_sensitive:
            package_name = normalize_package_name(package_name)

        # Check cache
        cache_key = self._get_cache_key(
            "get_package_info",
            package_name,
            ecosystem,
            version,
            include_dependencies,
            include_versions,
        )
        cached_result = await cache_manager.get(cache_key)
        if cached_result:
            return cached_result

        # Determine ecosystems to check
        if ecosystem:
            if isinstance(ecosystem, str):
                ecosystem = Ecosystem(sanitize_ecosystem_name(ecosystem))
            ecosystems = [ecosystem]
        else:
            ecosystems = await self._detect_ecosystems(package_name)

        # Gather data from all relevant sources concurrently
        tasks = []
        for eco in ecosystems:
            tasks.append(
                self._fetch_package_data(
                    eco, package_name, version, include_dependencies, include_versions
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        aggregated_info: Dict[str, Any] = {
            "name": package_name,
            "version": version,
            "ecosystems": {},
            "unified_data": {
                "description": None,
                "license": None,
                "homepage": None,
                "repository": None,
                "keywords": set(),
                "authors": [],
                "maintainers": [],
            },
            "versions": {},
            "dependencies": {},
            "system_requirements": {},
            "compatibility_matrix": {},
            "conflicts": [],
            "quality_metrics": {},
            "documentation": {},
            "metadata": {
                "aggregation_timestamp": datetime.now().isoformat(),
                "data_sources": [],
            },
        }

        # Process results
        for eco, result in zip(ecosystems, results):
            if isinstance(result, Exception):
                logger.error(f"Error fetching from {eco.value}: {result}")
                aggregated_info["metadata"]["data_sources"].append(
                    {"ecosystem": eco.value, "status": "error", "error": str(result)}
                )
                continue

            if result:
                eco_result: Dict[Any, Any] = result  # type: ignore[assignment]
                aggregated_info["ecosystems"][eco.value] = eco_result
                aggregated_info["metadata"]["data_sources"].append(
                    {"ecosystem": eco.value, "status": "success"}
                )
                await self._merge_ecosystem_data(aggregated_info, eco, eco_result)

        # Add custom database information
        custom_data = await self._fetch_custom_compatibility(package_name)
        if custom_data:
            await self._merge_custom_data(aggregated_info, custom_data)

        # Perform cross-ecosystem analysis
        await self._analyze_cross_ecosystem_compatibility(aggregated_info)

        # Calculate quality scores
        aggregated_info["quality_metrics"] = self._calculate_quality_metrics(
            aggregated_info
        )

        # Add documentation if requested
        if include_documentation:
            aggregated_info["documentation"] = await self._aggregate_documentation(
                package_name, ecosystems
            )

        # Check for security vulnerabilities
        vulnerabilities = []
        for eco in ecosystems:
            if eco != Ecosystem.DOCS and eco != Ecosystem.CUSTOM_DB:
                vulns = await self.check_vulnerabilities(
                    package_name, eco.value, version
                )
                vulnerabilities.extend(vulns)
        aggregated_info["security"] = {
            "vulnerabilities": vulnerabilities,
            "vulnerability_count": len(vulnerabilities),
        }

        # Cache the result
        await cache_manager.set(cache_key, aggregated_info, ttl=self.cache_ttl)

        return aggregated_info

    async def _detect_ecosystems(self, package_name: str) -> List[Ecosystem]:
        """Detect which ecosystems a package might belong to"""
        package_name = normalize_package_name(package_name)

        # Check cache
        if package_name in self._ecosystem_cache:
            return self._ecosystem_cache[package_name]

        ecosystems: List[Ecosystem] = []

        # Check each source concurrently
        tasks = []
        for eco in Ecosystem:
            if eco == Ecosystem.DOCS:  # Skip docs for ecosystem detection
                continue
            tasks.append(self._check_ecosystem_exists(eco, package_name))

        results = await asyncio.gather(*tasks)

        for eco, exists in zip([e for e in Ecosystem if e != Ecosystem.DOCS], results):
            if exists:
                ecosystems.append(eco)

        # Always check documentation if any ecosystem found
        if ecosystems:
            ecosystems.append(Ecosystem.DOCS)

        # Cache the result
        self._ecosystem_cache[package_name] = ecosystems

        return ecosystems

    async def _check_ecosystem_exists(
        self, ecosystem: Ecosystem, package_name: str
    ) -> bool:
        """Check if package exists in an ecosystem"""
        package_name = normalize_package_name(package_name)
        try:
            client = self._get_client(ecosystem)

            # Handle different client interfaces
            if hasattr(client, "package_exists"):
                if asyncio.iscoroutinefunction(client.package_exists):
                    return await client.package_exists(package_name)
                else:
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(
                        self.executor, client.package_exists, package_name
                    )
            else:
                # Try to get package info as existence check
                try:
                    if hasattr(client, "get_package_info_async"):
                        info = await client.get_package_info_async(package_name)
                    else:
                        loop = asyncio.get_event_loop()
                        info = await loop.run_in_executor(
                            self.executor, client.get_package_info, package_name
                        )
                    return info is not None
                except Exception:
                    return False

        except Exception as e:
            logger.debug(f"Error checking {package_name} in {ecosystem.value}: {e}")
            return False

    async def _fetch_package_data(
        self,
        ecosystem: Ecosystem,
        package_name: str,
        version: Optional[str],
        include_dependencies: bool,
        include_versions: bool,
    ) -> Dict:
        """Fetch package data from a specific ecosystem"""
        _dot_sensitive = {"gomodules", "nuget", "maven", "cocoapods"}
        if ecosystem.value not in _dot_sensitive:
            package_name = normalize_package_name(package_name)
        try:
            client = self._get_client(ecosystem)

            # Build method arguments based on client capabilities
            kwargs: Dict[str, Any] = {}
            if version and hasattr(client, "get_package_version"):
                method_name = "get_package_version"
                args: tuple = (package_name, version)
            else:
                method_name = "get_package_info"
                args = (package_name,)

                # Add optional parameters if supported
                if hasattr(client, "get_package_info_async"):
                    sig = client.get_package_info_async.__code__.co_varnames
                elif hasattr(client, "get_package_info"):
                    sig = client.get_package_info.__code__.co_varnames
                else:
                    sig = []

                if "include_dependencies" in sig:
                    kwargs["include_dependencies"] = include_dependencies
                if "include_versions" in sig:
                    kwargs["include_versions"] = include_versions

            # Call the appropriate method
            method = None
            if hasattr(client, f"{method_name}_async"):
                method = getattr(client, f"{method_name}_async")
            elif asyncio.iscoroutinefunction(getattr(client, method_name, None)):
                method = getattr(client, method_name)
            if method is not None:
                result = await method(*args, **kwargs)
            else:
                method = getattr(client, method_name)
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self.executor, lambda: method(*args, **kwargs)
                )

            return result

        except Exception as e:
            logger.error(f"Error fetching {package_name} from {ecosystem.value}: {e}")
            raise

    async def _merge_ecosystem_data(
        self, aggregated: Dict, ecosystem: Ecosystem, data: Dict
    ):
        """Merge data from an ecosystem into aggregated result"""

        # Merge basic metadata
        unified = aggregated["unified_data"]

        # Description (prefer longer descriptions)
        if "description" in data and data["description"]:
            if not unified["description"] or len(data["description"]) > len(
                unified["description"]
            ):
                unified["description"] = data["description"]

        # License
        if "license" in data and data["license"]:
            if not unified["license"]:
                unified["license"] = data["license"]

        # Homepage
        if "homepage" in data and data["homepage"]:
            if not unified["homepage"]:
                unified["homepage"] = data["homepage"]

        # Repository
        repo_keys = ["repository", "repo", "source"]
        for key in repo_keys:
            if key in data and data[key]:
                if not unified["repository"]:
                    unified["repository"] = data[key]
                break

        # Keywords
        if "keywords" in data and isinstance(data["keywords"], list):
            unified["keywords"].update(data["keywords"])

        # Authors and maintainers
        for person_type in ["authors", "author", "maintainers", "maintainer"]:
            if person_type in data:
                persons = data[person_type]
                if isinstance(persons, str):
                    persons = [persons]
                elif isinstance(persons, dict):
                    persons = [persons]

                target = "authors" if "author" in person_type else "maintainers"
                if isinstance(persons, list):
                    unified[target].extend(persons)

        # Merge versions
        if "versions" in data:
            if ecosystem.value not in aggregated["versions"]:
                aggregated["versions"][ecosystem.value] = []

            versions = data["versions"]
            if isinstance(versions, list):
                aggregated["versions"][ecosystem.value] = versions
            elif isinstance(versions, dict):
                aggregated["versions"][ecosystem.value] = list(versions.keys())

        # Merge dependencies
        if "dependencies" in data:
            aggregated["dependencies"][ecosystem.value] = self._normalize_dependencies(
                data["dependencies"], ecosystem
            )

        # Merge system requirements
        if "system_requirements" in data:
            aggregated["system_requirements"][ecosystem.value] = (
                self._normalize_system_requirements(
                    data["system_requirements"], ecosystem
                )
            )

        # Extract compatibility information
        if "compatibility" in data:
            aggregated["compatibility_matrix"][ecosystem.value] = data["compatibility"]
        elif "compatibility_matrix" in data:
            aggregated["compatibility_matrix"][ecosystem.value] = data[
                "compatibility_matrix"
            ]

    def _normalize_dependencies(
        self, deps: Union[Dict, List], ecosystem: Ecosystem
    ) -> Dict[str, List[Dependency]]:
        """Normalize dependency data from different ecosystems"""
        normalized = defaultdict(list)

        if isinstance(deps, dict):
            # Handle different dependency categories
            categories = {
                "dependencies": False,
                "required": False,
                "dev_dependencies": True,
                "devDependencies": True,
                "test_dependencies": True,
                "build_dependencies": True,
                "optional_dependencies": True,
                "optionalDependencies": True,
                "peer_dependencies": False,
                "peerDependencies": False,
            }

            for category, is_dev in categories.items():
                if category in deps:
                    cat_deps = deps[category]
                    if isinstance(cat_deps, dict):
                        for name, version_spec in cat_deps.items():
                            normalized["all"].append(
                                Dependency(
                                    name=name,
                                    version_spec=str(version_spec),
                                    ecosystem=ecosystem,
                                    dev_only=is_dev,
                                    optional="optional" in category,
                                )
                            )
                    elif isinstance(cat_deps, list):
                        for dep in cat_deps:
                            if isinstance(dep, dict):
                                normalized["all"].append(
                                    Dependency(
                                        name=dep.get("name", ""),
                                        version_spec=dep.get("version", "*"),
                                        ecosystem=ecosystem,
                                        dev_only=is_dev,
                                        optional=dep.get("optional", False),
                                    )
                                )

        elif isinstance(deps, list):
            # Simple list of dependencies
            for dep in deps:
                if isinstance(dep, str):
                    # Parse "name==version" format
                    match = re.match(r"^([^=<>!]+)(.*)$", dep)
                    if match:
                        name, version_spec = match.groups()
                        normalized["all"].append(
                            Dependency(
                                name=name.strip(),
                                version_spec=version_spec.strip() or "*",
                                ecosystem=ecosystem,
                            )
                        )
                elif isinstance(dep, dict):
                    normalized["all"].append(
                        Dependency(
                            name=dep.get("name", ""),
                            version_spec=dep.get("version", "*"),
                            ecosystem=ecosystem,
                            optional=dep.get("optional", False),
                        )
                    )

        return dict(normalized)

    def _normalize_system_requirements(
        self, reqs: Union[Dict, List], ecosystem: Ecosystem
    ) -> List[SystemRequirement]:
        """Normalize system requirements from different ecosystems"""
        normalized = []

        if isinstance(reqs, dict):
            # Handle different requirement types
            if "python" in reqs or "python_version" in reqs:
                py_req = reqs.get("python") or reqs.get("python_version")
                if isinstance(py_req, str):
                    normalized.append(
                        SystemRequirement(
                            type="runtime", name="python", version_spec=py_req
                        )
                    )
                elif isinstance(py_req, dict):
                    normalized.append(
                        SystemRequirement(
                            type="runtime",
                            name="python",
                            version_spec=py_req.get(
                                "version_spec", py_req.get("min", "*")
                            ),
                        )
                    )

            # Node.js requirements
            if "node" in reqs or "node_version" in reqs:
                node_req = reqs.get("node") or reqs.get("node_version")
                if isinstance(node_req, str):
                    normalized.append(
                        SystemRequirement(
                            type="runtime", name="node", version_spec=node_req
                        )
                    )

            # Java requirements
            if "java" in reqs or "java_version" in reqs:
                java_req = reqs.get("java") or reqs.get("java_version")
                if isinstance(java_req, str):
                    normalized.append(
                        SystemRequirement(
                            type="runtime", name="java", version_spec=java_req
                        )
                    )

            # Rust requirements
            if "rust" in reqs or "rust_version" in reqs:
                rust_req = reqs.get("rust") or reqs.get("rust_version")
                if isinstance(rust_req, str):
                    normalized.append(
                        SystemRequirement(
                            type="compiler", name="rust", version_spec=rust_req
                        )
                    )

            # OS requirements
            if "os" in reqs:
                os_reqs = reqs["os"]
                if isinstance(os_reqs, list):
                    for os_name in os_reqs:
                        normalized.append(SystemRequirement(type="os", name=os_name))

            # Architecture requirements
            if "arch" in reqs or "cpu" in reqs:
                arch_reqs = reqs.get("arch") or reqs.get("cpu")
                if isinstance(arch_reqs, list):
                    for arch in arch_reqs:
                        normalized.append(SystemRequirement(type="arch", name=arch))

            # Build tools
            if reqs.get("build_tools_required"):
                normalized.append(
                    SystemRequirement(type="build", name="c++ compiler", optional=False)
                )

        return normalized

    async def _analyze_cross_ecosystem_compatibility(self, aggregated: Dict):
        """Analyze compatibility across ecosystems"""
        conflicts = []

        # Check for version conflicts across ecosystems
        if len(aggregated["ecosystems"]) > 1:
            # Compare versions
            versions_by_eco = aggregated["versions"]
            if len(versions_by_eco) > 1:
                # Find latest version in each ecosystem
                latest_versions = {}
                for eco, versions in versions_by_eco.items():
                    if versions:
                        latest_versions[eco] = versions[0]  # Assuming sorted

                # Check if versions differ significantly
                if len(set(latest_versions.values())) > 1:
                    conflicts.append(
                        CompatibilityIssue(
                            severity=ConflictSeverity.MEDIUM,
                            ecosystem=Ecosystem.CUSTOM_DB,
                            description="Version mismatch across ecosystems",
                            affected_versions=list(latest_versions.values()),
                            resolution="Consider using ecosystem-specific version",
                        )
                    )

        # Check for dependency conflicts
        deps_by_eco = aggregated["dependencies"]
        if len(deps_by_eco) > 1:
            # Find common dependencies with different version requirements
            dep_versions: Dict[str, Dict[str, List[Any]]] = defaultdict(lambda: defaultdict(list))

            for eco, deps in deps_by_eco.items():
                if "all" in deps:
                    for dep in deps["all"]:
                        dep_versions[dep.name][eco].append(dep.version_spec)

            for dep_name, eco_versions in dep_versions.items():
                if len(eco_versions) > 1:
                    # Check if version specs are compatible
                    specs = []
                    for eco, versions in eco_versions.items():
                        specs.extend(versions)

                    if len(set(specs)) > 1 and not self._are_version_specs_compatible(
                        specs
                    ):
                        conflicts.append(
                            CompatibilityIssue(
                                severity=ConflictSeverity.HIGH,
                                ecosystem=Ecosystem.CUSTOM_DB,
                                description=f"Conflicting dependency versions for {dep_name}",
                                affected_versions=specs,
                                resolution="May need to use different versions in different ecosystems",
                            )
                        )

        # Check system requirements conflicts
        sys_reqs_by_eco = aggregated["system_requirements"]
        if len(sys_reqs_by_eco) > 1:
            # Compare runtime requirements
            runtime_reqs: Dict[str, Dict[str, List[Any]]] = defaultdict(lambda: defaultdict(list))

            for eco, reqs in sys_reqs_by_eco.items():
                for req in reqs:
                    if req.type == "runtime":
                        runtime_reqs[req.name][eco].append(req.version_spec)

            for runtime, eco_specs in runtime_reqs.items():
                if len(eco_specs) > 1:
                    all_specs = []
                    for specs in eco_specs.values():
                        all_specs.extend(specs)

                    if not self._are_version_specs_compatible(all_specs):
                        conflicts.append(
                            CompatibilityIssue(
                                severity=ConflictSeverity.CRITICAL,
                                ecosystem=Ecosystem.CUSTOM_DB,
                                description=f"Incompatible {runtime} version requirements",
                                affected_versions=all_specs,
                                resolution=f"Ensure {runtime} version satisfies all requirements",
                            )
                        )

        aggregated["conflicts"] = conflicts

        # Build cross-ecosystem dependency map
        # Detects deps that belong to a different ecosystem than the parent
        cross_eco = []
        dep_ecosystems = aggregated.get("dependencies", {})
        # If the package has dependency entries under multiple ecosystem keys,
        # those represent cross-ecosystem references worth tracking
        if len(dep_ecosystems) > 1:
            for parent_eco, deps_data in dep_ecosystems.items():
                for dep in deps_data.get("all", []):
                    for other_eco in dep_ecosystems:
                        if other_eco != parent_eco:
                            cross_eco.append(
                                {
                                    "source_ecosystem": parent_eco,
                                    "target_ecosystem": other_eco,
                                    "dependency": dep.name,
                                    "version_spec": dep.version_spec,
                                }
                            )
                            break
        aggregated["cross_ecosystem_deps"] = cross_eco

    def _are_version_specs_compatible(self, specs: List[str]) -> bool:
        """Check if multiple version specifications are compatible"""
        # Simplified compatibility check
        # In production, use proper version parsing

        # Remove duplicates
        unique_specs = list(set(specs))

        if len(unique_specs) == 1:
            return True

        # Check for obvious incompatibilities
        has_exact = any(
            not any(op in spec for op in [">", "<", "~", "^", "*"])
            for spec in unique_specs
        )
        has_range = any(
            any(op in spec for op in [">", "<", "~", "^"]) for spec in unique_specs
        )

        if has_exact and has_range:
            return False

        # More sophisticated checks would go here
        return True

    def _calculate_quality_metrics(self, aggregated: Dict) -> Dict[str, float]:
        """Calculate quality metrics for the package"""
        metrics = {
            "documentation_score": 0.0,
            "ecosystem_coverage": 0.0,
            "maintenance_score": 0.0,
            "compatibility_score": 0.0,
            "overall_score": 0.0,
        }

        # Documentation score
        doc_points = 0
        if aggregated["unified_data"]["description"]:
            doc_points += 2
        if aggregated["unified_data"]["homepage"]:
            doc_points += 1
        if aggregated["unified_data"]["repository"]:
            doc_points += 1
        if aggregated.get("documentation"):
            doc_points += 2
        metrics["documentation_score"] = min(doc_points / 6.0, 1.0)

        # Ecosystem coverage
        total_ecosystems = len(
            [e for e in Ecosystem if e not in [Ecosystem.DOCS, Ecosystem.CUSTOM_DB]]
        )
        covered_ecosystems = len(
            [e for e in aggregated["ecosystems"] if e not in ["docs", "custom_db"]]
        )
        metrics["ecosystem_coverage"] = (
            covered_ecosystems / total_ecosystems if total_ecosystems > 0 else 0
        )

        # Maintenance score (based on latest updates)
        # This is simplified - would need actual date parsing
        if aggregated["versions"]:
            metrics["maintenance_score"] = 0.7  # Placeholder

        # Compatibility score
        conflict_count = len(aggregated.get("conflicts", []))
        if conflict_count == 0:
            metrics["compatibility_score"] = 1.0
        elif conflict_count < 3:
            metrics["compatibility_score"] = 0.7
        elif conflict_count < 5:
            metrics["compatibility_score"] = 0.5
        else:
            metrics["compatibility_score"] = 0.3

        # Overall score
        weights = {
            "documentation_score": 0.25,
            "ecosystem_coverage": 0.25,
            "maintenance_score": 0.25,
            "compatibility_score": 0.25,
        }

        metrics["overall_score"] = sum(
            metrics[key] * weight for key, weight in weights.items()
        )

        return metrics

    async def _aggregate_documentation(
        self, package_name: str, ecosystems: List[Ecosystem]
    ) -> Dict[str, Any]:
        """Aggregate documentation from multiple sources"""
        package_name = normalize_package_name(package_name)
        docs: Dict[str, Any] = {
            "official_docs": [],
            "tutorials": [],
            "examples": [],
            "api_reference": None,
            "changelog": None,
        }

        # Get documentation from scraper
        try:
            doc_client = self._get_client(Ecosystem.DOCS)
            if hasattr(doc_client, "get_documentation"):
                doc_data = await self._call_client_method(
                    doc_client, "get_documentation", package_name
                )
                if doc_data:
                    docs.update(doc_data)
        except Exception as e:
            logger.error(f"Error fetching documentation: {e}")

        # Add ecosystem-specific documentation links
        for eco in ecosystems:
            if eco == Ecosystem.PYPI:
                docs["official_docs"].append(
                    {
                        "source": "PyPI",
                        "url": f"https://pypi.org/project/{package_name}/",
                    }
                )
            elif eco == Ecosystem.NPM:
                docs["official_docs"].append(
                    {
                        "source": "npm",
                        "url": f"https://www.npmjs.com/package/{package_name}",
                    }
                )
            elif eco == Ecosystem.CRATES:
                docs["official_docs"].append(
                    {"source": "docs.rs", "url": f"https://docs.rs/{package_name}"}
                )

        return docs

    async def _fetch_custom_compatibility(self, package_name: str) -> Optional[Dict]:
        """Fetch custom compatibility data from database"""
        package_name = normalize_package_name(package_name)
        try:
            client = self._get_client(Ecosystem.CUSTOM_DB)
            return await self._call_client_method(
                client, "get_compatibility_rules", package_name
            )
        except Exception as e:
            logger.error(f"Error fetching custom compatibility: {e}")
            return None

    async def _merge_custom_data(self, aggregated: Dict, custom_data: Dict):
        """Merge custom database information"""
        if "known_conflicts" in custom_data:
            for conflict in custom_data["known_conflicts"]:
                aggregated["conflicts"].append(
                    CompatibilityIssue(
                        severity=ConflictSeverity.HIGH,
                        ecosystem=Ecosystem.CUSTOM_DB,
                        description=conflict.get("description", ""),
                        affected_versions=conflict.get("versions", []),
                        resolution=conflict.get("resolution"),
                    )
                )

        if "verified_combinations" in custom_data:
            if "verified_combinations" not in aggregated:
                aggregated["verified_combinations"] = []
            aggregated["verified_combinations"].extend(
                custom_data["verified_combinations"]
            )

        if "community_notes" in custom_data:
            if "community_notes" not in aggregated:
                aggregated["community_notes"] = []
            aggregated["community_notes"].extend(custom_data["community_notes"])

    async def check_vulnerabilities(
        self, package_name: str, ecosystem: str, version: Optional[str] = None
    ) -> List[Dict]:
        """Check for security vulnerabilities using OSV database"""
        try:
            # Map ecosystem to OSV format
            osv_ecosystem = self._map_ecosystem_to_osv(ecosystem)
            if not osv_ecosystem:
                return []

            query = {"package": {"name": package_name, "ecosystem": osv_ecosystem}}

            if version:
                query["package"]["version"] = version

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    OSV_API_URL, json=query, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        vulnerabilities = data.get("vulns", [])
                        return vulnerabilities
                    else:
                        logger.error(f"OSV API error: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error checking vulnerabilities for {package_name}: {e}")
            return []

    def _map_ecosystem_to_osv(self, ecosystem: str) -> Optional[str]:
        """Map internal ecosystem names to OSV ecosystem names"""
        mapping = {
            "pypi": "PyPI",
            "npm": "npm",
            "maven": "Maven",
            "crates": "crates.io",
            "gomodules": "Go",
            "rubygems": "RubyGems",
            "packagist": "Packagist",
            "nuget": "NuGet",
        }
        return mapping.get(ecosystem.lower())

    async def _call_client_method(
        self, client: Any, method_name: str, *args, **kwargs
    ) -> Any:
        """Call a client method, handling both sync and async"""
        if hasattr(client, f"{method_name}_async"):
            method = getattr(client, f"{method_name}_async")
            return await method(*args, **kwargs)
        elif hasattr(client, method_name):
            method = getattr(client, method_name)
            if asyncio.iscoroutinefunction(method):
                return await method(*args, **kwargs)
            else:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    self.executor, lambda: method(*args, **kwargs)
                )
        else:
            raise AttributeError(f"Client has no method {method_name}")

    async def search_packages(
        self,
        query: str,
        ecosystems: Optional[List[Union[str, Ecosystem]]] = None,
        limit: int = 10,
    ) -> Dict[str, List[Dict]]:
        """Search for packages across multiple ecosystems"""
        query = normalize_package_name(query)
        eco_list: List[Ecosystem]
        if ecosystems:
            eco_list = []
            for e in ecosystems:
                if isinstance(e, str):
                    try:
                        eco_list.append(Ecosystem(sanitize_ecosystem_name(e)))
                    except ValueError:
                        logger.warning(f"Invalid ecosystem: {e}")
                        continue
                else:
                    eco_list.append(e)
        else:
            eco_list = [
                e for e in Ecosystem if e not in [Ecosystem.DOCS, Ecosystem.CUSTOM_DB]
            ]

        results: Dict[str, List[Dict]] = {}
        tasks = []

        for eco in eco_list:
            client = self._get_client(eco)
            if hasattr(client, "search_packages") or hasattr(client, "search"):
                tasks.append(self._search_in_ecosystem(eco, client, query, limit))

        search_results = await asyncio.gather(*tasks, return_exceptions=True)

        for eco, result in zip(eco_list, search_results):
            if isinstance(result, Exception):
                logger.error(f"Search error in {eco.value}: {result}")
                results[eco.value] = []
            else:
                search_result: List[Dict] = result or []  # type: ignore[assignment]
                results[eco.value] = search_result

        return results

    async def _search_in_ecosystem(
        self, ecosystem: Ecosystem, client: Any, query: str, limit: int
    ) -> List[Dict]:
        """Search in a specific ecosystem"""
        query = normalize_package_name(query)
        try:
            if hasattr(client, "search_packages"):
                return await self._call_client_method(
                    client, "search_packages", query, limit
                )
            elif hasattr(client, "search"):
                return await self._call_client_method(client, "search", query, limit)
            else:
                return []
        except Exception as e:
            logger.error(f"Search error in {ecosystem.value}: {e}")
            return []

    async def check_compatibility(
        self, packages: List[Dict[str, str]], system_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check compatibility of multiple packages with system"""
        compatibility_report: Dict[str, Any] = {
            "overall_compatible": True,
            "package_compatibility": {},
            "conflicts": [],
            "warnings": [],
            "system_requirements": {},
            "recommendations": [],
        }

        # Check each package
        for pkg in packages:
            name = pkg.get("name")
            if name:
                name = normalize_package_name(name)
                pkg["name"] = name
            version = pkg.get("version")
            ecosystem = pkg.get("ecosystem")

            if ecosystem and isinstance(ecosystem, str):
                ecosystem = sanitize_ecosystem_name(ecosystem)

            if not name:
                continue

            # Get package info
            pkg_info = await self.get_package_info(name, ecosystem, version)

            # Check individual compatibility
            pkg_compat: Dict[str, Any] = {"compatible": True, "issues": [], "requirements": []}

            # Check system requirements
            for eco, reqs in pkg_info.get("system_requirements", {}).items():
                for req in reqs:
                    if req.type == "runtime" and req.name in system_info:
                        if not self._check_requirement_compatibility(req, system_info):
                            pkg_compat["compatible"] = False
                            pkg_compat["issues"].append(
                                f"Requires {req.name} {req.version_spec}"
                            )

            compatibility_report["package_compatibility"][name] = pkg_compat

            if not pkg_compat["compatible"]:
                compatibility_report["overall_compatible"] = False

        # Check for inter-package conflicts
        await self._check_inter_package_conflicts(packages, compatibility_report)

        # Generate recommendations
        self._generate_compatibility_recommendations(compatibility_report)

        return compatibility_report

    async def _check_inter_package_conflicts(self, packages: List[Dict], report: Dict):
        """Check for conflicts between packages"""
        # Check for duplicate dependencies with different versions
        all_deps = defaultdict(list)

        for pkg in packages:
            name = pkg.get("name")
            if not name:
                continue

            name = normalize_package_name(name)

            pkg_info = await self.get_package_info(name)
            for eco, deps in pkg_info.get("dependencies", {}).items():
                if "all" in deps:
                    for dep in deps["all"]:
                        all_deps[dep.name].append(
                            {
                                "package": name,
                                "version_spec": dep.version_spec,
                                "ecosystem": eco,
                            }
                        )

        # Find conflicts
        for dep_name, requirements in all_deps.items():
            if len(requirements) > 1:
                unique_specs = set(r["version_spec"] for r in requirements)
                if len(unique_specs) > 1 and not self._are_version_specs_compatible(
                    list(unique_specs)
                ):
                    report["conflicts"].append(
                        {
                            "type": "dependency_conflict",
                            "dependency": dep_name,
                            "requirements": requirements,
                        }
                    )

    def _check_requirement_compatibility(
        self, requirement: SystemRequirement, system_info: Dict
    ) -> bool:
        """Check if system meets requirement"""
        from backend.core.utils import is_compatible_version

        if requirement.name not in system_info:
            return requirement.optional

        system_version = str(system_info[requirement.name])
        if requirement.version_spec:
            return is_compatible_version(system_version, requirement.version_spec)
        return True

    def _generate_compatibility_recommendations(self, report: Dict):
        """Generate recommendations based on compatibility analysis"""
        if not report["overall_compatible"]:
            report["recommendations"].append(
                "Consider using a virtual environment to isolate dependencies"
            )

        if report["conflicts"]:
            report["recommendations"].append(
                "Review dependency conflicts and consider using compatible versions"
            )

        # Add more intelligent recommendations based on specific issues
        for pkg_name, compat in report["package_compatibility"].items():
            if not compat["compatible"]:
                for issue in compat["issues"]:
                    if "python" in issue.lower():
                        report["recommendations"].append(
                            f"Consider using pyenv or conda to manage Python versions for {pkg_name}"
                        )
                    elif "node" in issue.lower():
                        report["recommendations"].append(
                            f"Consider using nvm to manage Node.js versions for {pkg_name}"
                        )
