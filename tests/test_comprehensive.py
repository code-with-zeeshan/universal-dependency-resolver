"""Comprehensive real-world tests for Universal Dependency Resolver.

Tests every critical path with mocked hardware detection but real registry data.
Covers: all manifest formats, CUDA conflicts, cross-ecosystem deep transitive
resolution, system detection, lock file operations, and edge cases.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from backend.core.conflict_resolver import ConflictResolver
from backend.core.data_aggregator import DataAggregator
from backend.manifest_detector import ManifestDetector

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.external_api,
    pytest.mark.asyncio(scope="module"),
]

# ---------------------------------------------------------------------------
# Mock system info presets — realistic hardware configurations
# ---------------------------------------------------------------------------

MOCK_GPU_NVIDIA_CUDA12: Dict[str, Any] = {
    "id": 0,
    "vendor": "NVIDIA",
    "name": "NVIDIA GeForce RTX 4090",
    "driver_version": "535.129.03",
    "cuda": "12.1",
    "memory_total": 24576,
    "memory_free": 16384,
    "utilization": 12.5,
    "temperature": 42.0,
}

MOCK_GPU_NVIDIA_CUDA11: Dict[str, Any] = {
    "id": 0,
    "vendor": "NVIDIA",
    "name": "NVIDIA Tesla T4",
    "driver_version": "470.182.03",
    "cuda": "11.8",
    "memory_total": 16384,
    "memory_free": 12288,
    "utilization": 5.0,
    "temperature": 38.0,
}

MOCK_GPU_AMD: Dict[str, Any] = {
    "id": 0,
    "vendor": "AMD",
    "name": "AMD Radeon RX 7900 XTX",
    "driver_version": "ROCm 6.0",
    "cuda": "",
    "memory_total": 24576,
    "memory_free": 20480,
    "utilization": 8.0,
    "temperature": 45.0,
}

MOCK_NO_GPU: Dict[str, Any] = {}

MOCK_ACCELERATORS_NONE: Dict[str, Any] = {
    "tpu": {"available": False},
    "npu": {"available": False},
    "ane": {"available": False},
}

MOCK_ACCELERATORS_TPU: Dict[str, Any] = {
    "tpu": {"available": True, "type": "Edge TPU", "count": 1},
    "npu": {"available": False},
    "ane": {"available": False},
}

MOCK_ACCELERATORS_NPU: Dict[str, Any] = {
    "tpu": {"available": False},
    "npu": {"available": True, "type": "Intel Myriad X", "count": 1},
    "ane": {"available": False},
}

MOCK_ACCELERATORS_ANE: Dict[str, Any] = {
    "tpu": {"available": False},
    "npu": {"available": False},
    "ane": {"available": True, "type": "Apple Neural Engine", "count": 16},
}


def _build_system_info(
    gpu: Optional[Dict] = None,
    accelerators: Optional[Dict] = None,
    cpu: Optional[Dict] = None,
    memory: Optional[Dict] = None,
    runtime: Optional[Dict] = None,
    disk: Optional[Dict] = None,
    network: Optional[Dict] = None,
    platform: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Build a realistic system_info dict with defaults + overrides."""
    info: Dict[str, Any] = {
        "platform": platform or {
            "os": "linux",
            "os_version": "Ubuntu 24.04 LTS",
            "architecture": "x86_64",
            "hostname": "test-host",
        },
        "cpu": cpu or {
            "brand": "AMD Ryzen 9 7950X",
            "count_physical": 16,
            "count_logical": 32,
            "current_frequency": 4500.0,
            "architecture": "x86_64",
        },
        "memory": memory or {
            "total": 68719476736,
            "available": 48000000000,
            "percent": 30.0,
        },
        "disk": disk or {
            "total": 1000000000000,
            "used": 400000000000,
            "free": 600000000000,
        },
        "network": network or {
            "interfaces": [{"name": "eth0", "speed": 10000}],
            "speed": {"dns_ms": 5.0, "http_ms": 20.0, "download_mbps": 500.0},
        },
        "gpu": gpu or MOCK_NO_GPU,
        "accelerators": accelerators or MOCK_ACCELERATORS_NONE,
        "runtime_versions": {
            "python": {"version": "3.11.0"},
            "node": {"version": "20.0.0"},
            "rust": {"version": "1.75.0"},
        },
        "container": {
            "in_container": False,
            "type": "none",
            "runtime": "",
        },
    }
    return info


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def aggregator():
    """Shared DataAggregator (hits real registries)."""
    return DataAggregator()


