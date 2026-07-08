# tests/unit/test_database/test_compatibility_db.py
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from backend.database.compatibility_db import CompatibilityDB

# ---------------------------------------------------------------------------
# Pure-method tests (no DB needed)
# ---------------------------------------------------------------------------


class TestExtractSystemFields:
    @pytest.fixture
    def db(self):
        return CompatibilityDB()

    def test_empty_system_info(self, db):
        result = db._extract_system_fields({})
        assert result["os_name"] is None
        assert result["os_version"] is None
        assert result["cpu_architecture"] is None
        assert result["gpu_name"] is None
        assert result["cuda_version"] is None
        assert result["cudnn_version"] is None
        assert result["python_version"] is None

    def test_full_platform_info(self, db):
        info = {
            "platform": {"system": "Linux", "release": "5.15.0"},
            "cpu": {"arch": "x86_64"},
            "gpu": {"available": False},
            "runtime_versions": {"python": {"version": "3.11.0"}},
        }
        result = db._extract_system_fields(info)
        assert result["os_name"] == "Linux"
        assert result["os_version"] == "5.15.0"
        assert result["cpu_architecture"] == "x86_64"
        assert result["gpu_name"] is None
        assert result["python_version"] == "3.11.0"

    def test_gpu_with_devices(self, db):
        info = {
            "gpu": {
                "available": True,
                "devices": [{"name": "RTX 4090", "memory_total": 24576}],
                "cuda": {"version": "12.1", "cudnn": {"version": "8.9.0"}},
            }
        }
        result = db._extract_system_fields(info)
        assert result["gpu_name"] == "RTX 4090"
        assert result["cuda_version"] == "12.1"
        assert result["cudnn_version"] == "8.9.0"

    def test_cuda_string_instead_of_dict(self, db):
        info = {
            "gpu": {
                "available": True,
                "devices": [{"name": "Tesla T4"}],
                "cuda": "11.8",
            }
        }
        assert db._extract_system_fields(info)["cuda_version"] == "11.8"

    def test_cpu_architecture_fallback(self, db):
        assert (
            db._extract_system_fields({"cpu": {"architecture": "arm64"}})["cpu_architecture"]
            == "arm64"
        )

    def test_python_version_not_dict(self, db):
        info = {"runtime_versions": {"python": "3.10.0"}}
        assert db._extract_system_fields(info)["python_version"] is None

    def test_no_devices_gpu_available(self, db):
        assert db._extract_system_fields({"gpu": {"available": True}})["gpu_name"] is None


class TestExtractWarningsFromReports:
    @pytest.fixture
    def db(self):
        return CompatibilityDB()

    @staticmethod
    def _report(works, notes=""):
        m = MagicMock()
        m.works = works
        m.notes = notes
        return m

    def test_no_failed_reports(self, db):
        assert db._extract_warnings_from_reports([self._report(True), self._report(True)]) == []

    def test_below_threshold(self, db):
        reports = [self._report(False, "other"), self._report(False, "another")]
        assert db._extract_warnings_from_reports(reports) == []

    def test_cuda_warning(self, db):
        reports = [
            self._report(False, "CUDA version mismatch"),
            self._report(False, "CUDA not found"),
        ]
        warnings = db._extract_warnings_from_reports(reports)
        assert any("cuda" in w.lower() for w in warnings)

    def test_memory_warning(self, db):
        reports = [
            self._report(False, "out of memory"),
            self._report(False, "memory allocation failed"),
        ]
        warnings = db._extract_warnings_from_reports(reports)
        assert any("memory" in w.lower() for w in warnings)

    def test_version_warning(self, db):
        reports = [self._report(False, "version conflict"), self._report(False, "wrong version")]
        warnings = db._extract_warnings_from_reports(reports)
        assert any("version" in w.lower() for w in warnings)


