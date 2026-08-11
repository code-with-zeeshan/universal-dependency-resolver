"""Golden regression matrix — re-run UDR against frozen real-repo fixtures.

Every fixture in ``tests/e2e/golden/<repo>/`` ships with an ``expected.json``
recording the outcome the repo produced **when it last passed**.  Any change
to resolver logic must keep every fixture passing — the corpus only grows,
so cumulative progress is monotonic and a fix for repo B can never silently
break repo A again.

Conventions
-----------
- Fixture layout: ``tests/e2e/golden/<repo>/{manifests..., expected.json}``
- ``expected.json`` keys: ``repo``, ``manifests``, ``guards`` (free text),
  ``expected`` dict holding ``status``, ``install_requires`` (manifest root
  set) and ``resolved_packages`` (the whole solved graph, sorted),
  ``anchors`` ({pkg: version} for behavior-sensitive pins, optional).
- Deliberately NOT recording every transitive version: upstream releases
  drift constantly and would create noise.  We lock the *signal*: status,
  the reachable name-set, the manifest roots, and explicit anchors.
- Regenerate a stale golden with ``UDR_GOLDEN_UPDATE=1 pytest ...``.

Network handling
----------------
Same convention as the other e2e suites: unreachable registries produce a
``pytest.skip`` (the corpus positions guards in CI/dev machines where a
correct result is verifiable). An actually-failing resolution (false UNSAT,
crash, dropped package) FAILS the test.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UDR = [sys.executable, "-m", "backend.cli"]
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
UPDATE_GOLDEN = os.environ.get("UDR_GOLDEN_UPDATE") == "1"
GOLDEN_TIMEOUT = int(os.environ.get("UDR_GOLDEN_TIMEOUT", "600"))

ENV = {
    **os.environ,
    "PYTHONPATH": str(REPO_ROOT),
    "TESTING": "true",
    "SECRET_KEY": "test-secret-key-for-ci",
}

_NETWORK_HINTS = (
    "connection",
    "timed out",
    "timeout",
    "network",
    "failed to fetch",
    "unavailable",
    "error fetching",
)


def _discover() -> list[tuple[str, Path, Path]]:
    """Discover golden fixtures: [(repo_name, fixture_dir, expected_json)]."""
    found = []
    if not GOLDEN_DIR.is_dir():
        return found
    for entry in sorted(GOLDEN_DIR.iterdir()):
        expected = entry / "expected.json"
        if entry.is_dir() and expected.is_file():
            found.append((entry.name, entry, expected))
    return found


def _looks_like_network_failure(result: subprocess.CompletedProcess) -> bool:
    combined = f"{result.stdout} {result.stderr}".lower()
    return any(hint in combined for hint in _NETWORK_HINTS)


def _run_lock(fixture_dir: Path, manifest: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*UDR, "lock", "--dry-run", "--json", "--manifest", manifest],
        capture_output=True,
        text=True,
        cwd=str(fixture_dir),
        env=ENV,
        timeout=GOLDEN_TIMEOUT,
    )


def _parse_json(result: subprocess.CompletedProcess) -> dict:
    try:
        return json.loads(result.stdout)
    except Exception as exc:
        pytest.fail(
            f"golden produced unparseable JSON: {exc}\n"
            f"stdout={result.stdout[:400]} stderr={result.stderr[:400]}"
        )


def _expected_dict(lock: dict, repo_name: str, expected: dict) -> dict:
    names = sorted((lock.get("packages") or {}).keys())
    return {
        "repo": repo_name,
        "manifests": expected.get("manifests", ["setup.py"]),
        "guards": expected.get("guards", []),
        "expected": {
            "status": lock.get("status", "satisfiable"),
            "install_requires": sorted(expected["expected"].get("install_requires", [])),
            "resolved_packages": names,
        },
        "anchors": {},
    }


def _run_golden(repo_name: str, fixture_dir: Path, expected: dict) -> None:
    manifests = expected.get("manifests", ["setup.py"])
    lock_results: dict[str, dict] = {}

    for manifest in manifests:
        manifest_path = fixture_dir / manifest
        if not manifest_path.is_file():
            pytest.fail(
                f"golden '{repo_name}': expected.json references "
                f"'{manifest}' but the fixture is missing"
            )
        result = _run_lock(fixture_dir, manifest)
        if result.returncode != 0:
            if _looks_like_network_failure(result):
                pytest.skip(f"{repo_name}: registry unreachable: {result.stderr[:200]}")
            pytest.fail(
                f"golden '{repo_name}' lock failed: rc={result.returncode} "
                f"stderr={result.stderr[:300]}"
            )
        lock_results[manifest] = _parse_json(result)

    # Merge multiple manifests: union of packages, satisfiable only if all are
    merged_names: set[str] = set()
    any_unsat = False
    for data in lock_results.values():
        merged_names |= set((data.get("packages") or {}).keys())
        if data.get("status") != "satisfiable":
            any_unsat = True
    merged = {
        "status": "unsatisfiable" if any_unsat else "satisfiable",
        "packages": {name: {} for name in merged_names},
    }

    if UPDATE_GOLDEN:
        (fixture_dir / "expected.json").write_text(
            json.dumps(_expected_dict(merged, repo_name, expected), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[golden] UDR_GOLDEN_UPDATE=1: rewrote {repo_name}/expected.json")
        return

    exp = expected["expected"]
    exp_status = exp.get("status", "satisfiable")
    if merged["status"] != exp_status:
        pytest.fail(
            f"golden '{repo_name}' status drift: expected {exp_status}, got {merged['status']}"
        )

    names = set(merged["packages"].keys())
    exp_names = exp.get("resolved_packages", [])
    missing = set(exp_names) - names
    extra = names - set(exp_names)
    if missing or extra:
        pytest.fail(
            f"golden '{repo_name}' graph drift:\n  missing: {sorted(missing)}\n"
            f"  unexpected: {sorted(extra)}"
        )

    roots = exp.get("install_requires", [])
    resolved_lower = {n.lower() for n in names}
    not_roots = [r for r in roots if r.lower() not in resolved_lower]
    assert not not_roots, f"golden '{repo_name}': missing manifest roots {sorted(not_roots)}"

    for pkg, ver in (expected.get("anchors") or {}).items():
        got = lock_results and merged["packages"].get(pkg, {}).get("version")
        if got != ver:
            pytest.fail(f"golden '{repo_name}' anchor drift: {pkg} expected {ver}, got {got}")


GOLDENS = _discover()


@pytest.mark.parametrize(
    "golden_tuple",
    [
        pytest.param((name, fixture_dir, expected), id=name)
        for name, fixture_dir, expected in GOLDENS
    ],
)
def test_repo_golden(golden_tuple: tuple[str, Path, Path]) -> None:
    repo_name, fixture_dir, expected_json = golden_tuple
    expected = json.loads(expected_json.read_text(encoding="utf-8"))
    _run_golden(repo_name, fixture_dir, expected)


def test_corpus_present() -> None:
    """Fail loudly if the golden corpus is empty — never silently no-op."""
    assert GOLDENS, "no golden fixtures found under tests/e2e/golden/ (corpus regressed?)"
