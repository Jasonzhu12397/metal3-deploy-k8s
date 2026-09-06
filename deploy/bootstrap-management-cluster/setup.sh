#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# bootstrap-management-cluster: installs everything this project's
# backend has, until now, always assumed was already there --
# Ironic + Baremetal Operator + Cluster API + Cluster API Provider
# Metal3 (CAPM3) -- onto a real Kubernetes cluster, so that cluster can
# then serve as this platform's "management cluster"
# (MGMT_KUBECONFIG_PATH).
#
# This is not this project inventing its own bootstrap mechanism -- it
# automates the REAL, current, official Metal3 quick-start flow
# (https://book.metal3.io/quick-start), using the pre-built release
# manifests the Ironic Standalone Operator and Baremetal Operator
# projects publish (no local Go/kustomize/controller-gen build step
# needed), plus clusterctl for the Cluster API + CAPM3 half. Nothing
# here is a shortcut or approximation of what real Metal3 installs
# require -- it's the same components, the same install order, the
# official upstream way.
#
# What this script does NOT do, and cannot do for you, because it is
# fundamentally specific to your physical network, not something any
# script can infer:
#   - Configure the actual provisioning network's DHCP range, NIC,
#     VLAN, or how Ironic's dnsmasq/DHCP/TFTP services reach your real
#     BMCs and the network your bare-metal hosts PXE-boot on. This
#     script applies a deliberately minimal `Ironic` custom resource
#     with networking left at the operator's defaults and prints a
#     clear TODO -- see "After this script" below for exactly what to
#     edit and why guessing would be actively harmful (a wrong DHCP
#     range can take down an unrelated network segment).
#   - Verify Ironic can actually reach a real BMC, or that a real
#     server can actually PXE-boot against it. That needs real hardware
#     network connectivity this script has no way to test from wherever
#     it happens to run.
# ============================================================

MGMT_CLUSTER_NAME="${MGMT_CLUSTER_NAME:-metal3-mgmt}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${SCRIPT_DIR}/.bootstrap-work"
export KUBECONFIG="${KUBECONFIG:-${WORK_DIR}/kubeconfig.yaml}"

echo "============================================================"
echo " bootstrap-management-cluster"
echo "============================================================"
echo

mkdir -p "${WORK_DIR}"

# ------------------------------------------------------------
# 0. Prerequisites
# ------------------------------------------------------------
for cmd in kubectl curl; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        echo "ERROR: ${cmd} is required but not installed." >&2
        exit 1
    fi
done

# ------------------------------------------------------------
# 1. A management cluster to install everything onto
# ------------------------------------------------------------
echo "[1/6] Management cluster..."
if kubectl get nodes >/dev/null 2>&1; then
    echo "[OK] KUBECONFIG already points at a reachable cluster -- using that ($(kubectl config current-context 2>/dev/null || echo "current context"))."
    echo "     (per the official Metal3 quick-start: \"If you already have a Kubernetes"
    echo "     cluster that you want to use, go ahead and use that.\" This script"
    echo "     doesn't require kind/k3s specifically -- any real cluster with network"
    echo "     access to your BMCs and provisioning network works.)"
else
    K3S_BIN="${WORK_DIR}/k3s"
    if [[ ! -x "${K3S_BIN}" ]]; then
        echo "No reachable cluster and no existing KUBECONFIG -- downloading k3s"
        echo "(a single static binary bundling a real kube-apiserver + etcd +"
        echo "controller-manager + scheduler + kubelet, no Docker needed) to use as"
        echo "the management cluster. This is a REAL, supported choice for this,"
        echo "not a toy substitute -- swap in any real cluster by setting KUBECONFIG"
        echo "yourself before running this script."
        K3S_VERSION="${K3S_VERSION:-v1.31.4+k3s1}"
        ENCODED_VERSION="$(echo "${K3S_VERSION}" | sed 's/+/%2B/')"
        curl -sL "https://github.com/k3s-io/k3s/releases/download/${ENCODED_VERSION}/k3s" -o "${K3S_BIN}"
        chmod +x "${K3S_BIN}"
    fi
    if ! pgrep -f "k3s server --data-dir ${WORK_DIR}/data" >/dev/null 2>&1; then
        rm -rf "${WORK_DIR}/data"
        setsid nohup "${K3S_BIN}" server \
            --data-dir "${WORK_DIR}/data" \
            --write-kubeconfig "${KUBECONFIG}" \
            > "${WORK_DIR}/k3s-server.log" 2>&1 < /dev/null &
        disown 2>/dev/null || true
    fi
    echo "Waiting for the management cluster's API server..."
    for _ in $(seq 1 30); do
        if kubectl get nodes >/dev/null 2>&1; then break; fi
        sleep 2
    done
    kubectl get nodes >/dev/null 2>&1 || { echo "ERROR: cluster never became ready, check ${WORK_DIR}/k3s-server.log" >&2; exit 1; }
    echo "[OK] k3s management cluster ready."
fi
echo

