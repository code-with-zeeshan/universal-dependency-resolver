"""Module docstring."""

# compatibility_db.py
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.core._json import dumps

from ..core.utils import (
    hash_system_info,
    normalize_package_name,
    parse_version,
    sanitize_ecosystem_name,
)
from .models import (
    CompatibilityReport,
    ConflictRule,
    Package,
    PackageVersion,
    ResolutionCache,
    SystemBenchmark,
    VerifiedCombination,
    get_db,
    init_db,
)

logger = logging.getLogger(__name__)


class CompatibilityDB:
    def __init__(self):
        init_db()

    def add_package(self, name: str, ecosystem: str, info: dict) -> int:
        """Add or update package information."""
        # Normalize inputs
        name = normalize_package_name(name)
        ecosystem = sanitize_ecosystem_name(ecosystem)

        db = next(get_db())
        try:
            # Check if package exists
            package = (
                db.query(Package)
                .filter(and_(Package.name == name, Package.ecosystem == ecosystem))
                .first()
            )

            if not package:
                package = Package(
                    name=name,
                    ecosystem=ecosystem,
                    latest_version=info.get("version"),
                    description=info.get("description"),
                    homepage=info.get("homepage"),
                    repository=info.get("repository"),
                    license=info.get("license"),
                )
                db.add(package)
            else:
                # Update existing package
                package.latest_version = info.get("version", package.latest_version)
                package.description = info.get("description", package.description)
                package.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(package)

            # Add versions
            for version_info in info.get("versions", []):
                self._add_package_version(db, package.id, version_info)

            return package.id

        except Exception as e:
            logger.error(f"Error adding package {name}: {e}")
            db.rollback()
            raise
        finally:
            db.close()

    def _add_package_version(self, db: Session, package_id: int, version_info: dict):
        """Add package version information."""
        version_str = version_info.get("version")

        # Validate version
        if not version_str or not parse_version(version_str):
            logger.warning(f"Invalid version: {version_str}")
            return

        version = (
            db.query(PackageVersion)
            .filter(
                and_(
                    PackageVersion.package_id == package_id,
                    PackageVersion.version == version_str,
                )
            )
            .first()
        )

        if not version:
            version = PackageVersion(
                package_id=package_id,
                version=version_str,
                release_date=version_info.get("release_date"),
                python_requires=version_info.get("python_requires"),
                size_bytes=version_info.get("size"),
                system_requirements=version_info.get("system_requirements", {}),
                dependencies=version_info.get("dependencies", {}),
                metadata_json=version_info.get("metadata", {}),
            )
            db.add(version)
            db.commit()

    def _extract_system_fields(self, system_info: dict) -> dict:
        """Extract flat fields from nested system_info structure."""
        platform = system_info.get("platform", {})
        cpu = system_info.get("cpu", {})
        gpu = system_info.get("gpu", {})
        runtime = system_info.get("runtime_versions", {})

        # Handle different possible structures for GPU info
        gpu_name = None
        cuda_version = None
        cudnn_version = None

        if gpu.get("available"):
            devices = gpu.get("devices", [])
            if devices and isinstance(devices[0], dict):
                gpu_name = devices[0].get("name")

            # CUDA info might be nested or flat
            cuda_info = gpu.get("cuda")
            if isinstance(cuda_info, dict):
                cuda_version = cuda_info.get("version")
                cudnn_info = cuda_info.get("cudnn")
                if isinstance(cudnn_info, dict):
                    cudnn_version = cudnn_info.get("version")
            elif isinstance(cuda_info, str):
                cuda_version = cuda_info

        # Extract Python version
        python_version = None
        python_info = runtime.get("python", {})
        if isinstance(python_info, dict):
            python_version = python_info.get("version")

        return {
            "os_name": platform.get("system"),
            "os_version": platform.get("release"),
            "cpu_architecture": cpu.get("architecture") or cpu.get("arch"),
            "gpu_name": gpu_name,
            "cuda_version": cuda_version,
            "cudnn_version": cudnn_version,
            "python_version": python_version,
        }

    def add_compatibility_report(
        self,
        package_name: str,
        version: str,
        ecosystem: str,
        system_info: dict,
        works: bool,
        notes: str | None = None,
        user_id: str | None = None,
    ) -> int:
        """Add a compatibility report from user."""
        # Normalize inputs
        package_name = normalize_package_name(package_name)
        ecosystem = sanitize_ecosystem_name(ecosystem)

        db = next(get_db())
        try:
            # Find or create package
            package = (
                db.query(Package)
                .filter(and_(Package.name == package_name, Package.ecosystem == ecosystem))
                .first()
            )

            if not package:
                package = Package(name=package_name, ecosystem=ecosystem)
                db.add(package)
                db.commit()
                db.refresh(package)

            # Extract system fields
            sys_fields = self._extract_system_fields(system_info)

            # Create report
            report = CompatibilityReport(
                package_id=package.id,
                version=version,
                os_name=sys_fields["os_name"],
                os_version=sys_fields["os_version"],
                cpu_architecture=sys_fields["cpu_architecture"],
                gpu_name=sys_fields["gpu_name"],
                cuda_version=sys_fields["cuda_version"],
                cudnn_version=sys_fields["cudnn_version"],
                python_version=sys_fields["python_version"],
                system_info=system_info,
                works=works,
                notes=notes,
                user_id=user_id,
            )

            db.add(report)
            db.commit()

            return int(report.id)

        except Exception as e:
            logger.error(f"Error adding compatibility report: {e}")
            db.rollback()
            raise
        finally:
            db.close()

    def get_compatibility_rules(self, package_name: str) -> dict:
        """Get compatibility rules for a package."""
        # Normalize package name
        package_name = normalize_package_name(package_name)

        db = next(get_db())
        try:
            # Find package
            package = db.query(Package).filter(Package.name == package_name).first()
            if not package:
                return {
                    "known_conflicts": [],
                    "verified_combinations": [],
                    "community_reports": {},
                }

            # Get conflict rules
            conflicts = (
                db.query(ConflictRule)
                .filter(
                    or_(
                        ConflictRule.package1_id == package.id,
                        ConflictRule.package2_id == package.id,
                    )
                )
                .all()
            )

            # Get verified combinations
            verified = (
                db.query(VerifiedCombination)
                .filter(VerifiedCombination.packages.contains([{"name": package_name}]))
                .all()
            )

            # Get community reports
            reports = (
                db.query(CompatibilityReport)
                .filter(CompatibilityReport.package_id == package.id)
                .order_by(CompatibilityReport.created_at.desc())
                .limit(100)
                .all()
            )

            # Aggregate results
            return {
                "known_conflicts": [self._serialize_conflict(c, package.id) for c in conflicts],
                "verified_combinations": [self._serialize_combination(v) for v in verified],
                "community_reports": self._aggregate_reports(reports),
            }

        finally:
            db.close()

    def get_package_by_normalized_name(self, name: str, ecosystem: str) -> Package | None:
        """Get package using normalized name."""
        name = normalize_package_name(name)
        ecosystem = sanitize_ecosystem_name(ecosystem)

        db = next(get_db())
        try:
            return (
                db.query(Package)
                .filter(and_(Package.name == name, Package.ecosystem == ecosystem))
                .first()
            )
        finally:
            db.close()

    def bulk_import_packages(self, packages: list[dict]) -> int:
        """Bulk import packages with normalization."""
        imported = 0
        for pkg in packages:
            try:
                name = normalize_package_name(pkg.get("name", ""))
                ecosystem = sanitize_ecosystem_name(pkg.get("ecosystem", ""))
                if name and ecosystem:
                    self.add_package(name, ecosystem, pkg)
                    imported += 1
            except Exception as e:
                logger.error(f"Failed to import {pkg.get('name')}: {e}")
        return imported

    def check_version_compatibility(
        self, package_name: str, version: str, system_info: dict
    ) -> dict:
        """Check if a specific version is compatible with system."""
        package_name = normalize_package_name(package_name)

        db = next(get_db())
        try:
            # Get package
            package = self.get_package_by_normalized_name(package_name, "pypi")  # Default to pypi
            if not package:
                return {
                    "compatible": True,
                    "confidence": 0.0,
                    "similar_systems": 0,
                    "warnings": ["Package not found in compatibility database"],
                }

            # Extract system fields for comparison
            sys_fields = self._extract_system_fields(system_info)

            # Find similar system reports
            similar_reports = (
                db.query(CompatibilityReport)
                .filter(
                    and_(
                        CompatibilityReport.package_id == package.id,
                        CompatibilityReport.version == version,
                        CompatibilityReport.os_name == sys_fields["os_name"],
                        CompatibilityReport.python_version == sys_fields["python_version"],
                    )
                )
                .all()
            )

            if not similar_reports:
                return {
                    "compatible": True,
                    "confidence": 0.1,
                    "similar_systems": 0,
                    "warnings": ["No compatibility data for this configuration"],
                }

            # Calculate compatibility score
            successful = sum(1 for r in similar_reports if r.works)
            success_rate = successful / len(similar_reports)

            return {
                "compatible": success_rate >= 0.8,
                "confidence": min(
                    success_rate, len(similar_reports) / 10.0
                ),  # Confidence increases with more data
                "similar_systems": len(similar_reports),
                "success_rate": success_rate,
                "warnings": self._extract_warnings_from_reports(similar_reports),
            }

        finally:
            db.close()

    def _extract_warnings_from_reports(self, reports: list[CompatibilityReport]) -> list[str]:
        """Extract common warnings from failed reports."""
        warnings = []
        failed_reports = [r for r in reports if not r.works and r.notes]

        if failed_reports:
            # Extract common patterns
            common_issues: dict[str, int] = {}
            for report in failed_reports:
                if "cuda" in report.notes.lower():
                    common_issues["cuda"] = common_issues.get("cuda", 0) + 1
                if "memory" in report.notes.lower():
                    common_issues["memory"] = common_issues.get("memory", 0) + 1
                if "version" in report.notes.lower():
                    common_issues["version"] = common_issues.get("version", 0) + 1

            # Convert to warnings
            for issue, count in common_issues.items():
                if count >= len(failed_reports) * 0.3:  # If 30% or more mention this
                    warnings.append(f"Common issue: {issue} (reported by {count} users)")

        return warnings

    def get_package_stats(self, package_name: str) -> dict:
        """Get aggregated statistics for a package."""
        package_name = normalize_package_name(package_name)

        db = next(get_db())
        try:
            package = self.get_package_by_normalized_name(package_name, "pypi")
            if not package:
                return {"error": "Package not found"}

            # Get all reports
            reports = (
                db.query(CompatibilityReport)
                .filter(CompatibilityReport.package_id == package.id)
                .all()
            )

            # Get version count
            versions = (
                db.query(PackageVersion).filter(PackageVersion.package_id == package.id).count()
            )

            # Calculate stats
            total_reports = len(reports)
            successful_reports = sum(1 for r in reports if r.works)

            # Group by version
            version_stats: dict[str, dict[str, Any]] = {}
            for report in reports:
                if report.version not in version_stats:
                    version_stats[report.version] = {
                        "total": 0,
                        "successful": 0,
                        "systems": set(),
                    }

                version_stats[report.version]["total"] += 1
                if report.works:
                    version_stats[report.version]["successful"] += 1

                system_key = f"{report.os_name}_{report.python_version}"
                version_stats[report.version]["systems"].add(system_key)

            # Find most compatible version
            most_compatible = None
            highest_success_rate = 0

            for version, stats in version_stats.items():
                success_rate = stats["successful"] / stats["total"]
                if success_rate > highest_success_rate and stats["total"] >= 5:  # Min 5 reports
                    highest_success_rate = success_rate
                    most_compatible = version

            return {
                "package_name": package.name,
                "ecosystem": package.ecosystem,
                "total_versions": versions,
                "total_reports": total_reports,
                "overall_success_rate": successful_reports / total_reports
                if total_reports > 0
                else 0,
                "most_compatible_version": most_compatible,
                "version_stats": {
                    v: {
                        "success_rate": s["successful"] / s["total"],
                        "report_count": s["total"],
                        "system_diversity": len(s["systems"]),
                    }
                    for v, s in version_stats.items()
                },
            }

        finally:
            db.close()

    def get_compatibility_statistics(
        self, package_name: str, ecosystem: str, version: str | None = None
    ) -> dict:
        """Get compatibility statistics filtered by ecosystem and optional version."""
        stats = self.get_package_stats(package_name)
        if "error" in stats:
            return {"reports_count": 0, "success_rate": None, "version": version}
        return {
            "reports_count": stats.get("total_reports", 0),
            "success_rate": stats.get("overall_success_rate"),
            "most_compatible_version": stats.get("most_compatible_version"),
            "version": version,
        }

    def cleanup_old_cache(self, days: int = 7):
        """Remove old cache entries."""
        db = next(get_db())
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            deleted = db.query(ResolutionCache).filter(ResolutionCache.created_at < cutoff).delete()
            db.commit()
            logger.info(f"Cleaned up {deleted} old cache entries")
        except Exception as e:
            logger.error(f"Error cleaning cache: {e}")
            db.rollback()
        finally:
            db.close()

    def _serialize_conflict(self, conflict: ConflictRule, package_id: int) -> dict:
        """Serialize conflict rule."""
        is_package1 = conflict.package1_id == package_id

        return {
            "conflicting_package": conflict.package2.name
            if is_package1
            else conflict.package1.name,
            "version_spec": conflict.package2_version_spec
            if is_package1
            else conflict.package1_version_spec,
            "type": conflict.conflict_type,
            "severity": conflict.severity,
            "description": conflict.description,
            "resolution": conflict.resolution,
        }

    def _serialize_combination(self, combination: VerifiedCombination) -> dict:
        """Serialize verified combination."""
        return {
            "name": combination.name,
            "description": combination.description,
            "packages": combination.packages,
            "system_requirements": combination.system_requirements,
            "verified_by": combination.verified_by,
            "verification_date": combination.verification_date.isoformat()
            if combination.verification_date
            else None,
            "usage_count": combination.usage_count,
            "success_rate": combination.success_rate,
        }

    def _aggregate_reports(self, reports: list[CompatibilityReport]) -> dict:
        """Aggregate compatibility reports."""
        aggregated = {
            "total_reports": len(reports),
            "success_rate": 0,
            "by_version": {},
            "by_system": {},
            "common_issues": [],
        }

        if not reports:
            return aggregated

        # Calculate success rate
        successful = sum(1 for r in reports if r.works)
        aggregated["success_rate"] = successful / len(reports)

        # Group by version
        version_stats = {}
        for report in reports:
            if report.version not in version_stats:
                version_stats[report.version] = {"success": 0, "total": 0}

            version_stats[report.version]["total"] += 1
            if report.works:
                version_stats[report.version]["success"] += 1

        aggregated["by_version"] = {
            v: {
                "success_rate": stats["success"] / stats["total"],
                "reports": stats["total"],
            }
            for v, stats in version_stats.items()
        }

        # Group by system configuration
        system_stats = {}
        for report in reports:
            key = f"{report.os_name}_{report.python_version}_{report.cuda_version or 'no_cuda'}"
            if key not in system_stats:
                system_stats[key] = {"success": 0, "total": 0}

            system_stats[key]["total"] += 1
            if report.works:
                system_stats[key]["success"] += 1

        aggregated["by_system"] = system_stats

        # Extract common issues from failed reports
        failed_reports = [r for r in reports if not r.works and r.notes]
        if failed_reports:
            # Simple keyword extraction
            issue_keywords: dict[str, int] = {}
            for report in failed_reports:
                words = report.notes.lower().split()
                for word in [
                    "cuda",
                    "cudnn",
                    "version",
                    "incompatible",
                    "missing",
                    "error",
                ]:
                    if word in words:
                        issue_keywords[word] = issue_keywords.get(word, 0) + 1

            aggregated["common_issues"] = [
                {"keyword": k, "frequency": v}
                for k, v in sorted(issue_keywords.items(), key=lambda x: x[1], reverse=True)[:5]
            ]

        return aggregated

    def add_conflict_rule(
        self,
        package1: str,
        package1_version: str,
        package2: str,
        package2_version: str,
        conflict_type: str,
        description: str,
        severity: str = "error",
        resolution: str | None = None,
    ):
        """Add a known conflict rule."""
        # Normalize package names
        package1 = normalize_package_name(package1)
        package2 = normalize_package_name(package2)

        db = next(get_db())
        try:
            # Find or create packages
            pkg1 = db.query(Package).filter(Package.name == package1).first()
            if not pkg1:
                pkg1 = Package(name=package1, ecosystem="unknown")
                db.add(pkg1)

            pkg2 = db.query(Package).filter(Package.name == package2).first()
            if not pkg2:
                pkg2 = Package(name=package2, ecosystem="unknown")
                db.add(pkg2)

            db.commit()

            # Create conflict rule
            conflict = ConflictRule(
                package1_id=pkg1.id,
                package1_version_spec=package1_version,
                package2_id=pkg2.id,
                package2_version_spec=package2_version,
                conflict_type=conflict_type,
                description=description,
                severity=severity,
                resolution=resolution,
                verified=True,
            )

            db.add(conflict)
            db.commit()

        except Exception as e:
            logger.error(f"Error adding conflict rule: {e}")
            db.rollback()
            raise
        finally:
            db.close()

    def add_verified_combination(
        self,
        name: str,
        packages: list[dict],
        system_requirements: dict | None = None,
        verified_by: str | None = None,
    ):
        """Add a verified working combination."""
        # Normalize package names in the combination
        normalized_packages = []
        for pkg in packages:
            normalized_pkg = pkg.copy()
            normalized_pkg["name"] = normalize_package_name(pkg.get("name", ""))
            if "ecosystem" in pkg:
                normalized_pkg["ecosystem"] = sanitize_ecosystem_name(pkg["ecosystem"])
            normalized_packages.append(normalized_pkg)

        db = next(get_db())
        try:
            combination = VerifiedCombination(
                name=name,
                packages=normalized_packages,
                system_requirements=system_requirements or {},
                verified_by=verified_by,
                verification_date=datetime.utcnow(),
            )

            db.add(combination)
            db.commit()

        except Exception as e:
            logger.error(f"Error adding verified combination: {e}")
            db.rollback()
            raise
        finally:
            db.close()

    def get_cached_resolution(self, packages: list[dict], system_info: dict) -> dict | None:
        """Get cached resolution if available."""
        # Normalize package names before creating hash
        normalized_packages = []
        for pkg in packages:
            normalized_pkg = pkg.copy()
            normalized_pkg["name"] = normalize_package_name(pkg.get("name", ""))
            if "ecosystem" in pkg:
                normalized_pkg["ecosystem"] = sanitize_ecosystem_name(pkg["ecosystem"])
            normalized_packages.append(normalized_pkg)

        # Use consistent system info hashing
        request_hash = self._generate_cache_key(normalized_packages, system_info)

        db = next(get_db())
        try:
            cached = (
                db.query(ResolutionCache)
                .filter(ResolutionCache.request_hash == request_hash)
                .first()
            )

            if cached and cached.expires_at > datetime.utcnow():
                # Update hit count
                cached.hit_count += 1
                db.commit()

                return cached.resolution

            return None

        finally:
            db.close()

    def cache_resolution(
        self,
        packages: list[dict],
        system_info: dict,
        resolution: dict,
        resolution_time_ms: int,
    ):
        """Cache a resolution result."""
        # Normalize package names before creating hash
        normalized_packages = []
        for pkg in packages:
            normalized_pkg = pkg.copy()
            normalized_pkg["name"] = normalize_package_name(pkg.get("name", ""))
            if "ecosystem" in pkg:
                normalized_pkg["ecosystem"] = sanitize_ecosystem_name(pkg["ecosystem"])
            normalized_packages.append(normalized_pkg)

        # Use consistent cache key generation
        request_hash = self._generate_cache_key(normalized_packages, system_info)

        db = next(get_db())
        try:
            # Check if already cached
            cached = (
                db.query(ResolutionCache)
                .filter(ResolutionCache.request_hash == request_hash)
                .first()
            )

            if cached:
                # Update existing cache
                cached.resolution = resolution
                cached.resolution_time_ms = resolution_time_ms
                cached.expires_at = datetime.utcnow() + timedelta(hours=24)
                cached.success = resolution.get("status") == "success"
            else:
                # Create new cache entry
                cached = ResolutionCache(
                    request_hash=request_hash,
                    packages=normalized_packages,
                    system_info=system_info,
                    resolution=resolution,
                    resolution_time_ms=resolution_time_ms,
                    success=resolution.get("status") == "success",
                    expires_at=datetime.utcnow() + timedelta(hours=24),
                )
                db.add(cached)

            db.commit()

        except Exception as e:
            logger.error(f"Error caching resolution: {e}")
            db.rollback()
        finally:
            db.close()

    def _generate_cache_key(self, packages: list[dict], system_info: dict) -> str:
        """Generate consistent cache key."""
        # Sort packages for consistent hashing
        sorted_packages = sorted(packages, key=lambda x: x.get("name", ""))

        # Use utility function for system info hash
        system_hash = hash_system_info(system_info)

        # Combine for final hash
        request_data = {"packages": sorted_packages, "system_hash": system_hash}

        return hashlib.sha256(dumps(request_data, sort_keys=True).encode()).hexdigest()

    def record_system_benchmark(self, system_info: dict, benchmarks: dict):
        """Record system benchmark results."""
        # Extract system fields
        sys_fields = self._extract_system_fields(system_info)

        # Create system hash using utility
        system_hash = hash_system_info(system_info)

        db = next(get_db())
        try:
            benchmark = (
                db.query(SystemBenchmark).filter(SystemBenchmark.system_hash == system_hash).first()
            )

            # Extract memory info
            memory_info = system_info.get("memory", {})
            ram_gb = memory_info.get("total", 0) / (1024**3) if memory_info else None

            # Extract GPU memory
            gpu_memory_gb = None
            if system_info.get("gpu", {}).get("available"):
                devices = system_info["gpu"].get("devices", [])
                if devices and isinstance(devices[0], dict):
                    gpu_memory_mb = devices[0].get("memory_total", 0)
                    gpu_memory_gb = gpu_memory_mb / 1024 if gpu_memory_mb else None

            if not benchmark:
                benchmark = SystemBenchmark(
                    system_hash=system_hash,
                    os_name=sys_fields["os_name"],
                    os_version=sys_fields["os_version"],
                    cpu_model=system_info.get("cpu", {}).get("brand"),
                    cpu_cores=system_info.get("cpu", {}).get("count_logical"),
                    ram_gb=ram_gb,
                    gpu_model=sys_fields["gpu_name"],
                    gpu_memory_gb=gpu_memory_gb,
                    system_info=system_info,
                    benchmarks=benchmarks,
                )
                db.add(benchmark)
            else:
                # Update benchmarks
                benchmark.benchmarks = benchmarks

            db.commit()

        except Exception as e:
            logger.error(f"Error recording benchmark: {e}")
            db.rollback()
        finally:
            db.close()
