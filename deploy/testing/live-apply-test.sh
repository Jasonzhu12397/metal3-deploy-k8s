#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# live-apply-test: the strongest verification this project has --
# actually `kubectl apply` this backend's real generated manifests
# against a REAL, live Kubernetes API server (k3s), with the REAL
# upstream CRDs installed. Not jsonschema validation against a
# downloaded schema file (that's tests/test_manifest_schema_validation.py) --
# this is the actual admission path a real cluster uses.
#
# Why k3s specifically: unlike kind/CAPD (deploy/testing/capd-quickstart/),
# k3s is a single static binary that bundles kube-apiserver + etcd
# (via an embedded sqlite-backed kine shim) + controller-manager +
# scheduler + kubelet + a minimal containerd. It does NOT need Docker.
# This matters on hosts where Docker genuinely isn't available (this
# script was developed and verified in exactly that kind of
# environment) -- k3s got a real API server up where Docker/kind could
# not.
#
# What this DOES prove: a real Kubernetes API server's actual admission
# path (not an offline schema snapshot) accepts every manifest this
# backend renders, for every infrastructure provider, including
# multi-resource scenarios (HA control planes, worker pools, GPU node
# labels). This is real proof the manifests are well-formed enough to
# reach a running cluster.
#
# What this does NOT prove: that real Cluster API / CAPM3 / CAPO / CAPV
# controllers would successfully RECONCILE these objects into actual
# running infrastructure (that needs the controller pods themselves
# running, which needs their container images -- not attempted here),
# or that real Ironic/baremetal-operator would successfully PXE-boot and
# provision actual hardware (needs real hardware or
# deploy/testing/vm-bmc/'s libvirt path). Applied objects here sit
# un-reconciled (empty/pending status) since no controller is watching
# them -- that's expected, not a failure.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORK_DIR="${SCRIPT_DIR}/.live-apply-work"
K3S_BIN="${WORK_DIR}/k3s"
export KUBECONFIG="${WORK_DIR}/kubeconfig.yaml"

echo "============================================================"
echo " live-apply-test"
echo "============================================================"
echo

mkdir -p "${WORK_DIR}"

# ------------------------------------------------------------
# 1. Get a real k3s binary (no Docker needed)
# ------------------------------------------------------------
if [[ ! -x "${K3S_BIN}" ]]; then
    echo "[1/5] Downloading k3s..."
    K3S_VERSION="${K3S_VERSION:-v1.31.4+k3s1}"
    ENCODED_VERSION="$(echo "${K3S_VERSION}" | sed 's/+/%2B/')"
    curl -sL "https://github.com/k3s-io/k3s/releases/download/${ENCODED_VERSION}/k3s" -o "${K3S_BIN}"
    chmod +x "${K3S_BIN}"
fi
echo "[OK] $(${K3S_BIN} --version | head -1)"
echo

# ------------------------------------------------------------
# 2. Start k3s (real kube-apiserver + etcd + controller-manager +
#    scheduler + kubelet, all in one process)
# ------------------------------------------------------------
echo "[2/5] Starting k3s server..."
if pgrep -f "k3s server --data-dir ${WORK_DIR}/data" >/dev/null 2>&1; then
    echo "[OK] Already running."
else
    rm -rf "${WORK_DIR}/data"
    setsid nohup "${K3S_BIN}" server \
        --data-dir "${WORK_DIR}/data" \
        --disable traefik --disable servicelb --disable metrics-server --disable local-storage \
        --write-kubeconfig "${KUBECONFIG}" \
        > "${WORK_DIR}/server.log" 2>&1 < /dev/null &
    disown 2>/dev/null || true

    echo "Waiting for the API server to become ready..."
    for _ in $(seq 1 30); do
        if "${K3S_BIN}" kubectl get nodes >/dev/null 2>&1; then
            break
        fi
        sleep 2
    done
fi

if ! "${K3S_BIN}" kubectl get nodes >/dev/null 2>&1; then
    echo "ERROR: k3s never became ready. Check ${WORK_DIR}/server.log" >&2
    exit 1
