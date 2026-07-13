#!/usr/bin/env python3
"""UDR Resolution Pipeline Benchmark.

Usage:
    python -m scripts.benchmark [--offline] [--solver z3|pubgrub|default]

Measures and reports performance for key operations:
  - Import timing
  - Solver instantiation
  - Solver small/medium resolution
  - Lock file parsing (50/100/500 packages)
  - System info fingerprint
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Helpers ──────────────────────────────────────────────────────────────────


def _timer(label: str, results: list, unit: str = "ms") -> callable:
    """Return a context-manager-style helper via `with`."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        start = time.perf_counter()
        yield
        elapsed = time.perf_counter() - start
        if unit == "ms":
            display = elapsed * 1000
        elif unit == "s":
            display = elapsed
        else:
            display = elapsed
        results.append((label, round(display, 2), unit))

    return _ctx


_SYNTHETIC_VERSIONS = [
    "1.0.0",
    "1.1.0",
    "1.2.0",
    "2.0.0",
    "2.1.0",
    "2.2.0",
    "2.3.0",
    "2.4.0",
    "2.5.0",
    "2.6.0",
    "2.7.0",
    "2.8.0",
    "2.9.0",
    "3.0.0",
    "3.1.0",
    "3.2.0",
    "3.3.0",
    "4.0.0",
    "4.1.0",
    "4.2.0",
]


def _make_pkg(
    name: str,
    eco: str = "pypi",
    constraint: str = ">=1.0.0",
    versions: list[str] | None = None,
    deps: dict | None = None,
) -> dict:
    return {
        "name": name,
        "ecosystem": eco,
        "version_constraint": constraint,
        "available_versions": versions or _SYNTHETIC_VERSIONS[:],
        "dependencies": {eco: deps or {}},
        "system_requirements": {},
        "cross_ecosystem_deps": [],
    }


def _build_medium_packages() -> list[dict]:
    """Build a 12-package dependency tree with matching constraint/version combos."""
    return [
        _make_pkg(
            "web-app", constraint=">=1.0,<5.0",
            versions=["2.0.0", "3.0.0", "4.0.0"],
            deps={"flask": ">=2.0,<4.0", "requests": ">=2.0,<3.0"},
        ),
        _make_pkg(
            "flask", constraint=">=2.0,<4.0",
            versions=["2.0.0", "2.1.0", "2.2.0", "3.0.0", "3.1.0"],
            deps={"click": ">=8.0", "itsdangerous": ">=2.0", "jinja2": ">=3.0", "werkzeug": ">=2.0"},
        ),
        _make_pkg(
            "requests", constraint=">=2.0,<3.0",
            versions=["2.0.0", "2.1.0", "2.2.0", "2.3.0", "2.4.0"],
            deps={"urllib3": ">=1.26,<3.0", "certifi": ">=2021.0", "charset-normalizer": ">=2.0,<4.0", "idna": ">=2.5,<4.0"},
        ),
        _make_pkg(
            "click", constraint=">=8.0",
            versions=["8.0.0", "8.1.0", "8.2.0", "9.0.0"],
        ),
        _make_pkg(
            "itsdangerous", constraint=">=2.0",
            versions=["2.0.0", "2.1.0", "2.2.0"],
        ),
        _make_pkg(
            "jinja2", constraint=">=3.0",
            versions=["3.0.0", "3.1.0", "3.2.0"],
            deps={"markupsafe": ">=2.0"},
        ),
        _make_pkg(
            "werkzeug", constraint=">=2.0",
            versions=["2.0.0", "2.1.0", "2.2.0", "2.3.0", "3.0.0"],
        ),
        _make_pkg(
            "urllib3", constraint=">=1.26,<3.0",
            versions=["1.26.0", "1.27.0", "2.0.0", "2.1.0", "2.2.0"],
        ),
        _make_pkg(
            "certifi", constraint=">=2021.0",
            versions=["2021.0.0", "2022.0.0", "2023.0.0"],
        ),
        _make_pkg(
            "charset-normalizer", constraint=">=2.0,<4.0",
            versions=["2.0.0", "2.1.0", "3.0.0", "3.1.0"],
        ),
        _make_pkg(
            "idna", constraint=">=2.5,<4.0",
            versions=["2.5.0", "2.6.0", "3.0.0", "3.1.0"],
        ),
        _make_pkg(
            "markupsafe", constraint=">=2.0",
            versions=["2.0.0", "2.1.0", "2.2.0"],
        ),
    ]


