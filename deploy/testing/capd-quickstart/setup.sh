#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# capd-quickstart: prove this platform can actually deploy and manage a
# real Kubernetes cluster, using only containers -- no physical hardware,
# no cloud account, no VMware. This is the same "no real infra needed"
# testing path philosophy as deploy/testing/fake-bmc/, but one level up
# the stack: fake-bmc proves BareMetalHost registration/inspection works,
# this proves a REAL Kubernetes API server comes up and is reachable,
# through this project's actual API end to end -- not a raw kubectl
# bypass of it.
#
# What this does, in order:
#   1. Creates a "kind" Docker network (Cluster API Provider Docker's own
#      documented prerequisite -- it puts its per-cluster load-balancer
#      container on this network).
#   2. Creates a kind cluster to serve as the MANAGEMENT cluster (the one
#      this project's backend talks to -- see MGMT_KUBECONFIG_PATH).
#   3. Installs Cluster API core + the Docker infrastructure provider
#      (CAPD) onto it via clusterctl init --infrastructure docker.
#   4. Brings up this project's own stack (docker compose) pointed at
#      that kubeconfig.
#   5. Calls this project's REAL API -- not a shortcut -- to create a
#      Cluster with infrastructure_provider=docker and trigger a
#      deployment, then polls it the same way the frontend's WebSocket
#      view would.
#   6. Once complete, fetches the new WORKLOAD cluster's own kubeconfig
#      (same "<cluster-name>-kubeconfig" Secret convention
#      services/target_cluster.py already uses for AI workload
#      deployment) and runs `kubectl get nodes` against it -- the actual
#      proof: a real, separate Kubernetes API server, stood up by this
#      platform, answering real requests.
#
# CAPD is explicitly a development/testing infrastructure provider --
# that's not this platform's opinion, it's upstream Cluster API's own
# documented position. This script exists to prove the pipeline works,
# not as a template for a production deployment.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
MGMT_CLUSTER_NAME="${MGMT_CLUSTER_NAME:-capd-quickstart-mgmt}"
WORKLOAD_CLUSTER_NAME="${WORKLOAD_CLUSTER_NAME:-capd-demo}"
NAMESPACE="${NAMESPACE:-metal3}"
KUBECONFIG_DIR="${SCRIPT_DIR}/.kubeconfigs"
MGMT_KUBECONFIG="${KUBECONFIG_DIR}/${MGMT_CLUSTER_NAME}.kubeconfig"
WORKLOAD_KUBECONFIG="${KUBECONFIG_DIR}/${WORKLOAD_CLUSTER_NAME}.kubeconfig"

echo
echo "============================================================"
echo " capd-quickstart"
echo "============================================================"
echo "Management cluster : ${MGMT_CLUSTER_NAME} (kind)"
echo "Workload cluster    : ${WORKLOAD_CLUSTER_NAME} (CAPD, this is what proves the platform works)"
echo

# ------------------------------------------------------------
# 0. Prerequisites
# ------------------------------------------------------------

for cmd in docker kind clusterctl kubectl jq curl; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        echo "ERROR: ${cmd} is required but not installed." >&2
        case "${cmd}" in
            kind)
                echo "  Install: curl -Lo ./kind https://github.com/kubernetes-sigs/kind/releases/latest/download/kind-linux-amd64 && chmod +x ./kind && sudo mv ./kind /usr/local/bin/" >&2
                ;;
            clusterctl)
                echo "  Install: see https://cluster-api.sigs.k8s.io/user/quick-start.html#install-clusterctl" >&2
                ;;
            jq)
                echo "  Install: apt-get install -y jq  (or your distro's equivalent)" >&2
                ;;
        esac
        exit 1
    fi
done

if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon isn't reachable (docker info failed). Start Docker and re-run." >&2
    exit 1
fi

mkdir -p "${KUBECONFIG_DIR}"

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    echo "ERROR: docker compose / docker-compose not found." >&2
    exit 1
fi

echo "[OK] All required tools present."
echo

# ------------------------------------------------------------
# 1. CAPD's required Docker network
# ------------------------------------------------------------

echo "[1/8] Ensuring the 'kind' Docker network exists (CAPD's load-balancer containers use it)..."
if ! docker network inspect kind >/dev/null 2>&1; then
    docker network create kind --opt com.docker.network.bridge.enable_ip_masquerade=true
    echo "[OK] Created."
else
    echo "[OK] Already exists."
fi
echo

