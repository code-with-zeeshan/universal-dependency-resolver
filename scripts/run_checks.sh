#!/usr/bin/env bash
# Run all quality checks — lint, format, typecheck, tests.
# Usage: scripts/run_checks.sh          # full suite
#        scripts/run_checks.sh --quick  # skip slow tests
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

QUICK="${1:-}"

echo "=== ruff check ==="
ruff check backend/

echo "=== ruff format check ==="
ruff format --check --diff backend/

echo "=== mypy ==="
mypy backend --ignore-missing-imports

if [ "$QUICK" = "--quick" ]; then
    echo "=== pytest (quick — unit only) ==="
    python -m pytest tests/unit/ -q --tb=short -k "not data_source"
else
    echo "=== pytest (full unit suite) ==="
    python -m pytest tests/unit/ -q --tb=short

    echo "=== pytest (CLI tests) ==="
    python -m pytest tests/cli/ -q --tb=short
fi

echo
echo "All checks passed."
