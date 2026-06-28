"""Tests for the CLI pipeline functions in backend/cli.py."""

import argparse
import io
import json
import sys
from unittest.mock import patch

import pytest

from backend.cli import (
    _parse_package_spec,
    _extract_cuda_variants,
    _select_best_cuda_variant,
    _aggregator_to_resolver_input,
    _output_json,
)


class TestParsePackageSpec:
    def test_basic_pypi_default(self):
        name, eco = _parse_package_spec("numpy")
        assert name == "numpy"
        assert eco == "pypi"

    def test_with_ecosystem(self):
        name, eco = _parse_package_spec("express@npm")
        assert name == "express"
        assert eco == "npm"

    def test_custom_default(self):
        name, eco = _parse_package_spec("tokio", default_ecosystem="crates")
        assert name == "tokio"
        assert eco == "crates"

    def test_with_ecosystem_overrides_default(self):
        name, eco = _parse_package_spec("numpy@conda", default_ecosystem="pypi")
        assert name == "numpy"
        assert eco == "conda"

    def test_multiple_at_signs(self):
        name, eco = _parse_package_spec("scoped@stuff@npm")
        assert name == "scoped@stuff"
        assert eco == "npm"

    def test_empty_string(self):
        name, eco = _parse_package_spec("")
        assert name == ""


class TestExtractCudaVariants:
    def test_no_variants(self):
        versions = [{"version": "2.0.0"}, {"version": "2.0.1"}]
        result = _extract_cuda_variants(versions, "2.0.0")
        assert result == []

    def test_matching_variants(self):
        versions = [
            {"version": "2.0.0"},
            {"version": "2.0.0+cu118"},
            {"version": "2.0.0+cu121"},
            {"version": "2.0.1+cu118"},
        ]
        result = _extract_cuda_variants(versions, "2.0.0")
        assert len(result) == 2
        assert {"version": "2.0.0+cu118", "cuda_version": "118"} in result
        assert {"version": "2.0.0+cu121", "cuda_version": "121"} in result

    def test_no_base_version_match(self):
        versions = [{"version": "1.0.0+cu118"}]
        result = _extract_cuda_variants(versions, "2.0.0")
        assert result == []


class TestSelectBestCudaVariant:
    def test_no_variants(self):
        assert _select_best_cuda_variant([], "12.1") is None

    def test_no_system_cuda_returns_first(self):
        variants = [
            {"version": "2.0.0+cu118", "cuda_version": "118"},
            {"version": "2.0.0+cu121", "cuda_version": "121"},
        ]
        result = _select_best_cuda_variant(variants, None)
        assert result == "2.0.0+cu118"

    def test_exact_match(self):
        variants = [
            {"version": "2.0.0+cu118", "cuda_version": "118"},
            {"version": "2.0.0+cu121", "cuda_version": "121"},
        ]
        result = _select_best_cuda_variant(variants, "12.1")
        assert result == "2.0.0+cu121"

    def test_fallback_to_compatible(self):
        variants = [
            {"version": "2.0.0+cu118", "cuda_version": "118"},
            {"version": "2.0.0+cu121", "cuda_version": "121"},
        ]
        result = _select_best_cuda_variant(variants, "12.0")
        # cu118 (11.8) <= 12.0, cu121 (12.1) > 12.0 → only cu118 is compatible
        assert result == "2.0.0+cu118"

    def test_no_compatible_version(self):
        variants = [{"version": "2.0.0+cu120", "cuda_version": "120"}]
        result = _select_best_cuda_variant(variants, "11.8")
        assert result == "2.0.0+cu120"  # fall back to first

    def test_empty_variants(self):
        assert _select_best_cuda_variant([], "12.1") is None


