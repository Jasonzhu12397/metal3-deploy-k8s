#!/usr/bin/env bash
set -Eeuo pipefail

# Tears down everything setup.sh created: the workload cluster, the kind
# management cluster, and this project's docker-compose stack. Does NOT
# remove the "kind" Docker network (other kind clusters on this host may
# still be using it) or this project's .env (your generated secrets --
# no reason to force regenerating those).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
MGMT_CLUSTER_NAME="${MGMT_CLUSTER_NAME:-capd-quickstart-mgmt}"
WORKLOAD_CLUSTER_NAME="${WORKLOAD_CLUSTER_NAME:-capd-demo}"
NAMESPACE="${NAMESPACE:-metal3}"
KUBECONFIG_DIR="${SCRIPT_DIR}/.kubeconfigs"
MGMT_KUBECONFIG="${KUBECONFIG_DIR}/${MGMT_CLUSTER_NAME}.kubeconfig"

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    COMPOSE_CMD=()
fi

if [[ -f "${MGMT_KUBECONFIG}" ]]; then
    echo "Deleting workload cluster '${WORKLOAD_CLUSTER_NAME}' (via the management cluster)..."
    KUBECONFIG="${MGMT_KUBECONFIG}" kubectl delete cluster "${WORKLOAD_CLUSTER_NAME}" -n "${NAMESPACE}" --ignore-not-found --timeout=120s || true
fi

if command -v kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -qx "${MGMT_CLUSTER_NAME}"; then
    echo "Deleting management cluster '${MGMT_CLUSTER_NAME}'..."
    kind delete cluster --name "${MGMT_CLUSTER_NAME}"
fi

if [[ ${#COMPOSE_CMD[@]} -gt 0 ]]; then
    echo "Stopping this project's docker-compose stack..."
    (cd "${PROJECT_DIR}" && "${COMPOSE_CMD[@]}" down) || true
fi

rm -rf "${KUBECONFIG_DIR}"
rm -f "${PROJECT_DIR}/deploy/kubeconfig/config"

echo "[OK] Cleaned up. The 'kind' Docker network and .env were left alone on purpose."