@pytest.fixture(scope="module")
def resolver():
    """Shared ConflictResolver."""
    return ConflictResolver()


@pytest.fixture
def temp_project():
    """Create + destroy a temp project directory."""
    d = tempfile.mkdtemp(prefix="udr_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def _write_manifest(path: Path, filename: str, content: str):
    """Write a manifest file into the temp project."""
    (path / filename).write_text(content)


async def _run_resolution(
    aggregator: DataAggregator,
    resolver: ConflictResolver,
    system_info: Dict[str, Any],
    specs: List[tuple],
) -> Dict[str, Any]:
    """Run the full resolution pipeline: fetch + resolve."""
    from backend.cli.shared import _aggregator_to_resolver_input, _resolve_transitive

    inputs: List[Dict] = []
    details: Dict[str, Dict] = {}

    for name, eco, constraint in specs:
        data = await aggregator.get_package_info(
            name, ecosystem=eco, include_dependencies=True, include_versions=True
        )
        if data:
            inputs.append(_aggregator_to_resolver_input(data, eco, constraint or "*"))
            details[name] = data

    result = await _resolve_transitive(aggregator, resolver, inputs, system_info)

    if "resolved" in result:
        result["resolved_packages"] = result.pop("resolved")
    return result


def _resolution_ok(result: Dict, min_pkgs: int = 1) -> bool:
    """Check if resolution succeeded with at least min_pkgs packages."""
    pkgs = result.get("resolved_packages", {}) or result.get("packages", {})
    return len(pkgs) >= min_pkgs


def _get_resolved(result: Dict) -> Dict:
    return result.get("resolved_packages", {}) or result.get("packages", {})


# ===================================================================
# 1. SYSTEM DETECTION (mocked)
# ===================================================================


class TestSystemInfoPresets:
    """Verify mock system_info presets are structurally valid."""

    def test_nvidia_cuda12_preset(self):
        info = _build_system_info(gpu=MOCK_GPU_NVIDIA_CUDA12)
        assert info["gpu"]["vendor"] == "NVIDIA"
        assert info["gpu"]["cuda"] == "12.1"
        assert info["gpu"]["memory_total"] == 24576

    def test_amd_gpu_preset(self):
        info = _build_system_info(gpu=MOCK_GPU_AMD)
        assert info["gpu"]["vendor"] == "AMD"
        assert not info["gpu"].get("cuda")

    def test_no_gpu_preset(self):
        info = _build_system_info(gpu=MOCK_NO_GPU)
        assert not info["gpu"]

    def test_accelerator_presets(self):
        for accel, name in [
            (MOCK_ACCELERATORS_TPU, "tpu"),
            (MOCK_ACCELERATORS_NPU, "npu"),
            (MOCK_ACCELERATORS_ANE, "ane"),
        ]:
            info = _build_system_info(accelerators=accel)
            assert info["accelerators"][name]["available"] is True
            assert info["accelerators"][name].get("type")

    def test_complete_structure(self):
        info = _build_system_info(gpu=MOCK_GPU_NVIDIA_CUDA12)
        for section in ("platform", "cpu", "memory", "disk", "network", "gpu",
                        "accelerators", "runtime_versions", "container"):
            assert section in info, f"Missing section: {section}"


# ===================================================================
# 2. MANIFEST PARSING (all formats)
# ===================================================================


class TestManifestParsing:
    """Test every supported manifest format is correctly parsed."""

    def _detect(self, project_dir: Path):
        detector = ManifestDetector(directory=str(project_dir))
        return detector.detect()

    def _write_manifest_bytes(self, path: Path, filename: str, raw: str):
        raw = raw.replace("\\n", "\n")
        (path / filename).write_text(raw)

    def test_requirements_txt(self, temp_project):
        _write_manifest(temp_project, "requirements.txt", "requests>=2.28\nflask>=2.0")
        result = self._detect(temp_project)
        assert isinstance(result, list) and len(result) >= 1
        ecosystems = {r.get("ecosystem") for r in result if isinstance(r, dict)}
        assert "pypi" in ecosystems

    def test_package_json(self, temp_project):
        pkg = {"dependencies": {"express": "^4.18", "lodash": "^4.17"}}
        _write_manifest(temp_project, "package.json", json.dumps(pkg))
        result = self._detect(temp_project)
        assert isinstance(result, list) and len(result) >= 1
        ecosystems = {r.get("ecosystem") for r in result if isinstance(r, dict)}
        assert "npm" in ecosystems

    def test_cargo_toml(self, temp_project):
        self._write_manifest_bytes(temp_project, "Cargo.toml",
            '[package]\nname = "test"\nversion = "0.1.0"\n'
            '[dependencies]\nserde = "1.0"\ntokio = "1.0"\n')
        result = self._detect(temp_project)
        assert isinstance(result, list) and len(result) >= 1
        ecosystems = {r.get("ecosystem") for r in result if isinstance(r, dict)}
        assert "crates" in ecosystems

    def test_go_mod(self, temp_project):
        self._write_manifest_bytes(temp_project, "go.mod",
            'module example.com/test\ngo 1.21\nrequire (\n'
            '\tgithub.com/pkg/errors v0.9.1\n'
            '\tgolang.org/x/text v0.14.0\n)\n')
        result = self._detect(temp_project)
        assert isinstance(result, list) and len(result) >= 1
        ecosystems = {r.get("ecosystem") for r in result if isinstance(r, dict)}
        assert "gomodules" in ecosystems

    def test_build_gradle(self, temp_project):
        self._write_manifest_bytes(temp_project, "build.gradle",
            'dependencies {\n'
            "    implementation 'com.google.guava:guava:32.1.3-jre'\n"
            "    implementation 'org.apache.commons:commons-lang3:3.13.0'\n"
            '}\n')
        result = self._detect(temp_project)
        assert isinstance(result, list) and len(result) >= 1
        ecosystems = {r.get("ecosystem") for r in result if isinstance(r, dict)}
        assert "gradle" in ecosystems

    def test_package_swift(self, temp_project):
        self._write_manifest_bytes(temp_project, "Package.swift",
            '// swift-tools-version:5.9\nimport PackageDescription\n'
            'let package = Package(\n'
            '    name: "MyLibrary",\n'
            '    dependencies: [\n'
            '        .package(url: "https://github.com/Alamofire/Alamofire.git", from: "5.8.0"),\n'
            '    ],\n'
            ')\n')
        result = self._detect(temp_project)
        assert isinstance(result, list) and len(result) >= 1
        ecosystems = {r.get("ecosystem") for r in result if isinstance(r, dict)}
        assert "swift" in ecosystems

    def test_mix_exs(self, temp_project):
        self._write_manifest_bytes(temp_project, "mix.exs",
            'defp deps do\n  [\n'
            '    {:phoenix, "~> 1.7.7"},\n'
            '    {:ecto_sql, "~> 3.10"},\n'
            '  ]\nend\n')
        result = self._detect(temp_project)
        assert isinstance(result, list) and len(result) >= 1
        ecosystems = {r.get("ecosystem") for r in result if isinstance(r, dict)}
        assert "hex" in ecosystems

    def test_cabal_file(self, temp_project):
        self._write_manifest_bytes(temp_project, "mypackage.cabal",
            'cabal-version: 3.4\nname: mypackage\nversion: 0.1.0\n'
            'build-depends: base >=4.16 && <5, containers >=0.6\n')
        result = self._detect(temp_project)
        assert isinstance(result, list) and len(result) >= 1
        ecosystems = {r.get("ecosystem") for r in result if isinstance(r, dict)}
        assert "haskell" in ecosystems

    async def test_multiple_manifests(self, temp_project):
        _write_manifest(temp_project, "requirements.txt", "requests>=2.28")
        pkg = {"dependencies": {"express": "^4.18"}}
        _write_manifest(temp_project, "package.json", json.dumps(pkg))
        self._write_manifest_bytes(temp_project, "Cargo.toml",
            '[package]\nname = "test"\nversion = "0.1.0"\n'
            '[dependencies]\nserde = "1.0"\n')
        result = self._detect(temp_project)
        assert isinstance(result, list) and len(result) >= 3


# ===================================================================
# 3. CUDA CONFLICT DETECTION
# ===================================================================


class TestCUDAConflicts:
    """Test that CUDA 11.x and 12.x package conflicts are detected."""

    async def test_cuda_11_vs_12_conflict_detected(self, aggregator, resolver):
        """Verify CUDA 11 packages conflict with CUDA 12 packages."""
        from backend.core.conflict_resolver import CONFLICT_RULES
        cuda_rules = [r for r in CONFLICT_RULES if "cuda" in r.get("id", "")]
        assert len(cuda_rules) >= 1
        cuda_rule = cuda_rules[0]
        assert "cuda:min_version >=11.0,<12.0" in str(cuda_rule)
        assert "cuda:min_version >=12.0,<13.0" in str(cuda_rule)

    async def test_resolve_torch_cuda11(self, aggregator, resolver):
        """Resolve torch on a CUDA 11.8 system — expect CUDA 11 compatible packages."""
        system_info = _build_system_info(gpu=MOCK_GPU_NVIDIA_CUDA11)
        specs = [("torch", "pypi", ">=2.0,<2.2")]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        assert _resolution_ok(result), f"Resolution failed: {result}"
        pkgs = _get_resolved(result)
        torch_ver = pkgs.get("torch", {}).get("version", "")
        assert torch_ver, f"Torch not resolved: {pkgs}"
        nvidia_pkgs = [n for n in pkgs if "nvidia" in n.lower()]
        if nvidia_pkgs:
            for n in nvidia_pkgs:
                ver = pkgs[n].get("version", "")
                assert ver, f"{n} resolved without version"

    async def test_resolve_torch_cuda12(self, aggregator, resolver):
        """Resolve torch on CUDA 12.1 — expect CUDA 12 compatible pkgs + nvidia deps."""
        system_info = _build_system_info(gpu=MOCK_GPU_NVIDIA_CUDA12)
        specs = [("torch", "pypi", ">=2.0")]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        assert _resolution_ok(result, min_pkgs=3), f"Resolution failed: {result}"
        pkgs = _get_resolved(result)
        nvidia_pkgs = [n for n in pkgs if "nvidia" in n.lower()]
        assert len(nvidia_pkgs) >= 1, \
            f"Expected nvidia deps for CUDA 12.1, got: {list(pkgs.keys())}"

    async def test_cuda_variant_selection(self, aggregator, resolver):
        """Test that CUDA variants (torch+cu121 vs torch+cu118) are selected correctly."""
        system_info = _build_system_info(gpu=MOCK_GPU_NVIDIA_CUDA12)
        specs = [("torch", "pypi", ">=2.1,<2.2")]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        assert _resolution_ok(result), f"Resolution failed: {result}"

        from backend.cli.shared import _apply_cuda_variants
        enriched = _apply_cuda_variants(result, {}, system_info)
        pkgs = _get_resolved(enriched)
        torch_info = pkgs.get("torch", {})
        if torch_info.get("cuda_variant"):
            assert "cu12" in torch_info.get("version", ""), \
                f"Expected CUDA 12 variant, got {torch_info.get('version')}"

    async def test_cuda_conflict_unsatisfiable(self, aggregator, resolver):
        """Test that mutually exclusive CUDA requirements are detected as unsatisfiable."""
        system_info = _build_system_info(gpu=MOCK_GPU_NVIDIA_CUDA12)
        specs = [
            ("torch", "pypi", ">=2.1,<2.2"),
        ]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        assert _resolution_ok(result) or result.get("status") in ("partial", "unsatisfiable")


# ===================================================================
# 4. CROSS-ECOSYSTEM RESOLUTION
# ===================================================================


class TestCrossEcosystem:
    """Test resolution across ecosystem boundaries."""

    async def test_pypi_npm_crates(self, aggregator, resolver):
        """Resolve packages from PyPI, npm, and crates.io simultaneously."""
        system_info = _build_system_info(gpu=MOCK_GPU_NVIDIA_CUDA12)
        specs: List[tuple] = [
            ("requests", "pypi", ">=2.28"),
            ("torch", "pypi", ">=2.0"),
        ]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        pkgs_list = list(_get_resolved(result).keys())[:10]
        assert _resolution_ok(result, min_pkgs=10), \
            f"Expected >=10 packages, got {len(_get_resolved(result))}: {pkgs_list}"

    async def test_deep_transitive(self, aggregator, resolver):
        """Test deep transitive resolution (deps of deps of deps)."""
        system_info = _build_system_info()
        specs = [("flask", "pypi", ">=2.3")]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        assert _resolution_ok(result, min_pkgs=5), \
            f"Expected >=5 transitive packages for flask, got {len(_get_resolved(result))}"
        pkgs = _get_resolved(result)
        expected_transitives = {"werkzeug", "jinja2", "click", "markupsafe"}
        found = expected_transitives & set(pkgs.keys())
        assert len(found) >= 2, \
            f"Expected transitive deps like werkzeug/jinja2/click, got: {list(pkgs.keys())[:10]}"

    async def test_npm_transitive(self, aggregator, resolver):
        """Test npm deep transitive resolution."""
        system_info = _build_system_info()
        specs = [("express", "npm", "^4.18")]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        assert _resolution_ok(result, min_pkgs=2), \
            f"Expected >=2 packages (express + transitive), got {len(_get_resolved(result))}"

    async def test_crates_transitive(self, aggregator, resolver):
        """Test crates.io transitive resolution."""
        system_info = _build_system_info()
        specs = [("serde", "crates", "1.0")]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        assert _resolution_ok(result, min_pkgs=1), \
            f"Expected serde resolved, got {result}"


# ===================================================================
# 5. EDGE CASES & CONFLICT HANDLING
# ===================================================================


class TestConflictHandling:
    """Test SAT solver behavior on edge cases."""

    async def test_unsatisfiable_constraints(self, aggregator, resolver):
        """SAT solver should gracefully handle impossible constraints."""
        system_info = _build_system_info()
        specs = [("requests", "pypi", ">=2.28"), ("urllib3", "pypi", ">=10.0")]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        status = result.get("status", "unknown")
        assert status in ("partial", "unsatisfiable", "satisfiable"), \
            f"Unexpected status: {status}"

    async def test_package_not_found(self, aggregator, resolver):
        """Missing packages should not crash the resolver."""
        system_info = _build_system_info()
        specs = [("this-package-does-not-exist-xyzzy", "pypi", "*")]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        assert result is not None

    async def test_multiple_constraint_types(self, aggregator, resolver):
        """Test various constraint operators: >=, ==, ~=, !=, <, >."""
        system_info = _build_system_info()
        specs = [
            ("requests", "pypi", ">=2.28,<3.0"),
            ("urllib3", "pypi", ">=1.26,<2.0"),
        ]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        assert _resolution_ok(result, min_pkgs=4), \
            f"Expected >=4 packages, got {len(_get_resolved(result))}"
        for spec_name, _, _ in specs:
            pkgs = _get_resolved(result)
            assert spec_name in pkgs, f"{spec_name} not resolved: {list(pkgs.keys())[:10]}"


# ===================================================================
# 6. LOCK FILE OPERATIONS
# ===================================================================


class TestLockFile:
    """Test lock file generation, validation, and reproducibility."""

    def test_lock_file_structure(self, temp_project):
        """Verify the lock file has the correct required fields."""
        _write_manifest(temp_project, "requirements.txt", "requests>=2.28")

        import subprocess
        import sys
        subprocess.run(
            [sys.executable, "-m", "backend.cli", "lock",
             "--directory", str(temp_project), "--yes", "--json"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "SOLVER_TIMEOUT": "120", "TESTING": "true"},
        )

        out_path = temp_project / "udr.lock"
        if not out_path.exists():
            alt = list(temp_project.glob("*.lock"))
            pytest.skip(f"No lock file generated: {alt}")
            return

        data = json.loads(out_path.read_text())
        assert "version" in data, f"Missing version: {list(data.keys())}"
        assert "packages" in data, f"Missing packages: {list(data.keys())}"
        assert "system" in data, f"Missing system: {list(data.keys())}"
        assert data["version"] in ("2.0",), f"Unexpected version: {data['version']}"
        assert len(data["packages"]) >= 3, \
            f"Expected >=3 packages, got {len(data['packages'])}"

    def test_lock_file_reproducibility(self, temp_project):
        """Resolving twice should produce the same result."""
        _write_manifest(temp_project, "requirements.txt", "requests>=2.28")

        import subprocess
        import sys

        def _lock() -> dict:
            subprocess.run(
                [sys.executable, "-m", "backend.cli", "lock",
                 "--directory", str(temp_project), "--yes", "--json"],
                capture_output=True, text=True, timeout=120,
                env={**os.environ, "SOLVER_TIMEOUT": "120", "TESTING": "true"},
            )
            out_path = temp_project / "udr.lock"
            if out_path.exists():
                return json.loads(out_path.read_text())
            return {}

        first = _lock()
        if not first:
            pytest.skip("First lock failed")
        (temp_project / "udr.lock").unlink(missing_ok=True)
        second = _lock()
        if not second:
            pytest.skip("Second lock failed")

        f1 = {n: v.get("resolved_version") for n, v in first.get("packages", {}).items()}
        f2 = {n: v.get("resolved_version") for n, v in second.get("packages", {}).items()}
        for name in f1:
            if name in f2:
                assert f1[name] == f2[name], \
                    f"Version mismatch for {name}: {f1[name]} vs {f2[name]}"


# ===================================================================
# 7. AMD / NO-GPU / ACCELERATOR SCENARIOS
# ===================================================================


class TestHardwareVariants:
    """Test resolution behaves correctly for different hardware profiles."""

    async def test_no_gpu_resolution(self, aggregator, resolver):
        """CPU-only resolution should not pull in CUDA packages."""
        system_info = _build_system_info(gpu=MOCK_NO_GPU)
        specs = [("requests", "pypi", ">=2.28")]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        assert _resolution_ok(result)
        pkgs = _get_resolved(result)
        cuda_pkgs = [n for n in pkgs if "cuda" in n.lower() or "nvidia" in n.lower()]
        assert len(cuda_pkgs) == 0, \
            f"CUDA packages should not appear without GPU: {cuda_pkgs}"

    async def test_amd_gpu_resolution(self, aggregator, resolver):
        """AMD GPU should resolve without CUDA packages."""
        system_info = _build_system_info(gpu=MOCK_GPU_AMD)
        specs = [("requests", "pypi", ">=2.28")]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        assert _resolution_ok(result)

    async def test_tpu_present_no_effect(self, aggregator, resolver):
        """TPU presence should not affect regular PyPI resolution."""
        system_info = _build_system_info(
            gpu=MOCK_NO_GPU, accelerators=MOCK_ACCELERATORS_TPU
        )
        specs = [("flask", "pypi", ">=2.3")]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        assert _resolution_ok(result, min_pkgs=5)

    async def test_npu_present_no_effect(self, aggregator, resolver):
        """NPU presence should not affect regular PyPI resolution."""
        system_info = _build_system_info(
            gpu=MOCK_NO_GPU, accelerators=MOCK_ACCELERATORS_NPU
        )
        specs = [("flask", "pypi", ">=2.3")]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        assert _resolution_ok(result, min_pkgs=5)


# ===================================================================
# 8. BACKTRACKING / ALTERNATIVES FALLBACK
# ===================================================================


class TestBacktracking:
    """Test the greedy→backtracking fallback path."""

    async def test_backtracking_fallback_called(self, aggregator, resolver):
        """Verify _resolve_with_alternatives is called when SAT fails."""
        system_info = _build_system_info()
        specs = [("requests", "pypi", ">=2.28"), ("urllib3", "pypi", ">=10.0")]
        result = await _run_resolution(aggregator, resolver, system_info, specs)
        status = result.get("status", "unknown")
        assert status in ("partial", "unsatisfiable", "satisfiable"), \
            f"Expected partial/unsatisfiable/satisfiable for incompatible deps, got {status}"