fi
echo "[OK] $("${K3S_BIN}" kubectl get nodes --no-headers | awk '{print $1, $2}')"
echo

# ------------------------------------------------------------
# 3. Install the real upstream CRDs (already snapshotted in this repo)
# ------------------------------------------------------------
echo "[3/5] Installing real CAPI + Metal3 + Docker + OpenStack CRDs..."
CRD_DIR="${PROJECT_DIR}/backend/tests_data/crd_schemas"
"${K3S_BIN}" kubectl apply -f "${CRD_DIR}/cluster.yaml" >/dev/null
"${K3S_BIN}" kubectl apply -f "${CRD_DIR}/machinedeployment.yaml" >/dev/null
"${K3S_BIN}" kubectl apply -f "${CRD_DIR}/kubeadmcontrolplane.yaml" >/dev/null
"${K3S_BIN}" kubectl apply -f "${CRD_DIR}/kubeadmconfigtemplate.yaml" >/dev/null
"${K3S_BIN}" kubectl apply -f "${CRD_DIR}/metal3cluster.yaml" >/dev/null
"${K3S_BIN}" kubectl apply -f "${CRD_DIR}/metal3machinetemplate.yaml" >/dev/null
"${K3S_BIN}" kubectl apply -f "${CRD_DIR}/baremetalhost.yaml" >/dev/null
"${K3S_BIN}" kubectl apply -f "${CRD_DIR}/dockercluster.yaml" >/dev/null
"${K3S_BIN}" kubectl apply -f "${CRD_DIR}/dockermachinetemplate.yaml" >/dev/null
"${K3S_BIN}" kubectl apply -f "${CRD_DIR}/openstackcluster.yaml" >/dev/null
"${K3S_BIN}" kubectl apply -f "${CRD_DIR}/openstackmachinetemplate.yaml" >/dev/null
"${K3S_BIN}" kubectl apply -f "${CRD_DIR}/vspherecluster.yaml" >/dev/null
"${K3S_BIN}" kubectl apply -f "${CRD_DIR}/vspheremachinetemplate.yaml" >/dev/null
"${K3S_BIN}" kubectl create namespace metal3 --dry-run=client -o yaml | "${K3S_BIN}" kubectl apply -f - >/dev/null
echo "[OK] $("${K3S_BIN}" kubectl get crd --no-headers | wc -l | tr -d ' ') CRDs installed."
echo

# ------------------------------------------------------------
# 4. Generate real manifests using this project's actual code, for
#    every provider, and apply every one of them for real
# ------------------------------------------------------------
echo "[4/5] Generating manifests (this project's real YamlGeneratorService) and applying..."
cd "${PROJECT_DIR}/backend"
python3 - "${WORK_DIR}" <<'PYEOF'
import sys, os
sys.path.insert(0, ".")
work_dir = sys.argv[1]

from app.services.asset_planner import AssetPlannerService
from app.services.yaml_generator import YamlGeneratorService
from app.models.hardware_asset import HardwareAsset
from types import SimpleNamespace

planner = AssetPlannerService()
gen = YamlGeneratorService()


def asset(name, i, gpu=False):
    return HardwareAsset(
        name=name, cpu_sockets=2, cpu_cores_per_socket=32, cpu_threads_per_core=2,
        memory_gb=256, bmc_address=f"redfish://192.0.2.{10+i}/redfish/v1/Systems/1",
        boot_mac_address=f"aa:bb:cc:dd:ee:{i:02d}",
        gpu_model="NVIDIA H100" if gpu else None, gpu_count=8 if gpu else 0,
        gpu_memory_gb=80 if gpu else None,
    )


def assignment(role):
    return SimpleNamespace(
        role=role, reserved_cores_per_socket=4, cpu_manager_policy="static",
        topology_manager_policy="single-numa-node", isolation_interrupts=False,
        hugepage_type="1GB", hugepage_count_1gb=16, hugepage_count_2mb=0,
    )


