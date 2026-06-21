# backend/api/routes/packages.py
from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks, Request
from typing import List, Optional, Dict, Tuple
from pydantic import BaseModel, Field
import asyncio
import re
import logging
from datetime import datetime
from packaging import version
import json

from backend.core.data_aggregator import DataAggregator
from backend.core.conflict_resolver import ConflictResolver
from backend.core.export_generator import ExportGenerator
from backend.database.compatibility_db import CompatibilityDB
from backend.core.system_scanner import SystemScanner

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Import dependencies from main.py
from backend.api.main import (
    get_data_aggregator, 
    get_conflict_resolver,
    get_export_generator,
    get_compatibility_db,
    get_system_scanner,
    limiter,
    PackageRequest,
    ResolveRequest,
    ExportRequest,
    SystemInfo
)

# Keep all your existing models
class PackageSearchRequest(BaseModel):
    query: str
    ecosystems: Optional[List[str]] = None
    limit: int = 20

class PackageVersionInfo(BaseModel):
    version: str
    release_date: Optional[str]
    python_requires: Optional[str]
    size: Optional[int]
    downloads: Optional[int]
    compatible: Optional[bool] = None
    compatibility_notes: Optional[List[str]] = None

class PackageDetailResponse(BaseModel):
    name: str
    ecosystem: str
    description: Optional[str]
    versions: List[PackageVersionInfo]
    latest_version: str
    homepage: Optional[str]
    repository: Optional[str]
    license: Optional[str]
    maintainers: Optional[List[str]]