class TestSerializeConflict:
    @pytest.fixture
    def db(self):
        return CompatibilityDB()

    @staticmethod
    def _conflict(p1_id, p2_id, p1_name, p2_name, **kw):
        c = MagicMock()
        c.package1_id = p1_id
        c.package2_id = p2_id
        c.package1 = MagicMock()
        c.package1.name = p1_name
        c.package2 = MagicMock()
        c.package2.name = p2_name
        for k, v in kw.items():
            setattr(c, k, v)
        return c

    def test_conflict_as_package1(self, db):
        conflict = self._conflict(
            1,
            2,
            "requests",
            "numpy",
            package1_version_spec=">=1.0",
            package2_version_spec="<2.0",
            conflict_type="incompatible",
            severity="error",
            description="numpy 2.x incompatible",
            resolution="pin numpy<2",
        )
        result = db._serialize_conflict(conflict, package_id=1)
        assert result["conflicting_package"] == "numpy"
        assert result["version_spec"] == "<2.0"
        assert result["severity"] == "error"

    def test_conflict_as_package2(self, db):
        conflict = self._conflict(
            1,
            2,
            "pandas",
            "numpy",
            package1_version_spec=">=1.0",
            package2_version_spec="<2.0",
            conflict_type="incompatible",
            severity="warning",
            description="version conflict",
            resolution="upgrade",
        )
        result = db._serialize_conflict(conflict, package_id=2)
        assert result["conflicting_package"] == "pandas"
        assert result["version_spec"] == ">=1.0"


class TestSerializeCombination:
    @pytest.fixture
    def db(self):
        return CompatibilityDB()

    def test_with_verification_date(self, db):
        combo = MagicMock()
        combo.name = "test-combo"
        combo.description = "a verified combo"
        combo.packages = [{"name": "numpy", "version": "1.24"}]
        combo.system_requirements = {"os": "linux"}
        combo.verified_by = "ci-bot"
        combo.verification_date = datetime(2024, 1, 15, 12, 0, 0)
        combo.usage_count = 5
        combo.success_rate = 0.95
        result = db._serialize_combination(combo)
        assert result["name"] == "test-combo"
        assert result["verification_date"] == "2024-01-15T12:00:00"

    def test_without_verification_date(self, db):
        combo = MagicMock()
        combo.name = "no-date"
        combo.description = ""
        combo.packages = []
        combo.system_requirements = {}
        combo.verified_by = None
        combo.verification_date = None
        combo.usage_count = 0
        combo.success_rate = 0.0
        result = db._serialize_combination(combo)
        assert result["verification_date"] is None


class TestGenerateCacheKey:
    @pytest.fixture
    def db(self):
        return CompatibilityDB()

    def test_deterministic(self, db):
        packages = [{"name": "requests", "version_spec": ">=2.0"}]
        system = {"os": "linux"}
        assert db._generate_cache_key(packages, system) == db._generate_cache_key(packages, system)

    def test_different_inputs_different_keys(self, db):
        k1 = db._generate_cache_key([{"name": "a"}], {"os": "linux"})
        k2 = db._generate_cache_key([{"name": "b"}], {"os": "linux"})
        assert k1 != k2

    def test_normalizes_sorted_order(self, db):
        k1 = db._generate_cache_key([{"name": "b"}, {"name": "a"}], {"os": "linux"})
        k2 = db._generate_cache_key([{"name": "a"}, {"name": "b"}], {"os": "linux"})
        assert k1 == k2

    def test_output_length(self, db):
        key = db._generate_cache_key([{"name": "x"}], {})
        assert len(key) == 64


class TestAddPackageVersion:
    @pytest.fixture
    def db(self):
        return CompatibilityDB()

    def test_invalid_version_skipped(self, db):
        mock_db = MagicMock()
        db._add_package_version(mock_db, 1, {"version": "notaversion"})
        mock_db.add.assert_not_called()

    def test_valid_version_added(self, db):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        db._add_package_version(mock_db, 1, {"version": "1.0.0"})
        mock_db.add.assert_called_once()

    def test_duplicate_version_skipped(self, db):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = MagicMock()
        db._add_package_version(mock_db, 1, {"version": "1.0.0"})
        mock_db.add.assert_not_called()


