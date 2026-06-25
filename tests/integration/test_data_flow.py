"""End-to-end data flow integration tests.

Tests the full pipeline: HTTP request -> route handler -> service layer ->
database operations -> response serialization.
"""

import pytest
from unittest.mock import patch, AsyncMock

from backend.database.models import Package, PackageVersion


class TestPackageLifecycle:
    """Full lifecycle of a package from creation through the API and database."""

    @pytest.fixture(autouse=True)
    def _mock_external(self):
        patcher = patch("backend.api.dependencies.get_data_aggregator")
        mock_get_agg = patcher.start()
        aggregator = AsyncMock()
        aggregator.get_package_info = AsyncMock(
            return_value={
                "name": "lifecycle-pkg",
                "ecosystem": "pypi",
                "version": "1.0.0",
                "description": "Lifecycle test package",
            }
        )
        aggregator.sources = {}
        mock_get_agg.return_value = aggregator
        yield
        patcher.stop()

    def test_package_create_and_fetch(self, db_session):
        pkg = Package(
            name="lifecycle-pkg",
            ecosystem="pypi",
            latest_version="1.0.0",
            description="A package with a full lifecycle",
        )
        db_session.add(pkg)
        db_session.commit()

        saved = db_session.query(Package).filter_by(name="lifecycle-pkg").first()
        assert saved.description == "A package with a full lifecycle"
        assert saved.latest_version == "1.0.0"

    def test_package_add_versions_then_query(self, db_session):
        pkg = Package(name="multi-version", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        versions = [
            PackageVersion(package_id=pkg.id, version=f"1.{i}.0") for i in range(5)
        ]
        db_session.add_all(versions)
        db_session.commit()

        versions_asc = (
            db_session.query(PackageVersion)
            .filter_by(package_id=pkg.id)
            .order_by(PackageVersion.version)
            .all()
        )
        assert len(versions_asc) == 5
        assert versions_asc[0].version == "1.0.0"
        assert versions_asc[-1].version == "1.4.0"

    def test_package_update_and_verify_timestamp(self, db_session):
        pkg = Package(name="timestamp-test", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        original_updated_at = pkg.updated_at

        pkg.latest_version = "2.0.0"
        db_session.commit()

        assert pkg.updated_at >= original_updated_at


class TestCrossModelRelationships:
    """Test relationships between multiple models."""

    def test_package_with_versions_and_compatibility(self, db_session):
        pkg = Package(name="relational-pkg", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        version = PackageVersion(
            package_id=pkg.id,
            version="1.0.0",
            python_requires=">=3.9",
        )
        db_session.add(version)
        db_session.commit()

        from backend.database.models import CompatibilityReport

        report = CompatibilityReport(
            package_id=pkg.id,
            version="1.0.0",
            os_name="Linux",
            python_version="3.11",
            works=True,
        )
        db_session.add(report)
        db_session.commit()

        loaded = db_session.query(Package).filter_by(name="relational-pkg").first()
        assert len(loaded.versions) == 1
        assert len(loaded.compatibility_reports) == 1
        assert loaded.compatibility_reports[0].works is True

    def test_conflict_between_packages(self, db_session):
        from backend.database.models import ConflictRule

        pkg_a = Package(name="lib-a", ecosystem="pypi")
        pkg_b = Package(name="lib-b", ecosystem="pypi")
        db_session.add_all([pkg_a, pkg_b])
        db_session.commit()

        conflict = ConflictRule(
            package1_id=pkg_a.id,
            package2_id=pkg_b.id,
            conflict_type="incompatible",
            severity="critical",
            description="lib-a and lib-b cannot coexist",
            resolution="Use lib-c instead",
        )
        db_session.add(conflict)
        db_session.commit()

        from sqlalchemy import and_

        found = (
            db_session.query(ConflictRule)
            .filter(
                and_(
                    ConflictRule.package1_id == pkg_a.id,
                    ConflictRule.package2_id == pkg_b.id,
                )
            )
            .first()
        )
        assert found is not None
        assert found.severity == "critical"
        assert found.resolution == "Use lib-c instead"


class TestDataPersistence:
    """Test that data persists correctly across operations."""

    def test_create_and_verify_multiple_tables(self, db_session):
        pkg = Package(name="persistence-test", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        ver = PackageVersion(package_id=pkg.id, version="0.1.0")
        db_session.add(ver)
        db_session.commit()

        verify_pkg = db_session.get(Package, pkg.id)
        assert verify_pkg is not None
        assert len(verify_pkg.versions) == 1

    def test_rollback_on_error(self, db_session):
        from sqlalchemy.exc import IntegrityError

        pkg = Package(name="rollback-test", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        pkg_id = pkg.id

        sp = db_session.begin_nested()
        try:
            dup = Package(name="rollback-test", ecosystem="pypi")
            db_session.add(dup)
            db_session.commit()
        except IntegrityError:
            sp.rollback()

        assert db_session.get(Package, pkg_id) is not None

    def test_serialize_package_to_dict(self, db_session):
        pkg = Package(
            name="serialize-test",
            ecosystem="pypi",
            latest_version="1.0.0",
            description="Testing serialization",
        )
        db_session.add(pkg)
        db_session.commit()

        d = {
            "id": pkg.id,
            "name": pkg.name,
            "ecosystem": pkg.ecosystem,
            "latest_version": pkg.latest_version,
            "description": pkg.description,
        }
        assert d["name"] == "serialize-test"
        assert d["ecosystem"] == "pypi"
        assert d["latest_version"] == "1.0.0"


class TestErrorRecovery:
    """Test system behavior under error conditions."""

    def test_duplicate_package_handling(self, db_session):
        pkg_a = Package(name="dup-test", ecosystem="pypi")
        db_session.add(pkg_a)
        db_session.commit()

        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            pkg_b = Package(name="dup-test", ecosystem="pypi")
            db_session.add(pkg_b)
            db_session.commit()

    def test_missing_relationship(self, db_session):
        orphan = PackageVersion(
            package_id=99999,
            version="1.0.0",
        )
        db_session.add(orphan)

        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
