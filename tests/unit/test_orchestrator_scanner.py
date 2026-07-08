"""Unit tests for orchestrator/scanner.py."""

import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.orchestrator.scanner import _safe_extractall


class TestSafeExtractall:
    def test_normal_extraction(self):
        with TemporaryDirectory() as tmp:
            z_data = io.BytesIO()
            with zipfile.ZipFile(z_data, "w") as zf:
                zf.writestr("normal_file.txt", "hello")
                zf.writestr("subdir/other.txt", "world")
            target = Path(tmp)
            z = zipfile.ZipFile(io.BytesIO(z_data.getvalue()))
            _safe_extractall(z, target)
            assert (target / "normal_file.txt").exists()
            assert (target / "subdir" / "other.txt").exists()
            assert (target / "normal_file.txt").read_text() == "hello"

    def test_path_traversal_detected(self):
        with TemporaryDirectory() as tmp:
            z_data = io.BytesIO()
            with zipfile.ZipFile(z_data, "w") as zf:
                zf.writestr("../outside.txt", "dangerous")
            target = Path(tmp)
            z = zipfile.ZipFile(io.BytesIO(z_data.getvalue()))
            with pytest.raises(ValueError, match="Path traversal"):
                _safe_extractall(z, target)

    def test_path_traversal_with_abs(self):
        with TemporaryDirectory() as tmp:
            z_data = io.BytesIO()
            with zipfile.ZipFile(z_data, "w") as zf:
                zf.writestr("/etc/passwd", "fake")
            target = Path(tmp)
            z = zipfile.ZipFile(io.BytesIO(z_data.getvalue()))
            with pytest.raises(ValueError, match="Path traversal"):
                _safe_extractall(z, target)

    def test_deeply_nested_safe(self):
        with TemporaryDirectory() as tmp:
            z_data = io.BytesIO()
            with zipfile.ZipFile(z_data, "w") as zf:
                zf.writestr("a/b/c/d/e/f/g/h/file.txt", "deep")
            target = Path(tmp)
            z = zipfile.ZipFile(io.BytesIO(z_data.getvalue()))
            _safe_extractall(z, target)
            assert (target / "a/b/c/d/e/f/g/h/file.txt").exists()

    def test_duplicate_entries(self):
        with TemporaryDirectory() as tmp:
            z_data = io.BytesIO()
            with zipfile.ZipFile(z_data, "w") as zf:
                zf.writestr("dup.txt", "first")
                zf.writestr("dup.txt", "second")
            target = Path(tmp)
            z = zipfile.ZipFile(io.BytesIO(z_data.getvalue()))
            _safe_extractall(z, target)
            assert (target / "dup.txt").exists()


class TestDownloadGithubRepo:
    @pytest.mark.asyncio
    async def test_invalid_url_raises(self):
        from backend.orchestrator.scanner import _download_github_repo

        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            await _download_github_repo("https://example.com/not-github", "main")