# ------------------------------------------------------------
# 2. Management cluster (kind)
# ------------------------------------------------------------

echo "[2/8] Creating the management cluster (kind cluster '${MGMT_CLUSTER_NAME}')..."
if kind get clusters 2>/dev/null | grep -qx "${MGMT_CLUSTER_NAME}"; then
    echo "[OK] Already exists -- reusing it. Delete first if you want a clean run:"
    echo "     kind delete cluster --name ${MGMT_CLUSTER_NAME}"
else
    kind create cluster --name "${MGMT_CLUSTER_NAME}"
fi
kind get kubeconfig --name "${MGMT_CLUSTER_NAME}" > "${MGMT_KUBECONFIG}"
echo "[OK] Management cluster kubeconfig: ${MGMT_KUBECONFIG}"
echo

# ------------------------------------------------------------
# 3. Cluster API + CAPD onto the management cluster
# ------------------------------------------------------------

echo "[3/8] Installing Cluster API core + the Docker infrastructure provider (CAPD)..."
export KUBECONFIG="${MGMT_KUBECONFIG}"
if kubectl get deployment -n capd-system capd-controller-manager >/dev/null 2>&1; then
    echo "[OK] CAPD already installed on this management cluster."
else
    clusterctl init --infrastructure docker
fi

echo "Waiting for CAPI/CAPD controllers to be ready..."
kubectl wait --for=condition=Available --timeout=180s -n capi-system deployment/capi-controller-manager
kubectl wait --for=condition=Available --timeout=180s -n capi-kubeadm-bootstrap-system deployment/capi-kubeadm-bootstrap-controller-manager
kubectl wait --for=condition=Available --timeout=180s -n capi-kubeadm-control-plane-system deployment/capi-kubeadm-control-plane-controller-manager
kubectl wait --for=condition=Available --timeout=180s -n capd-system deployment/capd-controller-manager
echo "[OK] Controllers ready."
echo

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# ------------------------------------------------------------
# 4. This project's own stack, pointed at the management cluster
# ------------------------------------------------------------

echo "[4/8] Starting this project's backend, pointed at the management cluster..."
mkdir -p "${PROJECT_DIR}/deploy/kubeconfig"
cp "${MGMT_KUBECONFIG}" "${PROJECT_DIR}/deploy/kubeconfig/config"

if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
    echo "No .env found -- running ./scripts/install.sh to generate one (real, random secrets, not placeholders)."
    (cd "${PROJECT_DIR}" && ./scripts/install.sh)
fi

(cd "${PROJECT_DIR}" && "${COMPOSE_CMD[@]}" up -d --build)

echo "Waiting for the API to come up..."
for _ in $(seq 1 30); do
    if curl -s -o /dev/null -w '' http://localhost:8000/healthz --max-time 2 2>/dev/null; then
        break
    fi
    sleep 2
done
API_HEALTH="$(curl -s http://localhost:8000/healthz --max-time 5 || true)"
if [[ "${API_HEALTH}" != *'"ok"'* ]]; then
    echo "ERROR: API never became healthy. Check: ${COMPOSE_CMD[*]} logs api" >&2
    exit 1
fi
echo "[OK] API is healthy: ${API_HEALTH}"
echo

# ------------------------------------------------------------
# 5. Log in and create a docker-provider cluster via the REAL API
# ------------------------------------------------------------

echo "[5/8] Creating a Cluster (infrastructure_provider=docker) via this project's real API..."

ADMIN_PASSWORD_HINT="check '${COMPOSE_CMD[*]} logs api | grep \"Seeded initial admin\"' if you didn't set ADMIN_PASSWORD in .env"
read -r -p "Admin password (${ADMIN_PASSWORD_HINT}): " -s ADMIN_PASSWORD
echo

TOKEN="$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"admin\",\"password\":\"${ADMIN_PASSWORD}\"}" | jq -r '.access_token')"

if [[ -z "${TOKEN}" || "${TOKEN}" == "null" ]]; then
    echo "ERROR: Login failed -- check the admin password." >&2
    exit 1
fi
AUTH_HEADER="Authorization: Bearer ${TOKEN}"
echo "[OK] Logged in."

CLUSTER_RESPONSE="$(curl -s -X POST http://localhost:8000/api/v1/clusters \
    -H "${AUTH_HEADER}" -H "Content-Type: application/json" \
    -d "{
        \"name\": \"${WORKLOAD_CLUSTER_NAME}\",
        \"namespace\": \"${NAMESPACE}\",
        \"infrastructure_provider\": \"docker\",
        \"control_plane_count\": 1,
        \"worker_pools\": []
    }")"
