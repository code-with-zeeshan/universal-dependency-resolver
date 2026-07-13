"""Tests for the CLI pipeline functions in backend/cli.py."""

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from rich.table import Table

from backend.cli import (
    _aggregator_to_resolver_input,
    _extract_cuda_variants,
    _output_json,
    _parse_package_spec,
    _select_best_cuda_variant,
)
from backend.cli.shared import (
    _build_resolved_table,
    _extract_severity,
    _generate_install_command,
    _read_lock_file,
    _validate_manifest_update_line,
)
from backend.orchestrator import _apply_cuda_variants


class TestParsePackageSpec:
    def test_basic_pypi_default(self):
        name, eco, constraint = _parse_package_spec("numpy")
        assert name == "numpy"
        assert eco == "pypi"
        assert constraint is None

    def test_with_ecosystem(self):
        name, eco, constraint = _parse_package_spec("express@npm")
        assert name == "express"
        assert eco == "npm"
        assert constraint is None

    def test_custom_default(self):
        name, eco, constraint = _parse_package_spec("tokio", default_ecosystem="crates")
        assert name == "tokio"
        assert eco == "crates"
        assert constraint is None

    def test_with_ecosystem_overrides_default(self):
        name, eco, constraint = _parse_package_spec("numpy@conda", default_ecosystem="pypi")
        assert name == "numpy"
        assert eco == "conda"
        assert constraint is None

    def test_multiple_at_signs(self):
        name, eco, constraint = _parse_package_spec("scoped@stuff@npm")
        assert name == "scoped@stuff"
        assert eco == "npm"
        assert constraint is None

    def test_empty_string(self):
        name, _eco, constraint = _parse_package_spec("")
        assert name == ""
        assert constraint is None


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
            "versions": {"pypi": [{"version": "2.31.0"}, {"version": "2.28.0"}]},
            "dependencies": {"pypi": {"all": [Dep()]}},
            "system_requirements": {"pypi": [Req()]},
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
            "ecosystems": {"pypi": {"system_requirements": {"cuda": {"min_version": "11.7"}}}},
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

    def test_check_json_flag(self):
        from backend.cli import _build_parser

        p = _build_parser()
        args = p.parse_args(["check", "--json"])
        assert args.command == "check"
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
        with patch.object(sys, "stdout"):
            with pytest.raises(SystemExit) as exc:
                _output_json(data, argparse.Namespace())
            assert exc.value.code == 0

    def test_output_json_writes_valid_json(self):
        data = {"packages": ["a", "b"], "count": 2}
        string_out = io.StringIO()
        with patch.object(sys, "stdout", string_out), contextlib.suppress(SystemExit):
            _output_json(data, argparse.Namespace())
        parsed = json.loads(string_out.getvalue())
        assert parsed == data

    def test_output_json_with_nested_data(self):
        data = {"resolved": {"pkg": {"version": "1.0", "ecosystem": "pypi"}}}
        string_out = io.StringIO()
        with patch.object(sys, "stdout", string_out), contextlib.suppress(SystemExit):
            _output_json(data, argparse.Namespace())
        parsed = json.loads(string_out.getvalue())
        assert parsed["resolved"]["pkg"]["version"] == "1.0"


class TestExtractSeverity:
    def test_list_severity_with_score(self):
        assert _extract_severity({"severity": [{"score": "HIGH"}]}) == "HIGH"

    def test_list_severity_with_type(self):
        assert _extract_severity({"severity": [{"type": "MEDIUM"}]}) == "MEDIUM"

    def test_string_severity(self):
        assert _extract_severity({"severity": "CRITICAL"}) == "CRITICAL"

    def test_empty_severity_list(self):
        assert _extract_severity({"severity": []}) == "UNKNOWN"

    def test_missing_severity(self):
        assert _extract_severity({}) == "UNKNOWN"


class TestBuildResolvedTable:
    def test_returns_table_with_packages(self):
        resolved = {
            "resolved_packages": {
                "requests": {"version": "2.31.0", "ecosystem": "pypi"},
                "express": {"version": "4.18.0", "ecosystem": "npm"},
            }
        }
        table = _build_resolved_table(resolved)
        assert isinstance(table, Table)
        assert table.row_count == 2

    def test_returns_none_for_empty(self):
        assert _build_resolved_table({}) is None

    def test_cuda_notes_column(self):
        resolved = {
            "resolved_packages": {
                "torch": {"version": "2.1.0+cu121", "ecosystem": "pypi", "cuda_version": "121"},
            }
        }
        table = _build_resolved_table(resolved)
        assert table is not None
        assert table.row_count == 1


