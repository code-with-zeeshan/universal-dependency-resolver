#!/usr/bin/env bash
set -o pipefail
# 10 Real-World CLI test scenarios — increasing difficulty

PASS=0
FAIL=0
TMPDIR=$(mktemp -d)

cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

pass() { PASS=$((PASS+1)); echo "  ✓ PASS"; }
fail() { FAIL=$((FAIL+1)); echo "  ✗ FAIL: $1"; }

# Cap every command so a hung network call cannot stall the whole CI runner.
# Timeout in seconds (overridable via UDR_CMD_TIMEOUT).
# -k 10: escalate SIGTERM -> SIGKILL 10s later (python ignores SIGTERM while
# blocked in aiohttp/C-level calls, and GNU timeout otherwise waits forever).
CMD_TIMEOUT="${UDR_CMD_TIMEOUT:-300}"
cmd() { timeout -k 10 "$CMD_TIMEOUT" "$@" 2>&1; }

echo "╔══════════════════════════════════════════════════╗"
echo "║  Universal Dependency Resolver — 10 Real-World  ║"
echo "║  CLI Test Scenarios (increasing difficulty)     ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ─── Scenario 1: Single package resolve ───
echo "─── [1/10] Single package resolve (basic) ───"
OUT=$(cmd udr resolve requests)
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | grep -q "requests"; then
    pass
else
    fail "exit=$RC"
fi

# ─── Scenario 2: Version constraint resolve ───
echo "─── [2/10] Resolve with version constraints ───"
OUT=$(cmd udr resolve "numpy>=1.20" "pandas>=1.3")
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | grep -q "numpy" && echo "$OUT" | grep -q "pandas"; then
    pass
else
    fail "exit=$RC"
fi

# ─── Scenario 3: Mixed ecosystems ───
echo "─── [3/10] Cross-ecosystem resolve ───"
OUT=$(cmd udr resolve numpy@pypi express@npm)
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | grep -q "numpy" && echo "$OUT" | grep -qi "express"; then
    pass
else
    fail "exit=$RC"
fi

# ─── Scenario 4: JSON output ───
echo "─── [4/10] Structured JSON output ───"
JSON=$(timeout -k 10 "$CMD_TIMEOUT" udr resolve requests --format json 2>/dev/null)
RC=$?
if [ $RC -eq 0 ]; then
    echo "$JSON" | python3 -c "
import sys,json
data=json.load(sys.stdin)
assert 'resolved_packages' in data, 'missing resolved_packages'
assert 'requests' in data['resolved_packages'], 'missing requests'
" 2>&1 && pass || fail "JSON validation failed"
else
    fail "exit=$RC"
fi

# ─── Scenario 5: Dependency graph ───
echo "─── [5/10] Dependency graph ───"
OUT=$(cmd udr graph requests flask)
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | grep -qiE "(requests|flask)"; then
    pass
else
    fail "exit=$RC"
fi

# ─── Scenario 6: Lock from manifest ───
echo "─── [6/10] Lock file from manifest ───"
mkdir -p "$TMPDIR/project"
cat > "$TMPDIR/project/requirements.txt" << 'EOF'
requests>=2.28
flask>=2.0
numpy>=1.20
EOF
OUT=$(cmd udr lock -d "$TMPDIR/project" -y)
RC=$?
if [ $RC -eq 0 ] && [ -f "$TMPDIR/project/udr.lock" ]; then
    pass
else
    fail "exit=$RC $(echo "$OUT" | tail -3)"
fi

# ─── Scenario 7: Verify lock file ───
echo "─── [7/10] Verify lock file ───"
OUT=$(cmd udr verify "$TMPDIR/project/udr.lock")
RC=$?
if [ $RC -eq 0 ]; then
    pass
else
    fail "exit=$RC $(echo "$OUT" | tail -3)"
fi

# ─── Scenario 8: Update package in lock ───
echo "─── [8/10] Update single package in lock ───"
OUT=$(cmd udr update requests -d "$TMPDIR/project")
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | grep -qi "requests"; then
    pass
else
    fail "exit=$RC $(echo "$OUT" | tail -3)"
fi

# ─── Scenario 9: CUDA-aware resolution ───
echo "─── [9/10] CUDA-aware resolution ───"
OUT=$(cmd udr resolve torch --cuda 12.1)
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | grep -qi "torch"; then
    pass
else
    fail "exit=$RC $(echo "$OUT" | tail -3)"
fi

# ─── Scenario 10: Full pipeline (export + install dry-run) ───
echo "─── [10/10] Full pipeline: export + install dry-run ───"
# Export from lock
OUT1=$(cmd udr lock -d "$TMPDIR/project" --export requirements.txt --dry-run)
RC1=$?
# Install dry-run
OUT2=$(cmd udr install -d "$TMPDIR/project" --dry-run -y)
RC2=$?
if [ $RC1 -eq 0 ] && [ $RC2 -eq 0 ]; then
    pass
else
    fail "export exit=$RC1 install exit=$RC2"
fi

# ─── Summary ───
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  Results: $PASS passed, $FAIL failed                    ║"
echo "╚══════════════════════════════════════════════════╝"
exit $FAIL