CLUSTER_ID="$(echo "${CLUSTER_RESPONSE}" | jq -r '.id')"
if [[ -z "${CLUSTER_ID}" || "${CLUSTER_ID}" == "null" ]]; then
    echo "ERROR: Cluster creation failed:" >&2
    echo "${CLUSTER_RESPONSE}" | jq . >&2 || echo "${CLUSTER_RESPONSE}" >&2
    exit 1
fi
echo "[OK] Cluster created: ${CLUSTER_ID}"
echo

# ------------------------------------------------------------
# 6. Trigger the deployment
# ------------------------------------------------------------

echo "[6/8] Triggering deployment..."
DEPLOYMENT_RESPONSE="$(curl -s -X POST http://localhost:8000/api/v1/deployments \
    -H "${AUTH_HEADER}" -H "Content-Type: application/json" \
    -d "{\"cluster_id\": \"${CLUSTER_ID}\", \"regenerate_manifests\": true}")"
DEPLOYMENT_ID="$(echo "${DEPLOYMENT_RESPONSE}" | jq -r '.id')"
if [[ -z "${DEPLOYMENT_ID}" || "${DEPLOYMENT_ID}" == "null" ]]; then
    echo "ERROR: Deployment creation failed:" >&2
    echo "${DEPLOYMENT_RESPONSE}" | jq . >&2 || echo "${DEPLOYMENT_RESPONSE}" >&2
    exit 1
fi
echo "[OK] Deployment started: ${DEPLOYMENT_ID}"
echo

# ------------------------------------------------------------
# 7. Poll until it's done (or fails)
# ------------------------------------------------------------

echo "[7/8] Waiting for the workload cluster's control plane to come up..."
echo "      (this pulls the kindest/node image the first time, can take a few minutes)"
DEADLINE=$(($(date +%s) + 600))
LAST_PHASE=""
while true; do
    if [[ $(date +%s) -gt ${DEADLINE} ]]; then
        echo "ERROR: Timed out after 10 minutes waiting for deployment to complete." >&2
        exit 1
    fi
    STATUS_RESPONSE="$(curl -s "http://localhost:8000/api/v1/deployments/${DEPLOYMENT_ID}" -H "${AUTH_HEADER}")"
    PHASE="$(echo "${STATUS_RESPONSE}" | jq -r '.phase')"
    if [[ "${PHASE}" != "${LAST_PHASE}" ]]; then
        echo "  phase: ${PHASE}"
        LAST_PHASE="${PHASE}"
    fi
    if [[ "${PHASE}" == "complete" ]]; then
        break
    fi
    if [[ "${PHASE}" == "failed" ]]; then
        echo "ERROR: Deployment failed:" >&2
        echo "${STATUS_RESPONSE}" | jq -r '.error_message' >&2
        exit 1
    fi
    sleep 5
done
echo "[OK] Deployment complete."
echo

# ------------------------------------------------------------
# 8. The actual proof: fetch the workload cluster's own kubeconfig
#    and run kubectl get nodes against it
# ------------------------------------------------------------

echo "[8/8] Fetching the workload cluster's kubeconfig and checking real nodes..."
kubectl get secret -n "${NAMESPACE}" "${WORKLOAD_CLUSTER_NAME}-kubeconfig" \
    -o jsonpath='{.data.value}' | base64 -d > "${WORKLOAD_KUBECONFIG}"

echo
echo "============================================================"
echo " kubectl get nodes  (against the NEW cluster, not the management one)"
echo "============================================================"
KUBECONFIG="${WORKLOAD_KUBECONFIG}" kubectl get nodes -o wide

echo
echo "============================================================"
echo " Success"
echo "============================================================"
echo "A real Kubernetes cluster ('${WORKLOAD_CLUSTER_NAME}') was deployed end to end"
echo "through this platform's actual API -- create cluster -> trigger"
echo "deployment -> CAPI/CAPD provisions container-backed nodes -> a real"
echo "kube-apiserver answers kubectl. No physical hardware, no cloud account."
echo
echo "Workload cluster kubeconfig: ${WORKLOAD_KUBECONFIG}"
echo "  export KUBECONFIG=${WORKLOAD_KUBECONFIG}"
echo "  kubectl get pods -A"
echo
echo "Clean up everything this script created:"
echo "  ${SCRIPT_DIR}/teardown.sh"
echo "============================================================"
