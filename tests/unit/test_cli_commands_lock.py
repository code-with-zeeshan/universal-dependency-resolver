import pytest

from backend.cli.commands.lock import _extract_integrity


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