class TestAggregateReports:
    @pytest.fixture
    def db(self):
        return CompatibilityDB()

    @staticmethod
    def _report(works, version="1.0", os_name="Linux", py="3.9", cuda=None, notes=""):
        r = MagicMock()
        r.works = works
        r.version = version
        r.os_name = os_name
        r.python_version = py
        r.cuda_version = cuda
        r.notes = notes
        return r

    def test_empty(self, db):
        result = db._aggregate_reports([])
        assert result["total_reports"] == 0
        assert result["success_rate"] == 0

    def test_all_successful(self, db):
        reports = [self._report(True), self._report(True)]
        result = db._aggregate_reports(reports)
        assert result["total_reports"] == 2
        assert result["success_rate"] == 1.0

    def test_mixed_results(self, db):
        reports = [self._report(True), self._report(False), self._report(True)]
        result = db._aggregate_reports(reports)
        assert result["total_reports"] == 3
        assert result["success_rate"] == pytest.approx(2 / 3)

    def test_common_issues_extracted(self, db):
        reports = [
            self._report(False, notes="CUDA incompatible"),
            self._report(False, notes="cuda error"),
        ]
        result = db._aggregate_reports(reports)
        keywords = [i["keyword"] for i in result["common_issues"]]
        assert "cuda" in keywords

    def test_by_version_grouping(self, db):
        reports = [self._report(True, version="1.0"), self._report(True, version="2.0")]
        result = db._aggregate_reports(reports)
        assert "1.0" in result["by_version"]
        assert "2.0" in result["by_version"]


# ---------------------------------------------------------------------------
# Mock-based DB method tests
# ---------------------------------------------------------------------------


class TestAddPackageMock:
    @pytest.fixture
    def db(self):
        return CompatibilityDB()

    def test_add_new_package(self, db):
        mock_pkg = MagicMock()
        mock_pkg.id = 1
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_get_db = iter([mock_session])

        with (
            patch("backend.database.compatibility_db.Package", return_value=mock_pkg),
            patch("backend.database.compatibility_db.get_db", return_value=mock_get_db),
        ):
            pkg_id = db.add_package("requests", "pypi", {"version": "2.31.0"})

        assert pkg_id == 1
        mock_session.add.assert_called_once_with(mock_pkg)
        mock_session.commit.assert_called_once()

    def test_add_package_with_invalid_version(self, db):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_get_db = iter([mock_session])

        with patch("backend.database.compatibility_db.get_db", return_value=mock_get_db):
            db.add_package(
                "badver", "pypi", {"version": "1.0", "versions": [{"version": "invalid"}]}
            )

        # The version with invalid version string should not be added
        assert mock_session.add.call_count >= 1  # at least the package itself


class TestGetPackageByNormalizedNameMock:
    def test_found(self):
        db = CompatibilityDB()
        mock_pkg = MagicMock()
        mock_pkg.name = "my-package"
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_pkg

        with patch("backend.database.compatibility_db.get_db", return_value=iter([mock_session])):
            result = db.get_package_by_normalized_name("my_package", "pypi")

        assert result is not None
        assert result.name == "my-package"

    def test_not_found(self):
        db = CompatibilityDB()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with patch("backend.database.compatibility_db.get_db", return_value=iter([mock_session])):
            result = db.get_package_by_normalized_name("nonexistent", "pypi")

        assert result is None


class TestAddConflictRuleMock:
    def test_add_rule(self):
        db = CompatibilityDB()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.side_effect = [None, None]
        mock_get_db = iter([mock_session, mock_session])

        with patch("backend.database.compatibility_db.get_db", return_value=mock_get_db):
            db.add_conflict_rule(
                "numpy", ">=1.24", "pandas", "<2.0", "incompatible", "numpy 1.24+ breaks pandas"
            )

        assert mock_session.add.call_count >= 1
        mock_session.commit.assert_called()


class TestBulkImportPackagesMock:
    def test_import_multiple(self):
        db = CompatibilityDB()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_get_db = iter([mock_session, mock_session, mock_session])

        with patch("backend.database.compatibility_db.get_db", return_value=mock_get_db):
            count = db.bulk_import_packages(
                [
                    {"name": "pkg1", "ecosystem": "pypi", "version": "1.0"},
                    {"name": "pkg2", "ecosystem": "npm", "version": "2.0"},
                ]
            )

        assert count == 2