class TestAggregatorToResolverInput:
    def test_basic_conversion(self):
        Dep = type("Dep", (), {"name": "urllib3", "version_spec": ">=1.21.1,<3"})
        Req = type("Req", (), {"type": "runtime", "name": "python", "version_spec": ">=3.7"})
        agg_data = {
            "name": "requests",
            "ecosystem": {"pypi": {"system_requirements": {}}},
            "versions": {
                "pypi": [{"version": "2.31.0"}, {"version": "2.28.0"}]
            },
            "dependencies": {
                "pypi": {
                    "all": [Dep()]
                }
            },
            "system_requirements": {
                "pypi": [Req()]
            },
        }
        result = _aggregator_to_resolver_input(agg_data, "pypi")
        assert result["name"] == "requests"
        assert result["ecosystem"] == "pypi"
        assert "2.31.0" in result["available_versions"]
        assert "2.28.0" in result["available_versions"]
        assert "urllib3" in result["dependencies"]["pypi"]
        assert result["system_requirements"]["python"]["min_version"] == "3.7"

    def test_cuda_variants_excluded(self):
        agg_data = {
            "name": "torch",
            "ecosystem": {"pypi": {"system_requirements": {}}},
            "versions": {
                "pypi": [
                    {"version": "2.1.0"},
                    {"version": "2.1.0+cu118"},
                    {"version": "2.1.0+cu121"},
                ]
            },
            "dependencies": {"pypi": {"all": []}},
            "system_requirements": {"pypi": []},
        }
        result = _aggregator_to_resolver_input(agg_data, "pypi")
        assert "2.1.0" in result["available_versions"]
        assert "2.1.0+cu118" not in result["available_versions"]
        assert "2.1.0+cu121" not in result["available_versions"]

    def test_cuda_system_requirements(self):
        agg_data = {
            "name": "torch",
            "ecosystem": {
                "pypi": {
                    "system_requirements": {"cuda": {"min_version": "11.7"}}
                }
            },
            "versions": {"pypi": [{"version": "2.1.0"}]},
            "dependencies": {"pypi": {"all": []}},
            "system_requirements": {"pypi": []},
        }
        result = _aggregator_to_resolver_input(agg_data, "pypi")
        assert "cuda" in result["system_requirements"]
        assert result["system_requirements"]["cuda"]["min_version"] == "11.7"


class TestCliArgumentParsing:
    """Test that CLI argument parsing works correctly."""

    def test_serve_default_mode(self):
        from backend.cli import _build_parser
        p = _build_parser()
        args = p.parse_args(["serve"])
        assert args.command == "serve"
        assert args.mode == "local"

    def test_check_defaults(self):
        from backend.cli import _build_parser
        p = _build_parser()
        args = p.parse_args(["check"])
        assert args.command == "check"
        assert not args.verbose
        assert not args.json

    def test_check_json_flag(self):
        from backend.cli import _build_parser
        p = _build_parser()
        args = p.parse_args(["check", "--json"])
        assert args.json

    def test_info_json_flag(self):
        from backend.cli import _build_parser
        p = _build_parser()
        args = p.parse_args(["info", "--json"])
        assert args.command == "info"
        assert args.json

    def test_lock_json_flag(self):
        from backend.cli import _build_parser
        p = _build_parser()
        args = p.parse_args(["lock", "--json"])
        assert args.command == "lock"
        assert args.json

    def test_lock_dry_run(self):
        from backend.cli import _build_parser
        p = _build_parser()
        args = p.parse_args(["lock", "--dry-run"])
        assert args.dry_run

    def test_resolve_format_json(self):
        from backend.cli import _build_parser
        p = _build_parser()
        args = p.parse_args(["resolve", "numpy", "--format", "json"])
        assert args.command == "resolve"
        assert args.format == "json"
        assert args.packages == ["numpy"]

    def test_resolve_interactive(self):
        from backend.cli import _build_parser
        p = _build_parser()
        args = p.parse_args(["resolve", "numpy@pypi", "express@npm", "-i"])
        assert args.command == "resolve"
        assert args.interactive
        assert args.packages == ["numpy@pypi", "express@npm"]


class TestOutputJson:
    """Test the _output_json helper function."""

    def test_output_json_exits_zero(self):
        data = {"key": "value"}
        with patch.object(sys, 'stdout') as mock_stdout:
            with pytest.raises(SystemExit) as exc:
                _output_json(data, argparse.Namespace())
            assert exc.value.code == 0

    def test_output_json_writes_valid_json(self):
        data = {"packages": ["a", "b"], "count": 2}
        string_out = io.StringIO()
        with patch.object(sys, 'stdout', string_out):
            try:
                _output_json(data, argparse.Namespace())
            except SystemExit:
                pass
        parsed = json.loads(string_out.getvalue())
        assert parsed == data

    def test_output_json_with_nested_data(self):
        data = {"resolved": {"pkg": {"version": "1.0", "ecosystem": "pypi"}}}
        string_out = io.StringIO()
        with patch.object(sys, 'stdout', string_out):
            try:
                _output_json(data, argparse.Namespace())
            except SystemExit:
                pass
        parsed = json.loads(string_out.getvalue())
        assert parsed["resolved"]["pkg"]["version"] == "1.0"
