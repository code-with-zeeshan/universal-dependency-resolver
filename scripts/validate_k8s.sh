#!/usr/bin/env bash
set -euo pipefail

KEEP="${1:-}"
CLUSTER_NAME="dep-resolver-test"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${YELLOW}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; }

cleanup() {
  if [ "$KEEP" = "--keep" ]; then
    info "Skipping cluster deletion (--keep was passed)"
    return
  fi
  info "Deleting kind cluster '$CLUSTER_NAME'..."
  kind delete cluster --name "$CLUSTER_NAME" 2>/dev/null || true
  ok "Cleanup complete"
}
trap cleanup EXIT

# --- kind ---
if command -v kind &>/dev/null; then
  ok "kind is already installed ($(kind --version))"
else
  info "kind not found — installing via go..."
  if command -v go &>/dev/null; then
    go install sigs.k8s.io/kind@latest
    export PATH="$HOME/go/bin:$PATH"
  else
    info "go not found — downloading kind binary to /usr/local/bin..."
    curl -Lo /tmp/kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64
    chmod +x /tmp/kind
    sudo mv /tmp/kind /usr/local/bin/kind
  fi
  ok "kind installed ($(kind --version))"
fi

# --- kubectl ---
if command -v kubectl &>/dev/null; then
  ok "kubectl is already installed ($(kubectl version --client --output=json 2>/dev/null | grep -o '"gitVersion":"[^"]*"' | head -1))"
else
  fail "kubectl is not installed — please install kubectl first (https://kubernetes.io/docs/tasks/tools/)"
  exit 1
fi

# --- create kind cluster ---
EXISTING=$(kind get clusters 2>/dev/null | grep -x "$CLUSTER_NAME" || true)
if [ -n "$EXISTING" ]; then
  info "Kind cluster '$CLUSTER_NAME' already exists"
else
  info "Creating kind cluster '$CLUSTER_NAME'..."
  kind create cluster --name "$CLUSTER_NAME" --wait 60s
  ok "Cluster created"
fi

# --- apply manifests ---
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MANIFESTS="$SCRIPT_DIR/k8s"
if [ -d "$MANIFESTS" ]; then
  info "Applying manifests from $MANIFESTS..."
  kubectl apply -f "$MANIFESTS"
  ok "Manifests applied"
else
  fail "k8s/ directory not found at $MANIFESTS"
  exit 1
fi

# --- wait for pods ---
info "Waiting 30s for pods to become ready..."
sleep 30

# --- show pods ---
echo ""
info "=== Pod status ==="
kubectl get pods -A
echo ""

# --- check deployments/pods for failures ---
FAILURES=0

for ns in $(kubectl get ns -o jsonpath='{.items[*].metadata.name}'); do
  for dep in $(kubectl get deployments -n "$ns" -o name 2>/dev/null); do
    READY=$(kubectl get "$dep" -n "$ns" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    REPLICAS=$(kubectl get "$dep" -n "$ns" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")
    if [ "${READY:-0}" -lt "${REPLICAS:-1}" ]; then
      fail "Deployment $dep in namespace $ns: ready $READY / desired $REPLICAS"
      FAILURES=$((FAILURES + 1))
    else
      ok "Deployment $dep in namespace $ns: $READY/$REPLICAS ready"
    fi
  done
done

# --- check HPA ---
echo ""
info "=== HPA status ==="
if kubectl get hpa -A 2>/dev/null; then
  ok "HPA manifests are valid"
else
  fail "HPA check returned an error"
  FAILURES=$((FAILURES + 1))
fi

# --- check PDB ---
echo ""
info "=== PDB status ==="
if kubectl get pdb -A 2>/dev/null; then
  ok "PDB manifests are valid"
else
  fail "PDB check returned an error"
  FAILURES=$((FAILURES + 1))
fi

# --- check network policies ---
echo ""
info "=== NetworkPolicy status ==="
if kubectl describe networkpolicies -A &>/dev/null; then
  ok "NetworkPolicy manifests are valid"
else
  fail "NetworkPolicy check returned an error"
  FAILURES=$((FAILURES + 1))
fi

# --- summary ---
echo ""
if [ "$FAILURES" -eq 0 ]; then
  ok "All validations passed!"
else
  fail "$FAILURES validation(s) failed"
  exit 1
fi
