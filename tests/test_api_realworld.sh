#!/usr/bin/env bash
set -o pipefail

PASS=0
FAIL=0
PORT=19876
BASE="http://127.0.0.1:$PORT/api/v1"
SERVER_PID=""

cleanup() {
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null && wait "$SERVER_PID" 2>/dev/null
}
trap cleanup EXIT

pass() { PASS=$((PASS+1)); echo "  ✓ PASS"; }
fail() { FAIL=$((FAIL+1)); echo "  ✗ FAIL: $1"; }

echo "╔══════════════════════════════════════════════════╗"
echo "║  Universal Dependency Resolver — 10 Real-World  ║"
echo "║  API Test Scenarios (increasing difficulty)     ║"
echo "╚══════════════════════════════════════════════════╝"

# Start server
echo ""
echo "─── Starting API server on port $PORT ───"
cd /home/user/universal-dependency-resolver
ENABLE_CSRF=false udr serve --port $PORT --host 127.0.0.1 > /tmp/udr_api_test.log 2>&1 &
SERVER_PID=$!
sleep 3

if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "  ✗ Server failed to start"
    cat /tmp/udr_api_test.log | tail -5
    exit 1
fi

# Helper — GET
api_get() {
    curl -sf "$BASE$1" 2>/dev/null
}

# Helper — POST
api_post() {
    local path=$1 data=$2
    curl -sf -X POST "$BASE$path" -H "Content-Type: application/json" -d "$data" 2>/dev/null
}

echo ""

# ─── Scenario 1: Health check ───
echo "─── [1/10] Health check (GET /api/v1/health) ───"
OUT=$(api_get /health)
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status') == 'healthy'" 2>/dev/null; then
    pass
else
    fail "exit=$RC $(echo "$OUT" | head -2)"
fi

# ─── Scenario 2: List ecosystems ───
echo "─── [2/10] List ecosystems (GET /api/v1/packages/ecosystems) ───"
OUT=$(api_get /packages/ecosystems)
RC=$?
ECO_COUNT=$(echo "$OUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total', 0))" 2>/dev/null)
if [ $RC -eq 0 ] && [ "$ECO_COUNT" -ge 13 ] 2>/dev/null; then
    pass
else
    fail "exit=$RC ecosystems=$ECO_COUNT (expected ≥13)"
fi

# ─── Scenario 3: Package details ───
echo "─── [3/10] Package details (GET /api/v1/packages/pypi/requests/details) ───"
OUT=$(api_get /packages/pypi/requests/details)
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d['status'] == 'success'
assert 'requests' in d['data']['name'].lower()
" 2>/dev/null; then
    pass
else
    fail "exit=$RC"
fi

# ─── Scenario 4: Search packages ───
echo "─── [4/10] Search packages (GET /api/v1/packages/search?q=requests) ───"
OUT=$(api_get '/packages/search?q=requests')
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d['status'] == 'success'
assert int(d.get('total_count', 0)) > 0
" 2>/dev/null; then
    pass
else
    fail "exit=$RC"
fi

# ─── Scenario 5: System check-compatibility (POST) ───
echo "─── [5/10] System check-compatibility (POST /api/v1/system/check-compatibility) ───"
OUT=$(api_post /system/check-compatibility '{"requirements":[{"type":"python","minimum":{"version":"3.8"},"required":true}]}')
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d['status'] == 'success'
assert 'compatible' in d.get('results', {})
" 2>/dev/null; then
    pass
else
    fail "exit=$RC $(echo "$OUT" | head -1)"
fi

# ─── Scenario 6: Package versions ───
echo "─── [6/10] Package versions (GET /api/v1/packages/pypi/requests/versions) ───"
OUT=$(api_get /packages/pypi/requests/versions)
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d['status'] == 'success'
assert int(d.get('total_versions', 0)) > 0
" 2>/dev/null; then
    pass
else
    fail "exit=$RC"
fi

# ─── Scenario 7: Package dependencies ───
echo "─── [7/10] Package dependencies (GET /api/v1/packages/pypi/requests/dependencies) ───"
OUT=$(api_get /packages/pypi/requests/dependencies)
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d['status'] == 'success'
" 2>/dev/null; then
    pass
else
    fail "exit=$RC"
fi

# ─── Scenario 8: Dependency graph (POST) ───
echo "─── [8/10] Dependency graph (POST /api/v1/graph) ───"
OUT=$(api_post /graph '{"packages":["requests","flask"],"ecosystem":"pypi"}')
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d['status'] == 'success'
assert len(d.get('trees', [])) > 0
" 2>/dev/null; then
    pass
else
    fail "exit=$RC $(echo "$OUT" | head -2)"
fi

# ─── Scenario 9: Cross-ecosystem install commands (POST) ───
echo "─── [9/10] Install commands (POST /api/v1/install-commands) ───"
OUT=$(api_post /install-commands '{"lock_data":{"packages":{"numpy":{"ecosystem":"pypi","resolved_version":"1.26.0","direct":true},"express":{"ecosystem":"npm","resolved_version":"4.18.2","direct":true}}}}')
RC=$?
if [ $RC -eq 0 ] && echo "$OUT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d['status'] == 'success'
assert len(d.get('commands', [])) >= 1
" 2>/dev/null; then
    pass
else
    fail "exit=$RC $(echo "$OUT" | head -2)"
fi

# ─── Scenario 10: Full pipeline (CLI resolve → API lock → API verify → API restore) ───
echo "─── [10/10] Full pipeline: CLI resolve → API generate-lock → API verify → API restore ───"
# Step 1: Resolve requests via CLI (proven in CLI test)
OUT1=$(udr resolve requests --format json 2>/dev/null)
RC1=$?
# Step 2: Generate lock via API with resolved version from CLI
RESOLVED_VER=$(echo "$OUT1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('resolved_packages',{}).get('requests',{}).get('version','0.0.0'))" 2>/dev/null)
OUT2=$(api_post /generate-lock "{\"packages\":[{\"name\":\"requests\",\"ecosystem\":\"pypi\",\"resolved_version\":\"$RESOLVED_VER\",\"constraint\":\">=2.28\"}],\"manifests\":[{\"filename\":\"requirements.txt\",\"ecosystem\":\"pypi\"}]}")
RC2=$?
# Step 3: Verify the generated lock data
LOCK_DATA=$(echo "$OUT2" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)['lock_data']))" 2>/dev/null)
OUT3=$(api_post /verify "{\"lock_data\":$LOCK_DATA}")
RC3=$?
# Step 4: Get restore commands from lock data
OUT4=$(api_post /restore-commands "{\"lock_data\":$LOCK_DATA}")
RC4=$?

if [ $RC1 -eq 0 ] && [ $RC2 -eq 0 ] && [ $RC3 -eq 0 ] && [ $RC4 -eq 0 ]; then
    pass
else
    fail "CLI_resolve=$RC1 generate=$RC2 verify=$RC3 restore=$RC4"
fi

# ─── Summary ───
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  API Results: $PASS passed, $FAIL failed               ║"
echo "╚══════════════════════════════════════════════════╝"
cleanup
exit $FAIL
