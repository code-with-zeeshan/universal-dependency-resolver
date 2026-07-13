"""Regression tests for content-based manifest detection and annotation parsing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.core.config_loader import (
    apply_annotation_overrides,
    extract_annotations,
)
from backend.core.content_detector import sniff_content, suggest_parsers


class TestSniffContent:
    def test_json_content(self, tmp_path: Path):
        p = tmp_path / "unknown.lock"
        p.write_text(json.dumps({"packages": []}))
        result = sniff_content(str(p))
        assert result is not None

    def test_xml_content(self, tmp_path: Path):
        p = tmp_path / "unknown.xml"
        p.write_text("<project><dependencies></dependencies></project>")
        result = sniff_content(str(p))
        assert result is not None

    def test_unknown_content(self, tmp_path: Path):
        p = tmp_path / "binary.dat"
        p.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd\xfc")
        result = sniff_content(str(p))
        # Should not crash; result can be None for unrecognised content
        assert result is None or isinstance(result, str)

    def test_empty_file(self, tmp_path: Path):
        p = tmp_path / "empty.txt"
        p.write_text("")
        result = sniff_content(str(p))
        assert result is None or isinstance(result, str)

    def test_nonexistent_file(self):
        result = sniff_content("/nonexistent/path/file.txt")
        assert result is None


class TestSuggestParsers:
    def test_json_type(self):
        parsers = suggest_parsers("json")
        assert isinstance(parsers, list)
        assert len(parsers) > 0
        assert "package_lock" in parsers

    def test_xml_type(self):
        parsers = suggest_parsers("xml")
        assert "maven" in parsers or "nuget" in parsers

    def test_unknown_type(self):
        parsers = suggest_parsers("application/octet-stream")
        assert parsers == []


class TestExtractAnnotations:
    def test_basic_annotation(self):
        result = extract_annotations("click>=8.0  # udr:ecosystem=pypi")
        assert result == {"ecosystem": "pypi"}

    def test_no_annotation(self):
        result = extract_annotations("click>=8.0")
        assert result == {}

    def test_multiple_annotations(self):
        result = extract_annotations("my-pkg  # udr:ecosystem=npm udr:extras=dev")
        assert result == {"ecosystem": "npm", "extras": "dev"}

    def test_non_udr_comment(self):
        result = extract_annotations("click>=8.0  # not a udr annotation")
        assert result == {}

    def test_line_without_comment(self):
        result = extract_annotations("requests")
        assert result == {}


class TestApplyAnnotationOverrides:
    def test_overrides_ecosystem(self):
        packages = [{"name": "click", "version": "8.0"}]
        content = "click>=8.0  # udr:ecosystem=npm"
        result = apply_annotation_overrides(packages, content)
        assert result[0].get("_ecosystem") == "npm"

    def test_preserves_no_annotation(self):
        packages = [{"name": "click", "version": "8.0"}]
        content = "click>=8.0"
        result = apply_annotation_overrides(packages, content)
        assert "_ecosystem" not in result[0]

    def test_multiple_packages(self):
        packages = [
            {"name": "click", "version": "8.0"},
            {"name": "flask", "version": "2.0"},
        ]
        content = "click>=8.0\nflask>=2.0  # udr:ecosystem=pypi"
        result = apply_annotation_overrides(packages, content)
        assert result[1].get("_ecosystem") == "pypi"

    def test_extras_annotation(self):
        packages = [{"name": "numpy", "version": "1.21"}]
        content = "numpy>=1.21  # udr:extras=all"
        result = apply_annotation_overrides(packages, content)
        assert "all" in result[0].get("extras", [])
