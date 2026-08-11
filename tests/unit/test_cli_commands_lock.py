import argparse

from backend.cli.commands.lock import _detect_and_parse_manifests, _extract_integrity
from backend.manifest_detector import ManifestDetector


class TestExtractIntegrity:
    def test_no_versions(self):
        assert _extract_integrity({"versions": []}, "1.0", "npm") is None

    def test_no_versions_key(self):
        assert _extract_integrity({}, "1.0", "npm") is None

    def test_version_not_found(self):
        pkg = {"versions": [{"version": "2.0", "dist": {"integrity": "sha512-abc123"}}]}
        assert _extract_integrity(pkg, "1.0", "npm") is None

    def test_sha512_integrity(self):
        pkg = {
            "versions": [
                {
                    "version": "1.0",
                    "dist": {"integrity": "sha512-abc123def456"},
                }
            ]
        }
        result = _extract_integrity(pkg, "1.0", "npm")
        assert result == {"algorithm": "sha512", "hash": "abc123def456"}

    def test_sha256_integrity(self):
        pkg = {
            "versions": [
                {
                    "version": "1.0",
                    "dist": {"integrity": "sha256-abc123def456"},
                }
            ]
        }
        result = _extract_integrity(pkg, "1.0", "npm")
        assert result == {"algorithm": "sha256", "hash": "abc123def456"}

    def test_sha1_integrity(self):
        pkg = {
            "versions": [
                {
                    "version": "1.0",
                    "dist": {"integrity": "sha1-abc123"},
                }
            ]
        }
        result = _extract_integrity(pkg, "1.0", "npm")
        assert result == {"algorithm": "sha1", "hash": "abc123"}

    def test_unknown_integrity(self):
        pkg = {
            "versions": [
                {
                    "version": "1.0",
                    "dist": {"integrity": "md5-abc123"},
                }
            ]
        }
        result = _extract_integrity(pkg, "1.0", "npm")
        assert result == {"algorithm": "unknown", "hash": "md5-abc123"}

    def test_shasum_fallback(self):
        pkg = {
            "versions": [
                {
                    "version": "1.0",
                    "dist": {"shasum": "abc123def456"},
                }
            ]
        }
        result = _extract_integrity(pkg, "1.0", "npm")
        assert result == {"algorithm": "sha1", "hash": "abc123def456"}

    def test_no_dist_key(self):
        pkg = {"versions": [{"version": "1.0"}]}
        assert _extract_integrity(pkg, "1.0", "npm") is None

    def test_empty_dist(self):
        pkg = {"versions": [{"version": "1.0", "dist": {}}]}
        assert _extract_integrity(pkg, "1.0", "npm") is None

    def test_non_dict_version_entry(self):
        pkg = {"versions": ["1.0"]}
        assert _extract_integrity(pkg, "1.0", "npm") is None


class TestBuildLockDataStatus:
    """Failed resolutions must surface status/resolution_error in lock JSON
    output instead of a silent empty packages dict (Minor 1 regression)."""

    def _build(self, resolved):
        from backend.cli.commands.lock import _build_lock_data

        class _Args:
            target = None
            platform = None
            cuda = None
            force = False
            pin = []
            block = []
            pin_mode = "none"
            freeze = False

        return _build_lock_data(
            None,
            None,
            {"platform": {}, "gpu": {}, "runtime_versions": {}, "cpu": {}},
            [],
            resolved,
            [],
            {},
            [],
            None,
            _Args(),
        )

    def test_unsatisfiable_includes_status(self):
        lock_data = self._build(
            {
                "status": "unsatisfiable",
                "resolution_error": "No versions of django satisfy >=5.0,<4.0",
                "resolved_packages": {},
            }
        )
        assert lock_data["status"] == "unsatisfiable"
        assert lock_data["resolution_error"] == "No versions of django satisfy >=5.0,<4.0"

    def test_satisfiable_default_status(self):
        lock_data = self._build(
            {"resolved_packages": {"django": {"version": "5.2.0", "ecosystem": "pypi"}}}
        )
        assert lock_data["status"] == "satisfiable"
        assert "resolution_error" not in lock_data


class TestDetectAndParseManifestsOptional:
    """--with-dev / --without-optional filtering of optional manifest deps."""

    def _make_args(self, **overrides) -> argparse.Namespace:
        defaults = {
            "directory": None,
            "include_dev": False,
            "manifest": None,
            "interactive": False,
            "json": True,
            "with_dev": None,
            "without_optional": None,
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def _write_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            """\
[project]
name = "demo"
version = "1.0.0"

[project.dependencies]
requests = ">=2.28.0"

[project.optional-dependencies]
dev = ["pytest>=7.0.0", "black"]
training = ["protobuf>=3.20.3,<4"]
""",
            encoding="utf-8",
        )

    def _packages(self, tmp_path, args):
        detector = ManifestDetector(str(tmp_path))
        _, packages = _detect_and_parse_manifests(detector, args)
        return sorted(p["name"] for p in packages)

    def test_default_excludes_optional(self, tmp_path):
        self._write_pyproject(tmp_path)
        names = self._packages(tmp_path, self._make_args(directory=str(tmp_path)))
        assert names == ["requests"]

    def test_with_dev_includes_optional(self, tmp_path):
        self._write_pyproject(tmp_path)
        names = self._packages(tmp_path, self._make_args(directory=str(tmp_path), with_dev=True))
        assert names == ["black", "protobuf", "pytest", "requests"]

    def test_without_optional_excludes_even_with_dev(self, tmp_path):
        self._write_pyproject(tmp_path)
        names = self._packages(
            tmp_path,
            self._make_args(directory=str(tmp_path), with_dev=True, without_optional=True),
        )
        assert names == ["requests"]
