import logging
from typing import Dict, List, Optional


from backend.api.helpers.compatibility import (
    _check_python_compatibility,
)

logger = logging.getLogger(__name__)


def _filter_by_python_version(results: List[Dict], python_version: str) -> List[Dict]:
    filtered = []
    for result in results:
        if "python_requires" in result:
            if _check_python_compatibility(python_version, result["python_requires"]):
                filtered.append(result)
        elif "python_versions" in result:
            if any(
                _check_python_compatibility(python_version, f"=={pv}")
                for pv in result["python_versions"]
            ):
                filtered.append(result)
        else:
            filtered.append(result)
    return filtered


def _sort_search_results(results: List[Dict], sort_by: str) -> List[Dict]:
    if not results:
        return results
    if sort_by == "downloads":
        return sorted(results, key=lambda x: x.get("downloads", 0), reverse=True)
    elif sort_by == "name":
        return sorted(results, key=lambda x: x.get("name", "").lower())
    elif sort_by == "updated":
        return sorted(
            results, key=lambda x: x.get("last_updated", "1970-01-01"), reverse=True
        )
    else:
        return results


async def _get_recursive_dependencies(
    source,
    package_name: str,
    version: Optional[str],
    max_depth: int,
    current_depth: int = 0,
    visited: Optional[set] = None,
) -> Dict:
    if visited is None:
        visited = set()
    key = f"{package_name}:{version or 'latest'}"
    if key in visited or current_depth >= max_depth:
        return {
            "name": package_name,
            "version": version or "latest",
            "dependencies": {},
            "circular_reference": key in visited,
        }
    visited.add(key)
    try:
        dependencies = await source.get_dependencies(package_name, version)
    except Exception as e:
        logger.warning(f"Failed to get dependencies for {package_name}: {e}")
        dependencies = {}
    dep_tree = {
        "name": package_name,
        "version": version or "latest",
        "dependencies": {},
    }
    for dep_type, deps in dependencies.items():
        if dep_type not in ["required", "run"]:
            continue
        dep_tree["dependencies"][dep_type] = {}
        for dep_name, dep_spec in deps.items():
            sub_deps = await _get_recursive_dependencies(
                source, dep_name, None, max_depth, current_depth + 1, visited
            )
            dep_tree["dependencies"][dep_type][dep_name] = sub_deps
    return dep_tree


def _count_dependencies(dep_tree: Dict) -> Dict:
    direct = 0
    transitive = 0

    for dep_type, deps in dep_tree.get("dependencies", {}).items():
        for dep_name, sub_tree in deps.items():
            direct += 1
            sub_count = _count_dependencies(sub_tree)
            transitive += sub_count.get("transitive", 0)

    return {"direct": direct, "transitive": transitive, "total": direct + transitive}


def _generate_compatibility_summary(package_info: Dict) -> Dict:
    summary = {
        "python_versions": package_info.get("python_requires", "unknown"),
        "platforms": package_info.get("platforms", []),
        "architectures": package_info.get("architectures", []),
        "cuda_requirements": package_info.get("cuda_versions", []),
        "gpu_required": package_info.get("gpu_required", False),
        "min_python_version": package_info.get("min_python_version", "3.6"),
        "max_python_version": package_info.get("max_python_version", "4.0"),
    }
    return summary


def _extract_version_compatibility(package_info: Dict, version_str: str) -> Dict:
    versions = package_info.get("versions", [])
    for ver in versions:
        if ver.get("version") == version_str:
            return {
                "compatible": True,
                "python_requires": ver.get("python_requires"),
                "published": ver.get("published"),
                "is_yanked": ver.get("yanked", False),
            }
    return {"compatible": False, "reason": f"Version {version_str} not found"}


async def _get_package_metrics(ecosystem: str, package_name: str) -> Dict:
    from datetime import datetime

    logger.debug(f"Getting metrics for {package_name} in {ecosystem}")
    return {
        "downloads": 0,
        "stars": 0,
        "dependents": 0,
        "last_updated": datetime.now().isoformat(),
    }


def _validate_system_info(system_info: Dict) -> bool:
    return "os" in system_info and "python_version" in system_info


async def _analyze_compatibility_reports(
    package_name: str, ecosystem: str, version: str
):
    logger.info(f"Analyzing compatibility reports for {package_name}")


async def _detect_package_ecosystem(package_name: str, aggregator) -> str:
    supported_ecosystems = ["pypi", "npm", "crates", "rubygems", "nuget", "packagist"]
    for eco in supported_ecosystems:
        try:
            source = aggregator.sources.get(eco)
            if source and await source.package_exists(package_name):
                return eco
        except Exception:
            continue
    return "pypi"


def _filter_comparison_aspects(info: Dict, aspects: str) -> Dict:
    aspect_map = {
        "dependencies": ["dependencies", "requirements"],
        "requirements": [
            "python_requires",
            "platforms",
            "architectures",
            "cuda_versions",
        ],
        "versions": ["versions", "latest_version", "version"],
    }
    selected = aspects.split(",") if aspects else list(aspect_map.keys())
    filtered = {}
    for aspect in selected:
        aspect = aspect.strip().lower()
        for key in aspect_map.get(aspect, []):
            if key in info:
                filtered[key] = info[key]
    return filtered


def _generate_comparison_summary(comparison_data: Dict) -> Dict:
    common_deps = None
    all_deps = {}
    for pkg_name, info in comparison_data.items():
        deps = set(info.get("dependencies", {}).keys())
        all_deps[pkg_name] = deps
        if common_deps is None:
            common_deps = deps
        else:
            common_deps = common_deps.intersection(deps)
    return {
        "common_dependencies": list(common_deps) if common_deps else [],
        "conflicts": [],
    }
