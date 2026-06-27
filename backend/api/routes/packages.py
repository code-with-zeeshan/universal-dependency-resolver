# backend/api/routes/packages.py
from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks, Request
from typing import List, Optional, Dict
from pydantic import BaseModel
import logging
from packaging import version

from backend.core.data_aggregator import DataAggregator
from backend.core.conflict_resolver import ConflictResolver
from backend.core.export_generator import ExportGenerator
from backend.database.compatibility_db import CompatibilityDB
from backend.core.system_scanner import SystemScanner
from backend.api.dependencies import (
    get_data_aggregator,
    get_conflict_resolver,
    get_export_generator,
    get_compatibility_db,
    get_system_scanner,
    limiter,
)
from backend.api.schemas import (
    ResolveRequest,
    ExportRequest,
)
from backend.api.auth import get_current_user
from backend.api.helpers.packages import (
    _filter_by_python_version,
    _sort_search_results,
    _get_recursive_dependencies,
    _count_dependencies,
    _generate_compatibility_summary,
    _extract_version_compatibility,
    _get_package_metrics,
    _validate_system_info,
    _analyze_compatibility_reports,
    _detect_package_ecosystem,
    _filter_comparison_aspects,
    _generate_comparison_summary,
)
from backend.api.helpers.compatibility import (
    _check_version_compatibility_detailed,
    _is_prerelease,
    SystemSpec,
)
from backend.database.models import User

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()


class PackageSearchRequest(BaseModel):
    query: str
    ecosystems: Optional[List[str]] = None
    limit: int = 20


@router.get("/{ecosystem}/{name}")
@limiter.limit("30/minute")
async def get_package_info(
    request: Request,
    ecosystem: str,
    name: str,
    aggregator: DataAggregator = Depends(get_data_aggregator),
    current_user: User = Depends(get_current_user),
):
    """Get package information from specified ecosystem"""
    try:
        info = await aggregator.get_package_info(name, ecosystem)
        if not info:
            raise HTTPException(
                status_code=404, detail=f"Package {name} not found in {ecosystem}"
            )
        return {"status": "success", "data": info}
    except ValueError as e:
        logger.error(f"Invalid package data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Package fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/resolve")
@limiter.limit("10/minute")
async def resolve_dependencies(
    request: Request,
    resolve_request: ResolveRequest,
    scanner: SystemScanner = Depends(get_system_scanner),
    aggregator: DataAggregator = Depends(get_data_aggregator),
    resolver: ConflictResolver = Depends(get_conflict_resolver),
    current_user: User = Depends(get_current_user),
):
    """Resolve dependencies for multiple packages"""
    try:
        # Get system info if needed
        system_info = (
            await scanner.scan_all()
            if resolve_request.auto_detect_system and not resolve_request.system_info
            else resolve_request.system_info.dict()
            if resolve_request.system_info
            else {}
        )

        # Get package information
        packages_info = []
        for pkg in resolve_request.packages:
            info = await aggregator.get_package_info(pkg.name, pkg.ecosystem)
            if info:
                packages_info.append(info)
            else:
                logger.warning(f"Package {pkg.name} not found in {pkg.ecosystem}")

        # Resolve conflicts
        resolved = resolver.resolve_dependencies(
            packages_info, system_info, resolve_request.prefer_compatibility
        )

        return {"status": "success", "data": resolved}
    except ValueError as e:
        logger.error(f"Invalid resolve data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Dependency resolution failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/export")
@limiter.limit("20/minute")
async def export_configuration(
    request: Request,
    export_request: ExportRequest,
    generator: ExportGenerator = Depends(get_export_generator),
    current_user: User = Depends(get_current_user),
):
    """Export resolved dependencies to various formats"""
    try:
        output = generator.generate(
            export_request.resolved_packages,
            export_request.format,
            export_request.system_info,
            export_request.options,
        )
        return {"status": "success", "format": export_request.format, "content": output}
    except ValueError as e:
        logger.error(f"Invalid export data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/export-formats")
