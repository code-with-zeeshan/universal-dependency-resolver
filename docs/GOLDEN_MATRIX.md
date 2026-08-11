# Golden Regression Matrix

Every resolver fix must be validated against **all** frozen real-repo fixtures,
not just the repo that motivated it. This makes progress monotonic: the corpus
only grows (one fixture per fixed real-world breakage), so a change for repo B
can never silently break repo A again — the e2e suite fails instead.

## Matrix current status

| Repo | Ecosystem(s) | Manifest | Resolves | Guards |
|------|-------------|----------|----------|--------|
| `flask-example` | pypi | `requirements.txt` | satisfiable (12 pkgs) | generic pipeline baseline (BFS, fetch, SAT) |
| `gpu-diffusers` | pypi | `setup.py` | satisfiable (23 pkgs) | extras leaking into roots (false UNSAT), PEP 440 wildcard exclusions (`!=8.3.*`) |
| `browserless-chrome` | npm | `package-lock.json` | satisfiable (407 pkgs) | nested `npm:` aliases (playwright-core 1.57/1.58/1.62…) are UNSAT under the single-version-per-package model → fixture pins a steamlined flat lock |
| `n8n` | npm | `pnpm-lock.yaml` | satisfiable (3132 pkgs) | express family in package.json (express@4.x → debug 2.6.9 → ms 2.0.0 vs send 0.18 → ms 2.1.3) provably UNSAT; fixture resolves its checked-in lock |
| `cilium` | gomodules | `go.mod` | satisfiable (321 pkgs) | go.mod `require (...)` root extraction against real supergraph; `go.sum` excluded (checksum-only, not a dependency manifest) |
| `superset` | pypi | `requirements.in` | satisfiable (33 pkgs) | `requirements/base.in` renamed → `requirements.in` so MANIFEST_PATTERNS detects it (loose pip-compile input, ranges) |
| `localstack` | pypi | `requirements.txt` | satisfiable (118 pkgs) | `requirements-runtime.txt` renamed → `requirements.txt` (pip-compile pinned output) |
| `sanic` | pypi | `setup.py` | satisfiable (20 pkgs) | `setup_kwargs["install_requires"] = requirements` variable-indirection pattern (sanic's modern setup.py) |

`test_repo_golden[<repo>]` in `tests/e2e/test_golden_matrix.py` re-runs
`udr lock --dry-run --json` inside each fixture and asserts:

1. **status** — satisfiable / unsatisfiable must match `expected.json`
2. **name-set** — the resolved graph (sorted package names) must match exactly
3. **roots** — every `install_requires` entry must be present (case-insensitive,
   PyPI normalizes names)
4. **anchors** — optional `{pkg: version}` pins for behavior-sensitive packages

Upstream releases drift constantly, so transitive *versions* are deliberately
not frozen — only the shape above plus explicit anchors. Regenerate a stale
golden with:

```bash
UDR_GOLDEN_UPDATE=1 pytest tests/e2e/test_golden_matrix.py
```

Review the diff of `expected.json` before committing the regeneration.
Fixture manifests are frozen snapshots of real repos (see `guards`); where a
manifest is self-unsatisfiable under the single-version-per-package model
(express family, nested npm aliases), the fixture resolves the checked-in
lock file instead — the guard documents that decision.

**Python-version binding**: the name-set is resolved by `udr lock`, whose
PEP 508 marker evaluation uses the host interpreter. Fixtures are frozen
under Python 3.13 (e.g. the superset graph gains `typing-extensions` on
py<3.13 because of conditional markers). The `golden-tests` CI job must run
**3.13** — running a different interpreter produces false graph drift and
requires regenerating `expected.json`.

## Network handling

Same policy as the other e2e suites: unreachable registries → `pytest.skip`
(hints: connection/timeout/network strings in output). A genuinely failing
resolution — false UNSAT, solver crash, dropped package — **fails** the test.

## Adding a new fixture (when a real repo breaks)

```bash
mkdir tests/e2e/golden/<repo>
# 1. copy the manifest(s) that reproduces the bug: e.g. setup.py / pyproject.toml
cp /path/to/real/repo/setup.py tests/e2e/golden/<repo>/
# 2. record the outcome of a KNOWN-GOOD run:
cd tests/e2e/golden/<repo>
UDR_GOLDEN_UPDATE=1 pytest ../../test_golden_matrix.py -k <repo>   # after first-run failure, or:
# run manually to capture the JSON, then write expected.json by hand
```

Then add a row to the matrix above (status + the exact bug being guarded
against) and commit the fixture — the corpus now permanently protects that
breakage.

## Rules of the corpus

- New reported breakage → new fixture. **The corpus only grows.**
- A fix lands only when the entire matrix is green; a red fixture is a
  regression by definition, never silently updated.
- `UDR_GOLDEN_UPDATE` is reserved for intentional expectation changes
  (packaging decisions, deliberate behavior changes) — always with an
  explicit commit and a `guards` note in `expected.json`.