def _build_lock_data(pkg_count: int) -> str:
    """Generate a synthetic lock file JSON string with *pkg_count* entries."""
    pkgs = {}
    for i in range(pkg_count):
        name = f"package-{i:04d}"
        pkgs[name] = {
            "version": f"{i // 10}.{(i % 10)}.0",
            "ecosystem": "pypi",
            "integrity": {"algorithm": "sha256", "hash": f"abc{hash(name) % 10**40:040x}"},
            "resolution_hash": f"hash-{i:016x}",
            "deprecated": i % 7 == 0,
            "yanked": False,
            "depends_on": {f"package-{(i + j) % pkg_count}": f">={j}.0.0" for j in range(min(3, pkg_count)) if (i + j) % pkg_count != i},
        }
    data = {
        "version": "2.0",
        "resolver": "pubgrub",
        "host": {"os": "linux", "arch": "x86_64"},
        "packages": pkgs,
    }
    return json.dumps(data, indent=2)


# ── Benchmark operations ─────────────────────────────────────────────────────


def benchmark_import(results: list) -> None:
    label = "import PubGrubSolver"
    start = time.perf_counter()
    from backend.core.pubgrub_solver import PubGrubSolver  # noqa: F401

    elapsed = time.perf_counter() - start
    results.append((label, round(elapsed * 1000, 2), "ms"))


def benchmark_orchestrator_import(results: list) -> None:
    """Measure import time for the orchestrator module (triggers more sub-module loading)."""
    label = "import backend.orchestrator"
    start = time.perf_counter()
    import backend.orchestrator
    elapsed = time.perf_counter() - start
    results.append((label, round(elapsed * 1000, 2), "ms"))


def benchmark_create_solver(results: list) -> None:
    from backend.orchestrator import create_solver

    label = "create_solver()"
    start = time.perf_counter()
    solver = create_solver()
    elapsed = time.perf_counter() - start
    results.append((label, round(elapsed * 1000, 2), "ms"))


def benchmark_solver_small(results: list, solver_type: str) -> None:
    """Resolve 2 packages with known compatible versions."""
    from backend.orchestrator import create_solver

    resolver = create_solver(solver_timeout=10000)
    packages = [
        _make_pkg(
            "requests", constraint=">=2.0,<3.0",
            versions=["2.0.0", "2.1.0", "2.2.0", "2.3.0", "2.4.0"],
        ),
        _make_pkg(
            "flask", constraint=">=2.0,<4.0",
            versions=["2.0.0", "2.1.0", "2.2.0", "3.0.0", "3.1.0"],
        ),
    ]
    system_info = {"os": "linux", "arch": "x86_64", "python_version": "3.13"}

    label = f"solver small ({solver_type})"
    start = time.perf_counter()
    result = resolver.resolve_dependencies(packages=packages, system_info=system_info)
    elapsed = time.perf_counter() - start
    status = result.get("status", "error")
    pkg_count = len(result.get("resolved_packages", {}))
    results.append((label, round(elapsed * 1000, 2), "ms"))
    results.append((f"  → status={status}, resolved={pkg_count}", 0, ""))


def benchmark_solver_medium(results: list, solver_type: str) -> None:
    """Resolve 12 packages."""
    from backend.orchestrator import create_solver

    resolver = create_solver(solver_timeout=10000)
    packages = _build_medium_packages()
    system_info = {"os": "linux", "arch": "x86_64", "python_version": "3.13"}

    label = f"solver medium ({solver_type})"
    start = time.perf_counter()
    result = resolver.resolve_dependencies(packages=packages, system_info=system_info)
    elapsed = time.perf_counter() - start
    status = result.get("status", "error")
    pkg_count = len(result.get("resolved_packages", {}))
    results.append((label, round(elapsed * 1000, 2), "ms"))
    results.append((f"  → status={status}, resolved={pkg_count}", 0, ""))