@limiter.limit("60/minute")
async def get_export_formats(
    request: Request, current_user: User = Depends(get_current_user)
):
    """Get available export formats"""
    try:
        formats = [
            {"format": fmt, "ecosystem": eco, "description": desc}
            for fmt, eco, desc in [
                ("requirements.txt", "python", "Python pip requirements file"),
                ("package.json", "node", "Node.js package configuration"),
                ("environment.yml", "conda", "Conda environment file"),
                ("pyproject.toml", "python", "Poetry/PEP 517 configuration"),
                ("Dockerfile", "multi", "Docker container definition"),
                ("docker-compose.yml", "multi", "Docker Compose configuration"),
                ("install.sh", "multi", "Shell installation script"),
                ("install.bat", "multi", "Windows batch installation script"),
                ("CMakeLists.txt", "cpp", "CMake build configuration"),
                ("cargo.toml", "rust", "Rust Cargo configuration"),
                ("build.gradle", "java", "Gradle build configuration"),
                ("pom.xml", "java", "Maven project configuration"),
            ]
        ]
        return {"status": "success", "formats": formats}
    except Exception as e:
        logger.error(f"Export formats fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Keep all your existing endpoints below (search, details, versions, etc.)
@router.get("/search")
@limiter.limit("60/minute")
async def search_packages(
    request: Request,
    q: str = Query(...),
    ecosystems: Optional[str] = Query(
        None, description="Comma-separated list of ecosystems"
    ),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query(
        "relevance", description="Sort by: relevance, downloads, name, updated"
    ),
    python_version: Optional[str] = Query(
        None, description="Filter by Python version compatibility"
    ),
    aggregator: DataAggregator = Depends(get_data_aggregator),
    current_user: User = Depends(get_current_user),
):
    """Search for packages across multiple ecosystems"""
    try:
        logger.info(f"Searching for packages: query='{q}', ecosystems={ecosystems}")

        ecosystem_list = ecosystems.split(",") if ecosystems else None

        results = await aggregator.search_packages(q, ecosystems=ecosystem_list, limit=limit)

        # Apply post-processing (filtering, sorting)
        for ecosystem, ecosystem_results in list(results.items()):
            # Filter by Python version if specified
            if python_version and ecosystem in ["pypi", "conda"] and isinstance(ecosystem_results, list):
                ecosystem_results = _filter_by_python_version(
                    ecosystem_results, python_version
                )

            # Sort results
            if isinstance(ecosystem_results, list):
                ecosystem_results = _sort_search_results(ecosystem_results, sort_by)
                results[ecosystem] = ecosystem_results

        # Calculate total count
        total_count = sum(
            len(r) if isinstance(r, list) else 0 for r in results.values()
        )

        return {
            "status": "success",
            "query": q,
            "total_count": total_count,
            "results": results,
            "filters_applied": {
                "ecosystems": ecosystem_list,
                "python_version": python_version,
                "sort_by": sort_by,
            },
        }
    except ValueError as e:
        logger.error(f"Invalid search parameters: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{ecosystem}/{package_name}/details")
@limiter.limit("120/minute")
async def get_package_details(
    request: Request,
    ecosystem: str,
    package_name: str,
    include_metrics: bool = Query(
        False, description="Include download and usage metrics"
    ),
    aggregator: DataAggregator = Depends(get_data_aggregator),
    current_user: User = Depends(get_current_user),
):
    """Get detailed information about a specific package"""
    try:
        logger.info(f"Getting package details: {ecosystem}/{package_name}")

        package_info = await aggregator.get_package_info(package_name, ecosystem)

        if not package_info or ecosystem not in package_info.get("ecosystems", {}):
            logger.warning(f"Package not found: {ecosystem}/{package_name}")
            raise HTTPException(
                status_code=404,
                detail=f"Package {package_name} not found in {ecosystem}",
            )

        ecosystem_data = package_info["ecosystems"][ecosystem]

        # Add metrics if requested
        if include_metrics:
            logger.debug(f"Fetching metrics for {ecosystem}/{package_name}")
            metrics = await _get_package_metrics(ecosystem, package_name)
            ecosystem_data["metrics"] = metrics

        # Add compatibility summary
        compatibility_summary = _generate_compatibility_summary(package_info)

        return {
            "status": "success",
            "data": {
                "name": package_name,
                "ecosystem": ecosystem,
                "info": ecosystem_data,
                "compatibility_matrix": package_info.get("compatibility_matrix", {}),
                "system_requirements": package_info.get("system_requirements", {}),
                "compatibility_summary": compatibility_summary,
            },
        }
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Invalid package data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get package details: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{ecosystem}/{package_name}/versions")
@limiter.limit("120/minute")
async def get_package_versions(
    request: Request,
    ecosystem: str,
    package_name: str,
    compatible_with: Optional[str] = Query(
        None,
        description="Filter versions compatible with system (e.g., 'os=linux,python=3.9,cuda=11.2')",
    ),
    include_yanked: bool = Query(
        False, description="Include yanked/deprecated versions"
    ),
    include_prerelease: bool = Query(False, description="Include pre-release versions"),
    aggregator: DataAggregator = Depends(get_data_aggregator),
    current_user: User = Depends(get_current_user),
):
    """Get all available versions of a package"""
    try:
        logger.info(f"Getting versions for: {ecosystem}/{package_name}")

        if ecosystem not in aggregator.sources:
            raise HTTPException(
                status_code=400, detail=f"Unknown ecosystem: {ecosystem}"
            )

        source = aggregator.sources[ecosystem]
        versions = await source.get_versions(package_name)

        # Parse system spec if provided
        system_spec = None
        if compatible_with:
            system_spec = SystemSpec.from_string(compatible_with)
            logger.debug(f"Filtering versions for compatibility: {compatible_with}")

        # Filter and annotate versions
        filtered_versions = []
        for v in versions:
            # Skip yanked versions if not requested
            if not include_yanked and v.get("yanked", False):
                continue

            # Skip pre-release versions if not requested
            if not include_prerelease and _is_prerelease(v.get("version", "")):
                continue

            # Check compatibility if system spec provided
            if system_spec:
                is_compatible, notes = _check_version_compatibility_detailed(
                    v, system_spec
                )
                v["compatible"] = is_compatible
                v["compatibility_notes"] = notes

                # Only include compatible versions unless explicitly showing all
                if not is_compatible and compatible_with:
                    continue

            filtered_versions.append(v)

        # Sort versions (newest first)
        filtered_versions.sort(
            key=lambda x: version.parse(x.get("version", "0.0.0")), reverse=True
        )

        logger.info(
            f"Found {len(filtered_versions)}/{len(versions)} versions after filtering"
        )

        return {
            "status": "success",
            "package": package_name,
            "ecosystem": ecosystem,
            "total_versions": len(versions),
            "filtered_count": len(filtered_versions),
            "versions": filtered_versions,
            "filters": {
                "compatible_with": compatible_with,
                "include_yanked": include_yanked,
                "include_prerelease": include_prerelease,
            },
        }
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Invalid version data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get versions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{ecosystem}/{package_name}/dependencies")
@limiter.limit("120/minute")
async def get_package_dependencies(
    request: Request,
    ecosystem: str,
    package_name: str,
    version: Optional[str] = Query(None, description="Specific version to check"),
    recursive: bool = Query(False, description="Get dependencies recursively"),
    max_depth: int = Query(3, ge=1, le=5, description="Maximum recursion depth"),
    aggregator: DataAggregator = Depends(get_data_aggregator),
    current_user: User = Depends(get_current_user),
):
    """Get dependencies for a specific package version"""
    try:
        logger.info(
            f"Getting dependencies for: {ecosystem}/{package_name}@{version or 'latest'}"
        )

        if ecosystem not in aggregator.sources:
            raise HTTPException(
                status_code=400, detail=f"Unknown ecosystem: {ecosystem}"
            )

        source = aggregator.sources[ecosystem]

        if recursive:
            logger.debug(f"Getting recursive dependencies with max_depth={max_depth}")
            # Get recursive dependencies
            dep_tree = await _get_recursive_dependencies(
                source, package_name, version, max_depth
            )
            return {
                "status": "success",
                "package": package_name,
                "version": version or "latest",
                "dependency_tree": dep_tree,
                "total_dependencies": _count_dependencies(dep_tree),
            }
        else:
            # Get direct dependencies only
            dependencies = await source.get_dependencies(package_name, version)

            return {
                "status": "success",
                "package": package_name,
                "version": version or "latest",
                "dependencies": dependencies,
            }
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Invalid dependency data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get dependencies: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{ecosystem}/{package_name}/compatibility")
@limiter.limit("120/minute")
async def get_package_compatibility(
    request: Request,
    ecosystem: str,
    package_name: str,
    version: Optional[str] = Query(None, description="Specific version to check"),
    compatibility_db: CompatibilityDB = Depends(get_compatibility_db),
    aggregator: DataAggregator = Depends(get_data_aggregator),
    current_user: User = Depends(get_current_user),
):
    """Get known compatibility information for a package"""
    try:
        logger.info(
            f"Getting compatibility info for: {ecosystem}/{package_name}@{version or 'latest'}"
        )

        # Get from custom database
        db_compatibility = compatibility_db.get_compatibility_rules(package_name)

        # Get from package metadata
        package_info = await aggregator.get_package_info(package_name, ecosystem)

        # Get version-specific compatibility if version specified
        version_compatibility = {}
        if version and package_info:
            version_compatibility = _extract_version_compatibility(
                package_info, version
            )

        # Get community statistics
        community_stats = compatibility_db.get_compatibility_statistics(
            package_name, ecosystem, version
        )

        return {
            "status": "success",
            "package": package_name,
            "ecosystem": ecosystem,
            "version": version,
            "compatibility": {
                "known_conflicts": db_compatibility.get("known_conflicts", []),
                "verified_combinations": db_compatibility.get(
                    "verified_combinations", []
                ),
                "system_requirements": package_info.get("system_requirements", {}),
                "version_specific": version_compatibility,
                "community_reports": db_compatibility.get("community_reports", []),
                "statistics": community_stats,
            },
        }
    except ValueError as e:
        logger.error(f"Invalid compatibility data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get compatibility info: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{ecosystem}/{package_name}/compatibility/report")
@limiter.limit("30/minute")
async def report_compatibility(
    request: Request,
    ecosystem: str,
    package_name: str,
    version: str,
    system_info: Dict,
    works: bool,
    notes: Optional[str] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    compatibility_db: CompatibilityDB = Depends(get_compatibility_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a compatibility report"""
    try:
        logger.info(
            f"Receiving compatibility report for: {ecosystem}/{package_name}@{version}"
        )

        # Validate system info
        if not _validate_system_info(system_info):
            logger.warning("Invalid system info format in compatibility report")
            raise HTTPException(status_code=400, detail="Invalid system info format")

        report_id = compatibility_db.add_compatibility_report(
            package_name=package_name,
            version=version,
            ecosystem=ecosystem,
            system_info=system_info,
            works=works,
            notes=notes,
        )

        logger.info(f"Compatibility report saved with ID: {report_id}")

        # Background task to analyze and aggregate reports
        background_tasks.add_task(
            _analyze_compatibility_reports, package_name, ecosystem, version
        )

        return {
            "status": "success",
            "message": "Compatibility report submitted",
            "report_id": report_id,
        }
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Invalid report data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to submit compatibility report: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/compare")
@limiter.limit("60/minute")
async def compare_packages(
    request: Request,
    packages: str = Query(
        ..., description="Comma-separated list of package:ecosystem pairs"
    ),
    aspects: Optional[str] = Query(
        "all",
        description="Aspects to compare: all, dependencies, requirements, versions",
    ),
    aggregator: DataAggregator = Depends(get_data_aggregator),
    current_user: User = Depends(get_current_user),
):
    """Compare multiple packages side by side"""
    try:
        logger.info(f"Comparing packages: {packages}")

        package_list = []
        for pkg_str in packages.split(","):
            if ":" in pkg_str:
                name, ecosystem = pkg_str.split(":", 1)
                package_list.append((name.strip(), ecosystem.strip()))
            else:
                # Auto-detect ecosystem
                ecosystem = await _detect_package_ecosystem(pkg_str.strip(), aggregator)
                package_list.append((pkg_str.strip(), ecosystem))

        if len(package_list) > 5:
            raise HTTPException(
                status_code=400, detail="Maximum 5 packages can be compared at once"
            )

        comparison_data = {}
        for name, ecosystem in package_list:
            info = await aggregator.get_package_info(name, ecosystem)
            if info:
                key = f"{name}:{ecosystem}"

                if aspects == "all":
                    comparison_data[key] = info
                else:
                    # Filter to requested aspects
                    comparison_data[key] = _filter_comparison_aspects(info, aspects)

        # Generate comparison summary
        summary = _generate_comparison_summary(comparison_data)

        logger.info(f"Successfully compared {len(comparison_data)} packages")

        return {"status": "success", "comparison": comparison_data, "summary": summary}
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Invalid comparison data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to compare packages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/ecosystems")
@limiter.limit("60/minute")
async def get_supported_ecosystems(
    request: Request, current_user: User = Depends(get_current_user)
):
    """Get list of supported package ecosystems with their capabilities"""
    ecosystems = {
        "pypi": {
            "name": "Python Package Index",
            "language": "Python",
            "package_manager": "pip",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True,
        },
        "npm": {
            "name": "Node Package Manager",
            "language": "JavaScript/TypeScript",
            "package_manager": "npm/yarn",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True,
        },
        "conda": {
            "name": "Conda",
            "language": "Python/Multi",
            "package_manager": "conda",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True,
        },
        "maven": {
            "name": "Maven Central",
            "language": "Java",
            "package_manager": "maven/gradle",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True,
        },
        "crates": {
            "name": "crates.io",
            "language": "Rust",
            "package_manager": "cargo",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True,
        },
        "gomodules": {
            "name": "Go Modules",
            "language": "Go",
            "package_manager": "go mod",
            "supports_search": False,
            "supports_versions": True,
            "supports_dependencies": True,
        },
        "nuget": {
            "name": "NuGet Gallery",
            "language": "C#/.NET",
            "package_manager": "dotnet/nuget",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True,
        },
        "rubygems": {
            "name": "RubyGems",
            "language": "Ruby",
            "package_manager": "gem/bundler",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True,
        },
        "packagist": {
            "name": "Packagist",
            "language": "PHP",
            "package_manager": "composer",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True,
        },
        "cocoapods": {
            "name": "CocoaPods",
            "language": "Objective-C/Swift",
            "package_manager": "cocoapods",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True,
        },
        "homebrew": {
            "name": "Homebrew",
            "language": "System",
            "package_manager": "brew",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True,
        },
        "apt": {
            "name": "Debian/Ubuntu Packages",
            "language": "System",
            "package_manager": "apt/apt-get",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True,
        },
        "apk": {
            "name": "Alpine Linux Packages",
            "language": "System",
            "package_manager": "apk",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True,
        },
    }

    return {"status": "success", "ecosystems": ecosystems, "total": len(ecosystems)}
