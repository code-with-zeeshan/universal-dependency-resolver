"""Integration tests for database models, relationships, and constraints."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.database.models import (
    Package,
    PackageVersion,
    CompatibilityReport,
    ConflictRule,
    ResolutionCache,
    User,
    APIKey,
)


class TestPackageCRUD:
    """Test basic CRUD operations on the Package model."""

    def test_create_package(self, db_session):
        pkg = Package(name="flask", ecosystem="pypi", latest_version="2.3.3")
        db_session.add(pkg)
        db_session.commit()

        saved = db_session.query(Package).filter_by(name="flask").first()
        assert saved is not None
        assert saved.name == "flask"
        assert saved.ecosystem == "pypi"
        assert saved.latest_version == "2.3.3"

    def test_unique_constraint_name_ecosystem(self, db_session):
        db_session.add(Package(name="flask", ecosystem="pypi"))
        db_session.commit()

        with pytest.raises(IntegrityError):
            db_session.add(Package(name="flask", ecosystem="pypi"))
            db_session.commit()
        db_session.rollback()

    def test_same_name_different_ecosystem_allowed(self, db_session):
        db_session.add(Package(name="flask", ecosystem="pypi"))
        db_session.commit()

        db_session.add(Package(name="flask", ecosystem="npm"))
        db_session.commit()

        count = db_session.query(Package).filter_by(name="flask").count()
        assert count == 2

    def test_update_package(self, db_session):
        pkg = Package(name="requests", ecosystem="pypi", latest_version="2.28.0")
        db_session.add(pkg)
        db_session.commit()

        pkg.latest_version = "2.31.0"
        db_session.commit()

        updated = db_session.query(Package).filter_by(name="requests").first()
        assert updated.latest_version == "2.31.0"

    def test_delete_package(self, db_session):
        pkg = Package(name="deleteme", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        db_session.delete(pkg)
        db_session.commit()

        deleted = db_session.query(Package).filter_by(name="deleteme").first()
        assert deleted is None

    def test_auto_timestamps(self, db_session):
        pkg = Package(name="timed-pkg", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        assert pkg.created_at is not None
        assert pkg.updated_at is not None


class TestPackageVersion:
    """Test PackageVersion model relationships and constraints."""

    def test_create_version(self, db_session):
        pkg = Package(name="numpy", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        version = PackageVersion(
            package_id=pkg.id,
            version="1.26.0",
            python_requires=">=3.9",
        )
        db_session.add(version)
        db_session.commit()

        saved = db_session.query(PackageVersion).filter_by(version="1.26.0").first()
        assert saved is not None
        assert saved.package_id == pkg.id

    def test_version_unique_per_package(self, db_session):
        pkg = Package(name="pandas", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        db_session.add(PackageVersion(package_id=pkg.id, version="2.0.0"))
        db_session.commit()

        with pytest.raises(IntegrityError):
            db_session.add(PackageVersion(package_id=pkg.id, version="2.0.0"))
            db_session.commit()
        db_session.rollback()

    def test_same_version_different_package_allowed(self, db_session):
        pkg1 = Package(name="pkg-a", ecosystem="pypi")
        pkg2 = Package(name="pkg-b", ecosystem="pypi")
        db_session.add_all([pkg1, pkg2])
        db_session.commit()

        db_session.add(PackageVersion(package_id=pkg1.id, version="1.0.0"))
        db_session.add(PackageVersion(package_id=pkg2.id, version="1.0.0"))
        db_session.commit()

        count = db_session.query(PackageVersion).filter_by(version="1.0.0").count()
        assert count == 2

    def test_version_with_dependencies_json(self, db_session):
        pkg = Package(name="tensorflow", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        deps = {"numpy": ">=1.24", "protobuf": ">=3.20"}
        system_reqs = {"python_versions": [">=3.9", "<3.12"], "cuda_versions": ["11.x"]}

        version = PackageVersion(
            package_id=pkg.id,
            version="2.13.0",
            dependencies=deps,
            system_requirements=system_reqs,
        )
        db_session.add(version)
        db_session.commit()

        saved = db_session.query(PackageVersion).filter_by(version="2.13.0").first()
        assert saved.dependencies == deps
        assert saved.system_requirements == system_reqs

    def test_version_relationship_backref(self, db_session):
        pkg = Package(name="scipy", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        db_session.add(PackageVersion(package_id=pkg.id, version="1.11.0"))
        db_session.add(PackageVersion(package_id=pkg.id, version="1.11.1"))
        db_session.commit()

        loaded_pkg = db_session.query(Package).filter_by(name="scipy").first()
        assert len(loaded_pkg.versions) == 2
        versions = sorted(v.version for v in loaded_pkg.versions)
        assert versions == ["1.11.0", "1.11.1"]


class TestCompatibilityReport:
    """Test CompatibilityReport model."""

    def test_create_report(self, db_session):
        pkg = Package(name="torch", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        report = CompatibilityReport(
            package_id=pkg.id,
            version="2.0.0",
            os_name="Linux",
            os_version="6.2",
            cpu_architecture="x86_64",
            gpu_name="RTX 3080",
            cuda_version="11.8",
            python_version="3.11",
            works=True,
            notes="Works perfectly",
        )
        db_session.add(report)
        db_session.commit()

        saved = db_session.query(CompatibilityReport).filter_by(version="2.0.0").first()
        assert saved is not None
        assert saved.works is True
        assert saved.cuda_version == "11.8"

    def test_report_relationship(self, db_session):
        pkg = Package(name="jax", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        report = CompatibilityReport(package_id=pkg.id, version="0.4.0", works=True)
        db_session.add(report)
        db_session.commit()

        loaded_pkg = db_session.query(Package).filter_by(name="jax").first()
        assert len(loaded_pkg.compatibility_reports) == 1


class TestConflictRule:
    """Test ConflictRule model."""

    def test_create_conflict(self, db_session):
        pkg1 = Package(name="pkg-a", ecosystem="pypi")
        pkg2 = Package(name="pkg-b", ecosystem="pypi")
        db_session.add_all([pkg1, pkg2])
        db_session.commit()

        conflict = ConflictRule(
            package1_id=pkg1.id,
            package2_id=pkg2.id,
            conflict_type="incompatible",
            severity="high",
            description="Package A conflicts with Package B",
            resolution="Use version 2.0 of both",
        )
        db_session.add(conflict)
        db_session.commit()

        saved = db_session.query(ConflictRule).first()
        assert saved is not None
        assert saved.conflict_type == "incompatible"
        assert saved.severity == "high"
        assert saved.package1 is not None
        assert saved.package2 is not None

    def test_conflict_relationships(self, db_session):
        pkg1 = Package(name="tensorflow", ecosystem="pypi")
        pkg2 = Package(name="torch", ecosystem="pypi")
        db_session.add_all([pkg1, pkg2])
        db_session.commit()

        conflict = ConflictRule(
            package1_id=pkg1.id,
            package2_id=pkg2.id,
            conflict_type="incompatible",
            description="ML framework conflict",
        )
        db_session.add(conflict)
        db_session.commit()

        loaded_pkg = db_session.query(Package).filter_by(name="tensorflow").first()
        assert len(loaded_pkg.conflicts) == 1


class TestUserAndAPIKey:
    """Test User and APIKey models."""

    def test_create_user(self, db_session):
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_pw",
        )
        db_session.add(user)
        db_session.commit()

        saved = db_session.query(User).filter_by(username="testuser").first()
        assert saved is not None
        assert saved.email == "test@example.com"
        assert saved.is_active is True

    def test_unique_username(self, db_session):
        db_session.add(
            User(username="unique_user", email="a@b.com", hashed_password="pw")
        )
        db_session.commit()

        with pytest.raises(IntegrityError):
            db_session.add(
                User(username="unique_user", email="c@d.com", hashed_password="pw2")
            )
            db_session.commit()
        db_session.rollback()

    def test_create_api_key_for_user(self, db_session):
        user = User(username="apiuser", email="api@test.com", hashed_password="pw")
        db_session.add(user)
        db_session.commit()

        api_key = APIKey(
            key="sk-test-key-12345",
            name="Test Key",
            user_id=user.id,
        )
        db_session.add(api_key)
        db_session.commit()

        saved = db_session.query(APIKey).filter_by(key="sk-test-key-12345").first()
        assert saved is not None
        assert saved.user.username == "apiuser"
        assert len(user.api_keys) == 1


class TestResolutionCache:
    """Test ResolutionCache model."""

    def test_create_cache_entry(self, db_session):
        entry = ResolutionCache(
            request_hash="abc123",
            packages={"flask": "2.3.3"},
            system_info={"os": "Linux"},
            constraints={"python": ">=3.9"},
            resolution={"flask": {"version": "2.3.3", "dependencies": {}}},
            resolution_time_ms=150,
            success=True,
        )
        db_session.add(entry)
        db_session.commit()

        saved = (
            db_session.query(ResolutionCache).filter_by(request_hash="abc123").first()
        )
        assert saved is not None
        assert saved.success is True
        assert saved.resolution_time_ms == 150

    def test_unique_request_hash(self, db_session):
        db_session.add(ResolutionCache(request_hash="dup_hash"))
        db_session.commit()

        with pytest.raises(IntegrityError):
            db_session.add(ResolutionCache(request_hash="dup_hash"))
            db_session.commit()
        db_session.rollback()



class TestBulkOperations:
    """Test bulk insert and query performance."""

    def test_bulk_insert_packages(self, db_session):
        packages = [
            Package(name=f"pkg-{i}", ecosystem="pypi", latest_version=f"1.{i}.0")
            for i in range(100)
        ]
        db_session.add_all(packages)
        db_session.commit()

        count = db_session.query(Package).count()
        assert count >= 100

    def test_bulk_insert_versions(self, db_session):
        pkg = Package(name="many-versions", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        versions = [
            PackageVersion(package_id=pkg.id, version=f"0.{i}.0") for i in range(50)
        ]
        db_session.add_all(versions)
        db_session.commit()

        loaded = db_session.query(Package).filter_by(name="many-versions").first()
        assert len(loaded.versions) == 50

    def test_cascade_delete_package_removes_versions(self, db_session):
        pkg = Package(name="cascade-test", ecosystem="pypi")
        db_session.add(pkg)
        db_session.commit()

        db_session.add_all(
            [
                PackageVersion(package_id=pkg.id, version="1.0.0"),
                PackageVersion(package_id=pkg.id, version="1.1.0"),
            ]
        )
        db_session.commit()

        version_count_before = (
            db_session.query(PackageVersion)
            .filter(PackageVersion.package_id == pkg.id)
            .count()
        )
        assert version_count_before == 2

        db_session.delete(pkg)
        db_session.commit()

        version_count_after = db_session.query(PackageVersion).count()
        assert version_count_after == 0

    def test_query_by_ecosystem(self, db_session):
        ecosystems = ["pypi", "npm", "pypi", "conda", "npm"]
        packages = [
            Package(name=f"pkg-{i}", ecosystem=eco) for i, eco in enumerate(ecosystems)
        ]
        db_session.add_all(packages)
        db_session.commit()

        pypi_count = db_session.query(Package).filter_by(ecosystem="pypi").count()
        npm_count = db_session.query(Package).filter_by(ecosystem="npm").count()
        assert pypi_count == 2
        assert npm_count == 2

    def test_indexed_search_by_name(self, db_session):
        db_session.add_all(
            [
                Package(name="tensorflow", ecosystem="pypi"),
                Package(name="tensorrt", ecosystem="pypi"),
                Package(name="tensorboard", ecosystem="pypi"),
                Package(name="pytorch", ecosystem="pypi"),
            ]
        )
        db_session.commit()

        results = db_session.query(Package).filter(Package.name.like("tensor%")).all()
        assert len(results) == 3


class TestHealthCheck:
    """Test database health check functionality."""

    def test_db_connection_health(self, db_session):
        result = db_session.execute(text("SELECT 1"))
        assert result.scalar() == 1

    @pytest.mark.requires_postgres
    def test_database_version(self, db_session):
        result = db_session.execute(text("SELECT version()"))
        version = result.scalar()
        assert "PostgreSQL" in version

    @pytest.mark.requires_postgres
    def test_table_count(self, db_session):
        result = db_session.execute(
            text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
            )
        )
        count = result.scalar()
        assert count >= 9