class SystemSpec(BaseModel):
    os: Optional[str] = Field(None, description="Operating system (linux, windows, macos)")
    os_version: Optional[str] = Field(None, description="OS version")
    architecture: Optional[str] = Field(None, description="CPU architecture (x86_64, arm64)")
    python_version: Optional[str] = Field(None, description="Python version")
    cuda_version: Optional[str] = Field(None, description="CUDA version if available")
    gpu_available: Optional[bool] = Field(False, description="GPU availability")
    
    @classmethod
    def from_string(cls, spec_string: str) -> "SystemSpec":
        """Parse system spec from string format"""
        spec = cls()
        
        # Parse key=value pairs
        parts = spec_string.split(',')
        for part in parts:
            if '=' in part:
                key, value = part.split('=', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if key in ['os', 'operating_system']:
                    spec.os = value.lower()
                elif key == 'os_version':
                    spec.os_version = value
                elif key in ['arch', 'architecture']:
                    spec.architecture = value.lower()
                elif key in ['python', 'python_version', 'py']:
                    spec.python_version = value
                elif key in ['cuda', 'cuda_version']:
                    spec.cuda_version = value
                elif key in ['gpu', 'gpu_available']:
                    spec.gpu_available = value.lower() in ['true', 'yes', '1']
        
        return spec

# MOVED FROM main.py - Get package info endpoint
@router.get("/{ecosystem}/{name}")
@limiter.limit("30/minute")
async def get_package_info(
    request: Request,
    ecosystem: str, 
    name: str, 
    aggregator: DataAggregator = Depends(get_data_aggregator)):
    """Get package information from specified ecosystem"""
    try:
        info = await aggregator.get_package_info(name, ecosystem)
        if not info:
            raise HTTPException(status_code=404, detail=f"Package {name} not found in {ecosystem}")
        return {"status": "success", "data": info}
    except ValueError as e:
        logger.error(f"Invalid package data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Package fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# MOVED FROM main.py - Resolve dependencies endpoint
@router.post("/resolve")
@limiter.limit("10/minute")
async def resolve_dependencies(
    request: Request,
    resolve_request: ResolveRequest,
    scanner: SystemScanner = Depends(get_system_scanner),
    aggregator: DataAggregator = Depends(get_data_aggregator),
    resolver: ConflictResolver = Depends(get_conflict_resolver)):
    """Resolve dependencies for multiple packages"""
    try:
        # Get system info if needed
        system_info = (
            scanner.scan_all()
            if resolve_request.auto_detect_system and not resolve_request.system_info
            else resolve_request.system_info.dict() if resolve_request.system_info else {}
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

# MOVED FROM main.py - Export configuration endpoint
@router.post("/export")
@limiter.limit("20/minute")
async def export_configuration(
    request: Request,
    export_request: ExportRequest,
    generator: ExportGenerator = Depends(get_export_generator)):
    """Export resolved dependencies to various formats"""
    try:
        output = generator.generate(
            export_request.resolved_packages, 
            export_request.format, 
            export_request.system_info, 
            export_request.options
        )
        return {
            "status": "success", 
            "format": export_request.format, 
            "content": output
        }
    except ValueError as e:
        logger.error(f"Invalid export data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# MOVED FROM main.py - Export formats endpoint
@router.get("/export-formats")
@limiter.limit("60/minute")
async def get_export_formats(request: Request):
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
async def search_packages(
    q: str = Query(..., description="Search query"),
    ecosystems: Optional[str] = Query(None, description="Comma-separated list of ecosystems"),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("relevance", description="Sort by: relevance, downloads, name, updated"),
    python_version: Optional[str] = Query(None, description="Filter by Python version compatibility"),
    aggregator: DataAggregator = Depends(get_data_aggregator)):
    """Search for packages across multiple ecosystems"""
    try:
        logger.info(f"Searching for packages: query='{q}', ecosystems={ecosystems}")
        
        # Update search tasks to include all ecosystems
        ecosystem_list = ecosystems.split(',') if ecosystems else None
     
         # Map of ecosystem names to their sources
        available_ecosystems = {
            'pypi': 'pypi',
            'npm': 'npm',
            'conda': 'conda',
            'maven': 'maven',
            'crates': 'crates',
            'gomodules': 'gomodules',
            'apt': 'apt',
            'apk': 'apk',
            'cocoapods': 'cocoapods',
            'rubygems': 'rubygems',
            'packagist': 'packagist',
            'nuget': 'nuget',
            'homebrew': 'homebrew'
        }
        
        # Search in parallel across ecosystems
        search_tasks = []
        ecosystems_to_search = ecosystem_list if ecosystem_list else list(available_ecosystems.keys())
    
        for eco in ecosystems_to_search:
            if eco in available_ecosystems and eco in aggregator.sources:
                source = aggregator.sources[eco]
                if hasattr(source, 'search_packages') or hasattr(source, 'search'):
                    method = 'search_packages' if hasattr(source, 'search_packages') else 'search'
                    search_tasks.append((eco, getattr(source, method)(q, limit)))
        
        results = {}
        for ecosystem, task in search_tasks:
            try:
                ecosystem_results = await asyncio.create_task(task) if asyncio.iscoroutine(task) else task
                
                # Filter by Python version if specified
                if python_version and ecosystem in ['pypi', 'conda']:
                    ecosystem_results = _filter_by_python_version(ecosystem_results, python_version)
                
                # Sort results
                ecosystem_results = _sort_search_results(ecosystem_results, sort_by)
                
                results[ecosystem] = ecosystem_results
                logger.debug(f"Found {len(ecosystem_results)} results in {ecosystem}")
            except Exception as e:
                logger.error(f"Search failed for ecosystem {ecosystem}: {e}")
                results[ecosystem] = {'error': str(e)}
        
        # Calculate total count
        total_count = sum(
            len(r) if isinstance(r, list) else 0 
            for r in results.values()
        )
        
        return {
            "status": "success",
            "query": q,
            "total_count": total_count,
            "results": results,
            "filters_applied": {
                "ecosystems": ecosystem_list,
                "python_version": python_version,
                "sort_by": sort_by
            }
        }
    except ValueError as e:
        logger.error(f"Invalid search parameters: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{ecosystem}/{package_name}")
async def get_package_details(
    ecosystem: str, 
    package_name: str,
    include_metrics: bool = Query(False, description="Include download and usage metrics"),
    aggregator: DataAggregator = Depends(get_data_aggregator)):
    """Get detailed information about a specific package"""
    try:
        logger.info(f"Getting package details: {ecosystem}/{package_name}")
        
        package_info = await aggregator.get_package_info(package_name, ecosystem)
        
        if not package_info or ecosystem not in package_info.get('ecosystems', {}):
            logger.warning(f"Package not found: {ecosystem}/{package_name}")
            raise HTTPException(status_code=404, detail=f"Package {package_name} not found in {ecosystem}")
        
        ecosystem_data = package_info['ecosystems'][ecosystem]
        
        # Add metrics if requested
        if include_metrics:
            logger.debug(f"Fetching metrics for {ecosystem}/{package_name}")
            metrics = await _get_package_metrics(ecosystem, package_name)
            ecosystem_data['metrics'] = metrics
        
        # Add compatibility summary
        compatibility_summary = _generate_compatibility_summary(package_info)
        
        return {
            "status": "success",
            "data": {
                "name": package_name,
                "ecosystem": ecosystem,
                "info": ecosystem_data,
                "compatibility_matrix": package_info.get('compatibility_matrix', {}),
                "system_requirements": package_info.get('system_requirements', {}),
                "compatibility_summary": compatibility_summary
            }
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
async def get_package_versions(
    ecosystem: str, 
    package_name: str,
    compatible_with: Optional[str] = Query(None, description="Filter versions compatible with system (e.g., 'os=linux,python=3.9,cuda=11.2')"),
    include_yanked: bool = Query(False, description="Include yanked/deprecated versions"),
    include_prerelease: bool = Query(False, description="Include pre-release versions"),
    aggregator: DataAggregator = Depends(get_data_aggregator)):
    """Get all available versions of a package"""
    try:
        logger.info(f"Getting versions for: {ecosystem}/{package_name}")
        
        if ecosystem not in aggregator.sources:
            raise HTTPException(status_code=400, detail=f"Unknown ecosystem: {ecosystem}")
        
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
            if not include_yanked and v.get('yanked', False):
                continue
            
            # Skip pre-release versions if not requested
            if not include_prerelease and _is_prerelease(v.get('version', '')):
                continue
            
            # Check compatibility if system spec provided
            if system_spec:
                is_compatible, notes = _check_version_compatibility_detailed(v, system_spec)
                v['compatible'] = is_compatible
                v['compatibility_notes'] = notes
                
                # Only include compatible versions unless explicitly showing all
                if not is_compatible and compatible_with:
                    continue
            
            filtered_versions.append(v)
        
        # Sort versions (newest first)
        filtered_versions.sort(
            key=lambda x: version.parse(x.get('version', '0.0.0')),
            reverse=True
        )
        
        logger.info(f"Found {len(filtered_versions)}/{len(versions)} versions after filtering")
        
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
                "include_prerelease": include_prerelease
            }
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
async def get_package_dependencies(
    ecosystem: str,
    package_name: str,
    version: Optional[str] = Query(None, description="Specific version to check"),
    recursive: bool = Query(False, description="Get dependencies recursively"),
    max_depth: int = Query(3, ge=1, le=5, description="Maximum recursion depth"),
    aggregator: DataAggregator = Depends(get_data_aggregator)):
    """Get dependencies for a specific package version"""
    try:
        logger.info(f"Getting dependencies for: {ecosystem}/{package_name}@{version or 'latest'}")
        
        if ecosystem not in aggregator.sources:
            raise HTTPException(status_code=400, detail=f"Unknown ecosystem: {ecosystem}")
        
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
                "total_dependencies": _count_dependencies(dep_tree)
            }
        else:
            # Get direct dependencies only
            dependencies = await source.get_dependencies(package_name, version)
            
            return {
                "status": "success",
                "package": package_name,
                "version": version or "latest",
                "dependencies": dependencies
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
async def get_package_compatibility(
    ecosystem: str, 
    package_name: str,
    version: Optional[str] = Query(None, description="Specific version to check"),
    compatibility_db: CompatibilityDB = Depends(get_compatibility_db),
    aggregator: DataAggregator = Depends(get_data_aggregator)):
    """Get known compatibility information for a package"""
    try:
        logger.info(f"Getting compatibility info for: {ecosystem}/{package_name}@{version or 'latest'}")
        
        # Get from custom database
        db_compatibility = compatibility_db.get_compatibility_rules(package_name)
        
        # Get from package metadata
        package_info = await aggregator.get_package_info(package_name, ecosystem)
        
        # Get version-specific compatibility if version specified
        version_compatibility = {}
        if version and package_info:
            version_compatibility = _extract_version_compatibility(package_info, version)
        
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
                "known_conflicts": db_compatibility.get('known_conflicts', []),
                "verified_combinations": db_compatibility.get('verified_combinations', []),
                "system_requirements": package_info.get('system_requirements', {}),
                "version_specific": version_compatibility,
                "community_reports": db_compatibility.get('community_reports', []),
                "statistics": community_stats
            }
        }
    except ValueError as e:
        logger.error(f"Invalid compatibility data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get compatibility info: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{ecosystem}/{package_name}/compatibility/report")
async def report_compatibility(
    ecosystem: str,
    package_name: str,
    version: str,
    system_info: Dict,
    works: bool,
    notes: Optional[str] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    compatibility_db: CompatibilityDB = Depends(get_compatibility_db)):
    """Submit a compatibility report"""
    try:
        logger.info(f"Receiving compatibility report for: {ecosystem}/{package_name}@{version}")
        
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
            notes=notes
        )
        
        logger.info(f"Compatibility report saved with ID: {report_id}")
        
        # Background task to analyze and aggregate reports
        background_tasks.add_task(
            _analyze_compatibility_reports,
            package_name, ecosystem, version
        )
        
        return {
            "status": "success",
            "message": "Compatibility report submitted",
            "report_id": report_id
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
async def compare_packages(
    packages: str = Query(..., description="Comma-separated list of package:ecosystem pairs"),
    aspects: Optional[str] = Query("all", description="Aspects to compare: all, dependencies, requirements, versions"),
    aggregator: DataAggregator = Depends(get_data_aggregator)):
    """Compare multiple packages side by side"""
    try:
        logger.info(f"Comparing packages: {packages}")
        
        package_list = []
        for pkg_str in packages.split(','):
            if ':' in pkg_str:
                name, ecosystem = pkg_str.split(':', 1)
                package_list.append((name.strip(), ecosystem.strip()))
            else:
                # Auto-detect ecosystem
                ecosystem = await _detect_package_ecosystem(pkg_str.strip(), aggregator)
                package_list.append((pkg_str.strip(), ecosystem))
        
        if len(package_list) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 packages can be compared at once")
        
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
        
        return {
            "status": "success",
            "comparison": comparison_data,
            "summary": summary
        }
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Invalid comparison data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to compare packages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Helper functions
def _check_version_compatibility(version_info: Dict, system_spec: str) -> bool:
    """Check if a version is compatible with system specification"""
    try:
        spec = SystemSpec.from_string(system_spec)
        is_compatible, _ = _check_version_compatibility_detailed(version_info, spec)
        return is_compatible
    except Exception:
        return True  # Default to compatible if parsing fails

def _check_version_compatibility_detailed(version_info: Dict, 
                                        system_spec: SystemSpec) -> Tuple[bool, List[str]]:
    """Check version compatibility with detailed notes"""
    compatibility_notes = []
    is_compatible = True
    
    # Check Python version compatibility
    if system_spec.python_version and version_info.get('python_requires'):
        python_requires = version_info['python_requires']
        if not _check_python_compatibility(system_spec.python_version, python_requires):
            is_compatible = False
            compatibility_notes.append(
                f"Requires Python {python_requires}, but system has {system_spec.python_version}"
            )
    
    # Check OS compatibility
    if system_spec.os and version_info.get('platforms'):
        platforms = version_info['platforms']
        if not _check_os_compatibility(system_spec.os, platforms):
            is_compatible = False
            compatibility_notes.append(
                f"Not available for {system_spec.os} (supports: {', '.join(platforms)})"
            )
    
    # Check architecture compatibility
    if system_spec.architecture and version_info.get('architectures'):
        architectures = version_info['architectures']
        if system_spec.architecture not in architectures:
            is_compatible = False
            compatibility_notes.append(
                f"Not available for {system_spec.architecture} architecture"
            )
    
    # Check CUDA compatibility
    if system_spec.cuda_version and version_info.get('cuda_required'):
        cuda_versions = version_info.get('cuda_versions', [])
        if cuda_versions and not _check_cuda_compatibility(system_spec.cuda_version, cuda_versions):
            is_compatible = False
            compatibility_notes.append(
                f"Requires CUDA {', '.join(cuda_versions)}, but system has {system_spec.cuda_version}"
            )
    elif not system_spec.gpu_available and version_info.get('gpu_required'):
        is_compatible = False
        compatibility_notes.append("Requires GPU but none available")
    
    # Check for yanked versions
    if version_info.get('yanked'):
        compatibility_notes.append("This version has been yanked by maintainers")
    
    return is_compatible, compatibility_notes

def _check_python_compatibility(system_python: str, requires_python: str) -> bool:
    """Check if system Python version satisfies requirement"""
    try:
        from packaging.specifiers import SpecifierSet
        
        spec = SpecifierSet(requires_python)
        system_version = version.parse(system_python)
        
        return system_version in spec
    except Exception as e:
        logger.warning(f"Failed to check Python compatibility: {e}")
        return True  # Default to compatible if parsing fails

def _check_os_compatibility(system_os: str, supported_platforms: List[str]) -> bool:
    """Check if OS is supported"""
    if not supported_platforms or 'any' in supported_platforms:
        return True
    
    os_mapping = {
        'linux': ['linux', 'manylinux', 'unix', 'posix'],
        'windows': ['windows', 'win', 'win32', 'win_amd64'],
        'macos': ['macos', 'darwin', 'osx', 'mac'],
        'darwin': ['macos', 'darwin', 'osx', 'mac']
    }
    
    system_aliases = os_mapping.get(system_os.lower(), [system_os.lower()])
    
    for platform in supported_platforms:
        platform_lower = platform.lower()
        if any(alias in platform_lower for alias in system_aliases):
            return True
    
    return False

def _check_cuda_compatibility(system_cuda: str, required_cuda: List[str]) -> bool:
    """Check if system CUDA version satisfies requirements"""
    try:
        system_version = version.parse(system_cuda)
        
        for req_cuda in required_cuda:
            # Handle different formats: "11.2", ">=11.0", "11.x"
            if req_cuda.endswith('.x'):
                # Match major version
                req_major = int(req_cuda[:-2])
                if system_version.major == req_major:
                    return True
            elif any(op in req_cuda for op in ['>=', '<=', '>', '<', '==']):
                # Parse as specifier
                from packaging.specifiers import SpecifierSet
                spec = SpecifierSet(req_cuda.replace('cuda', '').strip())
                if system_version in spec:
                    return True
            else:
                # Exact match
                req_version = version.parse(req_cuda)
                if system_version == req_version:
                    return True
        
        return False
    except Exception as e:
        logger.warning(f"Failed to check CUDA compatibility: {e}")
        return True  # Default to compatible if parsing fails

def _is_prerelease(version_str: str) -> bool:
    """Check if version is a pre-release"""
    try:
        v = version.parse(version_str)
        return v.is_prerelease
    except:
        # Check common pre-release patterns
        prerelease_indicators = ['alpha', 'beta', 'rc', 'dev', 'pre', 'a', 'b']
        version_lower = version_str.lower()
        return any(indicator in version_lower for indicator in prerelease_indicators)

def _filter_by_python_version(results: List[Dict], python_version: str) -> List[Dict]:
    """Filter search results by Python version compatibility"""
    filtered = []
    
    for result in results:
        # Check if result has Python version info
        if 'python_requires' in result:
            if _check_python_compatibility(python_version, result['python_requires']):
                filtered.append(result)
        elif 'python_versions' in result:
            # Check if any supported version matches
            if any(_check_python_compatibility(python_version, f"=={pv}") 
                   for pv in result['python_versions']):
                filtered.append(result)
        else:
            # No Python version info, include by default
            filtered.append(result)
    
    return filtered

def _sort_search_results(results: List[Dict], sort_by: str) -> List[Dict]:
    """Sort search results by specified criteria"""
    if not results:
        return results
    
    if sort_by == 'downloads':
        return sorted(results, key=lambda x: x.get('downloads', 0), reverse=True)
    elif sort_by == 'name':
        return sorted(results, key=lambda x: x.get('name', '').lower())
    elif sort_by == 'updated':
        return sorted(results, 
                     key=lambda x: x.get('last_updated', '1970-01-01'), 
                     reverse=True)
    else:  # relevance (default)
        # Assume results are already sorted by relevance from search
        return results

async def _get_recursive_dependencies(source, package_name: str, 
                                    version: Optional[str], 
                                    max_depth: int, 
                                    current_depth: int = 0,
                                    visited: Optional[set] = None) -> Dict:
    """Recursively get package dependencies"""
    if visited is None:
        visited = set()
    
    # Avoid circular dependencies
    key = f"{package_name}:{version or 'latest'}"
    if key in visited or current_depth >= max_depth:
        return {
            "name": package_name,
            "version": version or "latest",
            "dependencies": {},
            "circular_reference": key in visited
        }
    
    visited.add(key)
    
    # Get direct dependencies
    try:
        dependencies = await source.get_dependencies(package_name, version)
    except Exception as e:
        logger.warning(f"Failed to get dependencies for {package_name}: {e}")
        dependencies = {}
    
    # Build dependency tree
    dep_tree = {
        "name": package_name,
        "version": version or "latest",
        "dependencies": {}
    }
    
    # Recursively get dependencies for each dependency
    for dep_type, deps in dependencies.items():
        if dep_type not in ['required', 'run']:  # Focus on runtime dependencies
            continue
            
        dep_tree["dependencies"][dep_type] = {}
        
        for dep_name, dep_spec in deps.items():
            # For simplicity, don't resolve exact versions here
            sub_deps = await _get_recursive_dependencies(
                source, dep_name, None, max_depth, current_depth + 1, visited
            )
            dep_tree["dependencies"][dep_type][dep_name] = sub_deps
    
    return dep_tree

def _count_dependencies(dep_tree: Dict) -> Dict:
    """Count total dependencies in tree"""
    direct = 0
    transitive = 0
    
    def count_recursive(node, depth=0):
        nonlocal direct, transitive
        
        for dep_type, deps in node.get("dependencies", {}).items():
            for dep_name, dep_node in deps.items():
                if depth == 0:
                    direct += 1
                else:
                    transitive += 1
                count_recursive(dep_node, depth + 1)
    
    count_recursive(dep_tree)
    
    return {
        "direct": direct,
        "transitive": transitive,
        "total": direct + transitive
    }

def _generate_compatibility_summary(package_info: Dict) -> Dict:
    """Generate a compatibility summary from package info"""
    summary = {
        "python_versions": [],
        "operating_systems": [],
        "architectures": [],
        "special_requirements": []
    }
    
    # Extract from system requirements
    sys_reqs = package_info.get('system_requirements', {})
    
    if 'python' in sys_reqs:
        summary['python_versions'] = sys_reqs['python'].get('supported_versions', [])
    
    if 'os' in sys_reqs:
        summary['operating_systems'] = sys_reqs['os'].get('supported', [])
    
    if 'architecture' in sys_reqs:
        summary['architectures'] = sys_reqs['architecture'].get('supported', [])
    
    # Special requirements
    if sys_reqs.get('gpu', {}).get('required'):
        summary['special_requirements'].append('GPU required')
        if sys_reqs['gpu'].get('cuda_versions'):
            summary['special_requirements'].append(
                f"CUDA {', '.join(sys_reqs['gpu']['cuda_versions'])}"
            )
    
    return summary

def _extract_version_compatibility(package_info: Dict, version: str) -> Dict:
    """Extract compatibility info for a specific version"""
    compatibility_matrix = package_info.get('compatibility_matrix', {})
    
    if version in compatibility_matrix:
        return compatibility_matrix[version]
    
    # Try to find in versions list
    for ecosystem_data in package_info.get('ecosystems', {}).values():
        for version_info in ecosystem_data.get('versions', []):
            if version_info.get('version') == version:
                return {
                    'python': version_info.get('python_versions', []),
                    'platforms': version_info.get('platforms', [])
                }
    
    return {}

async def _get_package_metrics(ecosystem: str, package_name: str) -> Dict:
    """Get package usage metrics"""
    logger.debug(f"Fetching metrics for {ecosystem}/{package_name}")
    # This would fetch real metrics from analytics services
    # For now, returning placeholder data
    return {
        "downloads": {
            "last_day": 0,
            "last_week": 0,
            "last_month": 0
        },
        "stars": 0,
        "dependents": 0,
        "last_updated": datetime.now().isoformat()
    }

def _validate_system_info(system_info: Dict) -> bool:
    """Validate system info structure"""
    required_fields = ['os', 'python_version']
    return all(field in system_info for field in required_fields)

async def _analyze_compatibility_reports(package_name: str, 
                                       ecosystem: str, 
                                       version: str):
    """Background task to analyze compatibility reports"""
    logger.info(f"Analyzing compatibility reports for {ecosystem}/{package_name}@{version}")
    # This would aggregate reports and update compatibility statistics
    # Implementation would involve:
    # 1. Fetching all reports for this package/version
    # 2. Identifying patterns in success/failure
    # 3. Updating compatibility rules and statistics
    pass

async def _detect_package_ecosystem(package_name: str, aggregator: DataAggregator) -> str:
    """Auto-detect package ecosystem"""
    logger.debug(f"Auto-detecting ecosystem for package: {package_name}")
    
    # Check all available ecosystems
    all_ecosystems = [
        'pypi', 'npm', 'conda', 'maven', 'crates', 
        'gomodules', 'apt', 'apk', 'cocoapods', 
        'rubygems', 'packagist', 'nuget', 'homebrew'
    ]

    # Check each ecosystem for the package
    for ecosystem in all_ecosystems:
        if ecosystem in aggregator.sources:
            source = aggregator.sources[ecosystem]
            try:
                if hasattr(source, 'package_exists'):
                    exists = await source.package_exists(package_name)
                    if exists:
                        logger.info(f"Package {package_name} found in {ecosystem}")
                        return ecosystem
            except Exception as e:
                logger.warning(f"Failed to check {ecosystem} for {package_name}: {e}")
    
    logger.info(f"Package {package_name} not found, defaulting to PyPI")
    return 'pypi'  # Default to PyPI

@router.get("/ecosystems")
@limiter.limit("60/minute")
async def get_supported_ecosystems(request: Request):
    """Get list of supported package ecosystems with their capabilities"""
    ecosystems = {
        "pypi": {
            "name": "Python Package Index",
            "language": "Python",
            "package_manager": "pip",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True
        },
        "npm": {
            "name": "Node Package Manager",
            "language": "JavaScript/TypeScript",
            "package_manager": "npm/yarn",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True
        },
        "gomodules": {
            "name": "Go Modules",
            "language": "Go",
            "package_manager": "go mod",
            "supports_search": False,  # Limited search capability
            "supports_versions": True,
            "supports_dependencies": True
        },
        "apt": {
            "name": "Debian/Ubuntu Packages",
            "language": "System",
            "package_manager": "apt/apt-get",
            "supports_search": True,
            "supports_versions": True,
            "supports_dependencies": True
        },
        # Add other ecosystems...
    }
    
    return {
        "status": "success",
        "ecosystems": ecosystems,
        "total": len(ecosystems)
    }


def _filter_comparison_aspects(info: Dict, aspects: str) -> Dict:
    """Filter package info to requested comparison aspects"""
    aspects_list = aspects.split(',')
    filtered = {}
    
    aspect_mapping = {
        'dependencies': ['ecosystems.*.dependencies'],
        'requirements': ['system_requirements', 'compatibility_matrix'],
        'versions': ['ecosystems.*.versions', 'ecosystems.*.latest_version']
    }
    
    for aspect in aspects_list:
        if aspect in aspect_mapping:
            for path in aspect_mapping[aspect]:
                # Simple path extraction (would be more complex in production)
                if '.' not in path:
                    if path in info:
                        filtered[path] = info[path]
    
    return filtered

def _generate_comparison_summary(comparison_data: Dict) -> Dict:
    """Generate summary of package comparison"""
    summary = {
        "common_dependencies": [],
        "conflicting_requirements": [],
        "compatibility_overlap": {}
    }
    
    # Find common dependencies
    all_deps = []
    for pkg_data in comparison_data.values():
        deps = set()
        for eco_data in pkg_data.get('ecosystems', {}).values():
            for dep_dict in eco_data.get('dependencies', {}).values():
                deps.update(dep_dict.keys())
        all_deps.append(deps)
    
    if all_deps:
        summary['common_dependencies'] = list(set.intersection(*all_deps))
    
    return summary