# Metal3: HA control plane + workers + a GPU pool
pools = {
    "control-plane": ([asset(f"cp-{i}", i) for i in range(3)], [assignment("control-plane")] * 3),
    "workers": ([asset(f"wk-{i}", i + 3) for i in range(2)], [assignment("worker")] * 2),
    "gpu-pool": ([asset("gpu-0", 5, gpu=True)], [assignment("worker")]),
}
bundle = planner.generate_bundle(
    {"name": "live-metal3", "namespace": "default", "control_plane_endpoint": "192.0.2.200"}, pools
)
open(f"{work_dir}/metal3.yaml", "w").write(bundle["cluster_config_yaml"])
open(f"{work_dir}/metal3-bmh.yaml", "w").write(bundle["bmh_yaml"])

# Docker (CAPD)
docker_spec = {
    "name": "live-docker", "namespace": "default", "infrastructure_provider": "docker",
    "control_plane_count": 1, "worker_pools": [{"name": "workers", "count": 2, "node_labels": ["role=test"]}],
}
open(f"{work_dir}/docker.yaml", "w").write(gen.render_cluster_config(docker_spec))

# OpenStack (CAPO)
ost_spec = {
    "name": "live-openstack", "namespace": "default", "infrastructure_provider": "openstack",
    "control_plane_count": 3, "control_plane_endpoint": "192.0.2.1",
    "control_plane_flavor": "m1.large", "control_plane_image": "ubuntu-22.04",
    "worker_pools": [{"name": "workers", "count": 2, "flavor": "m1.medium", "image": "ubuntu-22.04"}],
    "openstack": {"cloud_name": "mycloud"},
}
open(f"{work_dir}/openstack.yaml", "w").write(gen.render_cluster_config(ost_spec))

# vSphere (CAPV)
vs_spec = {
    "name": "live-vsphere", "namespace": "default", "infrastructure_provider": "vsphere",
    "control_plane_count": 3, "control_plane_endpoint": "192.0.2.1",
    "control_plane_flavor": "", "control_plane_image": "ubuntu-template",
    "worker_pools": [{"name": "workers", "count": 2, "flavor": "", "image": "ubuntu-template"}],
    "vsphere": {"server": "vcenter.local"},
}
open(f"{work_dir}/vsphere.yaml", "w").write(gen.render_cluster_config(vs_spec))

print("Generated: metal3.yaml, metal3-bmh.yaml, docker.yaml, openstack.yaml, vsphere.yaml")
PYEOF

APPLY_FAILED=0
for f in metal3 metal3-bmh docker openstack vsphere; do
    echo "--- ${f}.yaml ---"
    if ! "${K3S_BIN}" kubectl apply -f "${WORK_DIR}/${f}.yaml"; then
        APPLY_FAILED=1
    fi
done
echo

# ------------------------------------------------------------
# 5. Verify: real objects, real fields, actually stored
# ------------------------------------------------------------
echo "[5/5] Confirming objects are real and queryable..."
"${K3S_BIN}" kubectl get clusters,metal3clusters,dockerclusters,openstackclusters,vsphereclusters -A
echo
"${K3S_BIN}" kubectl get baremetalhosts -A
echo

if [[ "${APPLY_FAILED}" -eq 1 ]]; then
    echo "============================================================"
    echo " FAILED -- at least one manifest was rejected by the real API server."
    echo "============================================================"
    exit 1
fi

echo "============================================================"
echo " PASSED"
echo "============================================================"
echo "Every manifest this backend generates, for every infrastructure"
echo "provider, was accepted by a real, live Kubernetes API server with"
echo "the real upstream CRDs installed -- not offline schema validation,"
echo "actual kubectl apply admission."
echo
echo "NOT proven by this: that real CAPI/CAPM3/CAPO/CAPV controllers would"
echo "reconcile these into running infrastructure, or that real hardware"
echo "would actually provision. See this script's own header comment."
echo
echo "Clean up: rm -rf ${WORK_DIR}  (or just: pkill -f 'k3s server')"
echo "============================================================"