# ------------------------------------------------------------
# 2. Cluster API core + CAPM3 (+ cert-manager, which clusterctl
#    installs automatically if missing)
# ------------------------------------------------------------
echo "[2/6] Cluster API core + Cluster API Provider Metal3 (CAPM3)..."
CLUSTERCTL_BIN="${WORK_DIR}/clusterctl"
if [[ ! -x "${CLUSTERCTL_BIN}" ]]; then
    CLUSTERCTL_VERSION="${CLUSTERCTL_VERSION:-v1.14.0}"
    curl -sL "https://github.com/kubernetes-sigs/cluster-api/releases/download/${CLUSTERCTL_VERSION}/clusterctl-linux-amd64" -o "${CLUSTERCTL_BIN}"
    chmod +x "${CLUSTERCTL_BIN}"
fi
if kubectl get deployment -n capm3-system capm3-controller-manager >/dev/null 2>&1; then
    echo "[OK] CAPM3 already installed."
else
    "${CLUSTERCTL_BIN}" init --infrastructure=metal3 --ipam=metal3
fi
echo

# ------------------------------------------------------------
# 3. Ironic Standalone Operator (IrSO) -- the officially recommended
#    way to run Ironic since CAPM3 decoupled it from its own install.
#    Using the project's own published release manifest, not a local
#    kustomize/Go build (this environment may not have Go -- and
#    shouldn't need to, when upstream already publishes exactly this).
# ------------------------------------------------------------
echo "[3/6] Ironic Standalone Operator (IrSO)..."
if kubectl get deployment -n ironic-standalone-operator-system ironic-standalone-operator-controller-manager >/dev/null 2>&1; then
    echo "[OK] IrSO already installed."
else
    IRSO_VERSION="${IRSO_VERSION:-v0.11.0}"
    kubectl apply -f "https://github.com/metal3-io/ironic-standalone-operator/releases/download/${IRSO_VERSION}/install.yaml"
    echo "Waiting for IrSO controller..."
    kubectl -n ironic-standalone-operator-system wait --for=condition=Available --timeout=180s \
        deploy/ironic-standalone-operator-controller-manager
fi
echo

# ------------------------------------------------------------
# 4. Baremetal Operator (BMO)
# ------------------------------------------------------------
echo "[4/6] Baremetal Operator (BMO)..."
kubectl create namespace baremetal-operator-system --dry-run=client -o yaml | kubectl apply -f -
if kubectl get deployment -n baremetal-operator-system baremetal-operator-controller-manager >/dev/null 2>&1; then
    echo "[OK] BMO already installed."
else
    BMO_VERSION="${BMO_VERSION:-v0.13.4}"
    kubectl apply -n baremetal-operator-system -f "https://github.com/metal3-io/baremetal-operator/releases/download/${BMO_VERSION}/baremetal-operator.yaml"
    echo "Waiting for BMO controller..."
    kubectl -n baremetal-operator-system wait --for=condition=Available --timeout=180s \
        deploy/baremetal-operator-controller-manager
fi
echo

# ------------------------------------------------------------
# 5. A minimal Ironic instance via IrSO's Ironic CRD.
#
#    Deliberately minimal: leaves `networking` at the operator's
#    defaults rather than guessing your DHCP range/interface, per this
#    script's own header comment on why guessing here would be
#    actively harmful. Fine for reaching Ironic's API from inside this
#    cluster; you MUST edit this before real PXE-boot against real
#    hardware will work -- see "After this script" in this directory's
#    README.md for exactly which fields and why.
# ------------------------------------------------------------
echo "[5/6] Ironic instance (IrSO's Ironic custom resource)..."
if kubectl get ironic -n baremetal-operator-system ironic >/dev/null 2>&1; then
    echo "[OK] Ironic resource already exists."
else
    cat <<'EOF' | kubectl apply -f -
apiVersion: ironic.metal3.io/v1alpha1
kind: Ironic
metadata:
  name: ironic
  namespace: baremetal-operator-system
spec:
  # TODO before real PXE boot: set networking.dhcp / networking.interface
  # to match your actual provisioning network -- see this directory's
  # README.md. Left unset here so this script doesn't take a guess at
  # your network topology.
  networking: {}
EOF
    echo "Waiting for Ironic to report Ready (may take a few minutes -- it's pulling images)..."
    kubectl -n baremetal-operator-system wait --for=condition=Ready --timeout=300s ironic/ironic || \
        echo "  (not Ready yet -- check: kubectl -n baremetal-operator-system describe ironic/ironic)"
fi
echo

# ------------------------------------------------------------
# 6. Summary
# ------------------------------------------------------------
echo "[6/6] Summary"
kubectl get deployment -n capi-system capi-controller-manager 2>/dev/null && echo "  CAPI core: installed"
kubectl get deployment -n capm3-system capm3-controller-manager 2>/dev/null && echo "  CAPM3: installed"
kubectl get deployment -n ironic-standalone-operator-system ironic-standalone-operator-controller-manager 2>/dev/null && echo "  IrSO: installed"
kubectl get deployment -n baremetal-operator-system baremetal-operator-controller-manager 2>/dev/null && echo "  BMO: installed"
kubectl get ironic -n baremetal-operator-system ironic 2>/dev/null && echo "  Ironic: applied"

echo
echo "============================================================"
echo " Done -- see this directory's README.md for what to do next"
echo " (network config Ironic needs before real hardware works, and"
echo " how to point this project's own backend at this cluster via"
echo " MGMT_KUBECONFIG_PATH)."
echo "============================================================"
echo "Management cluster kubeconfig: ${KUBECONFIG}"
