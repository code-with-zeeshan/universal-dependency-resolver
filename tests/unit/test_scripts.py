"""Unit tests for scripts/ — tests for self-contained scripts.

Skips scripts that require external tools (git, gh, network) or
are too tightly coupled to the repo (bump_version, seed_db, benchmark).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"


# ── generate_badge.py ─────────────────────────────────────────────────────────


class TestGenerateBadge:
    @pytest.fixture(autouse=True)
    def _import(self):
        sys.path.insert(0, str(SCRIPTS))
        yield
        sys.path.pop(0)

    def test_generate_badge_basic(self):
        from generate_badge import generate_badge

        svg = generate_badge("tests", "42 passed", "green")
        assert '<?xml version="1.0" encoding="UTF-8"?>' in svg
        assert 'width="' in svg
        assert "42 passed" in svg
        assert "tests" in svg
        assert "green" in svg

    def test_generate_badge_different_colors(self):
        from generate_badge import generate_badge

        for color in ("red", "#dfb317", "blue"):
            svg = generate_badge("x", "y", color)
            assert color in svg

    def test_generate_badge_empty_value(self):
        from generate_badge import generate_badge

        svg = generate_badge("label", "", "green")
        assert "label" in svg

    def test_text_width(self):
        from generate_badge import _text_width

        assert _text_width("") >= 10
        assert _text_width("iiiii") < _text_width("WWWWW")
        assert _text_width("hello") > 0

    def test_main_help(self, capsys):
        from generate_badge import main

        old_argv = sys.argv
        sys.argv = ["generate_badge.py", "--help"]
        try:
            with pytest.raises(SystemExit):
                main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "usage:" in captured.out or "label" in captured.out

    def test_main_with_args(self, capsys):
        from generate_badge import main

        old_argv = sys.argv
        sys.argv = ["generate_badge.py", "--label", "tests", "--value", "100", "--color", "green"]
        try:
            main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "100" in captured.out
        assert "tests" in captured.out
        assert "green" in captured.out

    def test_generate_badge_standalone(self):
        from generate_badge import generate_badge

        svg = generate_badge("coverage", "80%", "green")
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg
        assert "coverage" in svg
        assert "80%" in svg


# ── sync-version.py ───────────────────────────────────────────────────────────


class TestSyncVersion:
    def test_sync_version_regex_matches(self):
        text = '[project]\nversion = "1.2.3"\n'
        import re

        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        assert m is not None
        assert m.group(1) == "1.2.3"

    def test_sync_version_regex_no_match(self):
        text = "[tool.ruff]\nline-length = 100\n"
        import re

        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        assert m is None

    def test_sync_version_updates_json(self, tmp_path: Path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "1.2.3"\n')
        pkg_dir = tmp_path / "desktop"
        pkg_dir.mkdir()
        pkg_json = pkg_dir / "package.json"
        pkg_json.write_text(json.dumps({"version": "0.0.1", "name": "udr-desktop"}))

        import re

        text = pyproject.read_text()
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        assert m is not None
        version = m.group(1)
        pkg = json.loads(pkg_json.read_text())
        old_version = pkg.get("version")
        if old_version != version:
            pkg["version"] = version
            pkg_json.write_text(json.dumps(pkg, indent=2) + "\n")

        updated = json.loads(pkg_json.read_text())
        assert updated["version"] == "1.2.3"

    def test_sync_version_skips_when_same(self, tmp_path: Path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "1.2.3"\n')
        pkg_dir = tmp_path / "desktop"
        pkg_dir.mkdir()
        pkg_json = pkg_dir / "package.json"
        pkg_json.write_text(json.dumps({"version": "1.2.3", "name": "udr-desktop"}))

        import re

        text = pyproject.read_text()
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        assert m is not None
        version = m.group(1)
        pkg = json.loads(pkg_json.read_text())
        assert pkg["version"] == version  # already same, no update needed


# ── extract_changelog.py ──────────────────────────────────────────────────────


class TestExtractChangelog:
    """Test extract_changelog.py regex logic and section extraction."""

    SCRIPT = SCRIPTS / "extract_changelog.py"

    def test_extract_section_found(self, tmp_path: Path):
        changelog = (
            "# Changelog\n\n## [1.0.0]\n\n### Added\n- Initial release\n\n## [0.9.0]\n\n### Fixed\n- Bug\n"
        )
        ch_path = tmp_path / "CHANGELOG.md"
        ch_path.write_text(changelog)

        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), "1.0.0"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert "Initial release" in result.stdout

    def test_extract_section_not_found(self, tmp_path: Path):
        changelog = "# Changelog\n\n## [1.0.0]\n\n### Added\n- Initial release\n"
        ch_path = tmp_path / "CHANGELOG.md"
        ch_path.write_text(changelog)

        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), "2.0.0"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 1
        assert "No changelog" in result.stderr

    def test_extract_requires_version_arg(self, tmp_path: Path):
        # Create dummy CHANGELOG.md so the script doesn't fail on missing file
        ch_path = tmp_path / "CHANGELOG.md"
        ch_path.write_text("# Changelog\n\n## [1.0.0]\n\n### Added\n- Initial\n")

        result = subprocess.run(
            [sys.executable, str(self.SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 1
        assert "Usage:" in result.stderr

    def test_extract_regex_pattern(self):
        import re

        text = "## [1.0.0]\n### Added\n- Initial release\n"
        m = re.match(r"^## \[(\d+\.\d+\.\d+)\]", text)
        assert m is not None
        assert m.group(1) == "1.0.0"

    def test_extract_regex_no_match(self):
        import re

        text = "## Unreleased\n### Added\n- Initial release\n"
        m = re.match(r"^## \[(\d+\.\d+\.\d+)\]", text)
        assert m is None


# ── check_arch_imports.py ─────────────────────────────────────────────────────


class TestCheckArchImports:
    def test_check_clean_file(self, tmp_path: Path):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import check_arch_imports

            repo = tmp_path / "repo"
            backend = repo / "backend"
            src = backend / "core"
            src.mkdir(parents=True)
            f = src / "utils.py"
            f.write_text("import os\nimport json\nfrom pathlib import Path\n")

            old_backend = check_arch_imports.BACKEND
            check_arch_imports.BACKEND = backend
            try:
                violations = check_arch_imports._check_file(f)
                assert violations == []
            finally:
                check_arch_imports.BACKEND = old_backend
        finally:
            sys.path.pop(0)

    def test_check_violation(self, tmp_path: Path):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import check_arch_imports

            repo = tmp_path / "repo"
            backend = repo / "backend"
            src = backend / "cli"
            src.mkdir(parents=True)
            f = src / "some_cmd.py"
            # Direct import of a forbidden layer — "api" is forbidden for "cli"
            f.write_text("import os\nimport api\n")

            old_backend = check_arch_imports.BACKEND
            check_arch_imports.BACKEND = backend
            try:
                violations = check_arch_imports._check_file(f)
                assert len(violations) > 0
                assert "api" in violations[0]
            finally:
                check_arch_imports.BACKEND = old_backend
        finally:
            sys.path.pop(0)

    def test_get_layer(self, tmp_path: Path):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import check_arch_imports

            repo = tmp_path / "repo"
            backend = repo / "backend"
            (backend / "cli" / "commands").mkdir(parents=True)
            (backend / "core").mkdir(parents=True)

            p = backend / "cli" / "commands" / "lock.py"
            p.touch()
            old_backend = check_arch_imports.BACKEND
            check_arch_imports.BACKEND = backend
            try:
                assert check_arch_imports._get_layer(p) == "cli"
                p2 = backend / "core" / "conflict_resolver.py"
                p2.touch()
                assert check_arch_imports._get_layer(p2) == "core"
                p3 = repo / "tests" / "test_foo.py"
                p3.parent.mkdir(parents=True)
                p3.touch()
                assert check_arch_imports._get_layer(p3) is None
            finally:
                check_arch_imports.BACKEND = old_backend
        finally:
            sys.path.pop(0)

    def test_is_exempted(self, tmp_path: Path):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import check_arch_imports

            repo = tmp_path / "repo"
            backend = repo / "backend"
            p = backend / "cli" / "commands" / "serve.py"
            p.parent.mkdir(parents=True)
            p.touch()

            old_backend = check_arch_imports.BACKEND
            check_arch_imports.BACKEND = backend
            try:
                assert check_arch_imports._is_exempted(p) is True
            finally:
                check_arch_imports.BACKEND = old_backend
        finally:
            sys.path.pop(0)

    def test_is_test_file(self, tmp_path: Path):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import check_arch_imports

            repo = tmp_path / "repo"
            backend = repo / "backend"
            old_backend = check_arch_imports.BACKEND
            check_arch_imports.BACKEND = backend
            try:
                assert check_arch_imports._is_test_file(repo / "tests" / "test_foo.py")
                assert check_arch_imports._is_test_file(backend / "tests" / "test_foo.py")
                assert not check_arch_imports._is_test_file(backend / "cli" / "main.py")
            finally:
                check_arch_imports.BACKEND = old_backend
        finally:
            sys.path.pop(0)

    def test_normalize_import(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import check_arch_imports

            assert check_arch_imports._normalize_import("os") == "os"
            assert check_arch_imports._normalize_import("backend.api.routes") == "backend"
            assert check_arch_imports._normalize_import("a.b.c.d") == "a"
        finally:
            sys.path.pop(0)

    def test_main_clean(self, tmp_path: Path):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import check_arch_imports

            old_backend = check_arch_imports.BACKEND
            check_arch_imports.BACKEND = tmp_path
            try:
                rc = check_arch_imports.main()
                assert rc == 0
            finally:
                check_arch_imports.BACKEND = old_backend
        finally:
            sys.path.pop(0)