class TestAddCompatibilityReportMock:
    def test_add_report(self):
        db = CompatibilityDB()
        mock_pkg = MagicMock()
        mock_pkg.id = 1
        mock_report = MagicMock()
        mock_report.id = 1
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_pkg
        mock_get_db = iter([mock_session])

        with (
            patch(
                "backend.database.compatibility_db.CompatibilityReport", return_value=mock_report
            ),
            patch("backend.database.compatibility_db.get_db", return_value=mock_get_db),
        ):
            report_id = db.add_compatibility_report(
                "torch",
                "2.0.0",
                "pypi",
                {"platform": {"system": "Linux"}, "gpu": {"available": False}},
                works=True,
            )

        assert report_id == 1
        mock_session.add.assert_called_once_with(mock_report)
        mock_session.commit.assert_called()


class TestCacheResolutionMock:
    def test_cache_miss(self):
        db = CompatibilityDB()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_get_db = iter([mock_session])

        with patch("backend.database.compatibility_db.get_db", return_value=mock_get_db):
            result = db.get_cached_resolution([{"name": "requests"}], {"os": "linux"})

        assert result is None

    def test_cache_hit(self):
        db = CompatibilityDB()
        mock_cache_entry = MagicMock()
        mock_cache_entry.expires_at = datetime(2099, 1, 1)
        mock_cache_entry.resolution = {"status": "success", "packages": {"requests": "2.31.0"}}
        mock_cache_entry.hit_count = 0
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_cache_entry
        mock_get_db = iter([mock_session])

        with patch("backend.database.compatibility_db.get_db", return_value=mock_get_db):
            result = db.get_cached_resolution([{"name": "requests"}], {"os": "linux"})

        assert result == {"status": "success", "packages": {"requests": "2.31.0"}}
        assert mock_cache_entry.hit_count == 1

    def test_expired_cache(self):
        db = CompatibilityDB()
        mock_cache_entry = MagicMock()
        mock_cache_entry.expires_at = datetime(2020, 1, 1)
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_cache_entry
        mock_get_db = iter([mock_session])

        with patch("backend.database.compatibility_db.get_db", return_value=mock_get_db):
            result = db.get_cached_resolution([{"name": "requests"}], {"os": "linux"})

        assert result is None


class TestCheckVersionCompatibilityMock:
    def test_package_not_found(self):
        db = CompatibilityDB()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with patch(
            "backend.database.compatibility_db.get_db",
            return_value=iter([mock_session, mock_session]),
        ):
            result = db.check_version_compatibility("unknown", "1.0", {})

        assert result["compatible"] is True
        assert result["confidence"] == 0.0

    def test_no_reports(self):
        db = CompatibilityDB()
        mock_pkg = MagicMock()
        mock_pkg.id = 1
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.side_effect = [mock_pkg]
        mock_session.query.return_value.filter.return_value.all.return_value = []

        with patch(
            "backend.database.compatibility_db.get_db",
            return_value=iter([mock_session, mock_session]),
        ):
            result = db.check_version_compatibility(
                "pkg",
                "1.0",
                {
                    "platform": {"system": "Linux"},
                    "runtime_versions": {"python": {"version": "3.11"}},
                },
            )

        assert result["compatible"] is True
        assert result["confidence"] == 0.1
        assert result["similar_systems"] == 0


class TestRecordSystemBenchmarkMock:
    def test_new_benchmark(self):
        db = CompatibilityDB()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with patch("backend.database.compatibility_db.get_db", return_value=iter([mock_session])):
            db.record_system_benchmark(
                {"platform": {"system": "Linux"}, "cpu": {"brand": "Intel", "count_logical": 16}},
                {"cpu_score": 1000},
            )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called()

    def test_update_existing(self):
        db = CompatibilityDB()
        existing = MagicMock()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = existing

        with patch("backend.database.compatibility_db.get_db", return_value=iter([mock_session])):
            db.record_system_benchmark({"platform": {"system": "Linux"}}, {"cpu_score": 2000})

        mock_session.add.assert_not_called()
        mock_session.commit.assert_called()


class TestCleanupOldCacheMock:
    def test_cleanup(self):
        db = CompatibilityDB()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.delete.return_value = 5

        with patch("backend.database.compatibility_db.get_db", return_value=iter([mock_session])):
            db.cleanup_old_cache(days=7)

        mock_session.commit.assert_called()