def benchmark_lock_parse(results: list) -> None:
    """Benchmark JSON parse of synthetic lock files with 50/100/500 packages."""
    import json

    for count in (50, 100, 500):
        data = _build_lock_data(count)
        label = f"parse lock ({count} pkgs)"
        start = time.perf_counter()
        parsed = json.loads(data)
        _ = len(parsed["packages"])
        elapsed = time.perf_counter() - start
        results.append((label, round(elapsed * 1000, 2), "ms"))
        size_kb = len(data) / 1024
        results.append((f"  → {size_kb:.1f} KB", 0, ""))


def benchmark_fingerprint(results: list) -> None:
    """Benchmark _system_info_fingerprint()."""
    from backend.orchestrator.resolve import _system_info_fingerprint

    system_info = {
        "os": "linux",
        "arch": "x86_64",
        "platform": {"system": "linux", "architecture": "x86_64"},
        "gpu": {"available": True, "cuda": "12.1"},
        "runtime_versions": {"python": {"version": "3.13"}},
        "memory": {"total_gb": 32},
        "disks": [{"mount": "/", "total_gb": 256}],
        "hostname": "bench-host",
    }

    label = "system info fingerprint"
    start = time.perf_counter()
    for _ in range(10000):
        _ = _system_info_fingerprint(system_info)
    elapsed = time.perf_counter() - start
    results.append((label, round(elapsed * 1000 / 10000, 4), "ms (avg of 10k)"))


# ── Main ──────────────────────────────────────────────────────────────────────


def print_table(results: list) -> None:
    """Print a formatted results table."""
    sep = "-" * 72
    print()
    print("╔" + "═" * 70 + "╗")
    print("║" + " " * 24 + "UDR Performance Benchmark" + " " * 24 + "║")
    print("╚" + "═" * 70 + "╝")
    print()
    print(f"{'Operation':<42} {'Time':>12} {'Unit'}")
    print(sep)
    for op, t, unit in results:
        if t == 0 and unit == "":
            print(f"  {op:<40}")
        else:
            print(f"{op:<42} {t:>12.4f} {unit}")


def main() -> None:
    parser = argparse.ArgumentParser(description="UDR Resolution Pipeline Benchmark")
    parser.add_argument("--offline", action="store_true", help="Use local synthetic data (no API calls)")
    parser.add_argument("--solver", choices=["z3", "pubgrub", "default"], default="default", help="Solver backend to benchmark")
    args = parser.parse_args()

    # Environment setup for offline mode
    if args.offline:
        os.environ["ENABLE_CACHE"] = "true"
        os.environ["SOLVER_MAX_VARIABLES"] = "50000"

    # Select solver backend
    if args.solver == "z3":
        os.environ["USE_Z3_SOLVER"] = "true"
        os.environ["USE_PUBGRUB_SOLVER"] = "false"
        solver_type = "Z3"
    elif args.solver == "pubgrub":
        os.environ["USE_Z3_SOLVER"] = "false"
        os.environ["USE_PUBGRUB_SOLVER"] = "true"
        solver_type = "PubGrub"
    else:
        solver_type = "default (PubGrub)"

    results: list = []

    print(f"Benchmarking solver backend: {solver_type}")
    print(f"Offline mode: {'ON' if args.offline else 'OFF'}")
    print()

    # 1. Import timing
    benchmark_import(results)

    # 2. Orchestrator module import (separated from solver instantiation)
    benchmark_orchestrator_import(results)

    # 3. Solver instantiation
    benchmark_create_solver(results)

    # 4. Solver small
    benchmark_solver_small(results, solver_type)

    # 5. Solver medium
    benchmark_solver_medium(results, solver_type)

    # 6. Lock file parsing
    benchmark_lock_parse(results)

    # 7. System info fingerprint
    benchmark_fingerprint(results)

    # Print results table
    print_table(results)

    # Check for slow operations (>5s threshold)
    divider = "-" * 72
    print()
    print(divider)
    slow_ops = [(op, t) for op, t, u in results if u == "ms" and t > 5000]
    if slow_ops:
        print(f"\n⚠️  {len(slow_ops)} operation(s) exceeded 5s threshold:")
        for op, t in slow_ops:
            print(f"   {op}: {t:.0f}ms")
    else:
        print("\n✅ All operations within acceptable thresholds (<5s)")


if __name__ == "__main__":
    main()