class TestReadLockFile:
    def test_reads_valid_lock_file(self, tmp_path):
        lock = tmp_path / "udr.lock"
        lock.write_text(json.dumps({"version": "2.0", "packages": {}}))
        data = _read_lock_file(Path(str(lock)))
        assert data["version"] == "2.0"

    def test_exits_on_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.lock"
        with pytest.raises(SystemExit):
            _read_lock_file(Path(str(missing)))

    def test_exits_on_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.lock"
        bad.write_text("not json")
        with pytest.raises(SystemExit):
            _read_lock_file(Path(str(bad)))

    def test_exits_on_unsupported_version(self, tmp_path):
        lock = tmp_path / "udr.lock"
        lock.write_text(json.dumps({"version": "9.9", "packages": {}}))
        with pytest.raises(SystemExit):
            _read_lock_file(Path(str(lock)))


class TestValidateManifestUpdateLine:
    def test_empty_line(self):
        assert _validate_manifest_update_line("", "numpy", "1.0") is None

    def test_comment_line(self):
        assert _validate_manifest_update_line("# numpy==1.0", "numpy", "1.0") is None

    def test_flag_line(self):
        assert _validate_manifest_update_line("-r base.txt", "numpy", "1.0") is None

    def test_updates_double_quoted(self):
        result = _validate_manifest_update_line('"numpy"==1.0', "numpy", "2.0")
        assert result == '"numpy==2.0"'

    def test_updates_single_quoted(self):
        result = _validate_manifest_update_line("'numpy'>=1.0", "numpy", "2.0")
        assert result == "'numpy==2.0'"

    def test_updates_unquoted(self):
        result = _validate_manifest_update_line("numpy==1.0", "numpy", "2.0")
        assert result == "numpy==2.0"

    def test_no_match_different_package(self):
        result = _validate_manifest_update_line("pandas==1.0", "numpy", "2.0")
        assert result is None

    def test_updates_with_trailing_comment(self):
        result = _validate_manifest_update_line("numpy==1.0 # pinned", "numpy", "2.0")
        assert "# pinned" in result

    def test_updates_spaced_format(self):
        result = _validate_manifest_update_line("numpy 1.0", "numpy", "2.0")
        assert result == "numpy==2.0"

    def test_updates_with_operator(self):
        result = _validate_manifest_update_line("numpy >=1.0", "numpy", "2.0")
        assert result == "numpy==2.0"


class TestGenerateInstallCommand:
    def test_pypi(self):
        cmd = _generate_install_command("pypi", [("requests", "2.31.0")])
        assert cmd is not None
        assert "pip install" in cmd
        assert "requests==2.31.0" in cmd

    def test_npm(self):
        cmd = _generate_install_command("npm", [("express", "4.18.0")])
        assert cmd is not None
        assert "npm install" in cmd

    def test_unknown_ecosystem(self):
        cmd = _generate_install_command("unknown", [("pkg", "1.0")])
        assert cmd is None

    def test_multi_package(self):
        cmd = _generate_install_command("pypi", [("a", "1.0"), ("b", "2.0")])
        assert cmd is not None
        assert "a==1.0" in cmd
        assert "b==2.0" in cmd


class TestApplyCudaVariants:
    def test_no_gpu_no_cuda_skipped(self):
        resolved = {"resolved_packages": {"numpy": {"version": "1.0", "ecosystem": "pypi"}}}
        result = _apply_cuda_variants(resolved, {}, {})
        assert result["resolved_packages"]["numpy"]["version"] == "1.0"

    def test_non_pypi_ecosystem_skipped(self):
        resolved = {"resolved_packages": {"express": {"version": "4.0", "ecosystem": "npm"}}}
        result = _apply_cuda_variants(resolved, {}, {})
        assert result["resolved_packages"]["express"]["version"] == "4.0"

    def test_no_cuda_variants_available(self):
        resolved = {"resolved_packages": {"torch": {"version": "2.1.0", "ecosystem": "pypi"}}}
        details = {"torch": {"versions": {"pypi": [{"version": "2.1.0"}]}}}
        system = {"gpu": {"cuda": "12.1"}}
        result = _apply_cuda_variants(resolved, details, system)
        assert result["resolved_packages"]["torch"]["version"] == "2.1.0"

    def test_selects_cuda_variant(self):
        resolved = {"resolved_packages": {"torch": {"version": "2.1.0", "ecosystem": "pypi"}}}
        details = {
            "torch": {
                "versions": {
                    "pypi": [
                        {"version": "2.1.0"},
                        {"version": "2.1.0+cu118"},
                        {"version": "2.1.0+cu121"},
                    ]
                }
            }
        }
        system = {"gpu": {"cuda": "12.1"}}
        result = _apply_cuda_variants(resolved, details, system)
        pkg = result["resolved_packages"]["torch"]
        assert pkg["version"] == "2.1.0+cu121"
        assert pkg["cuda_variant"] is True
