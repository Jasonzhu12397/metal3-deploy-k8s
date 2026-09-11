#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# download-assets.sh -- downloads every NON-container-image file this
# project's Talos-based path needs from the public internet (binaries,
# YAML manifests, the Talos disk image) into one local directory, so
# they can be re-served from a local HTTP file server the customer's
# actual (disconnected) network can reach -- the file-based complement
# to mirror-images.sh's container-image mirroring.
#
# Run this on the same internet-connected jump box as mirror-images.sh.
# Real, current URLs throughout -- the same ones
# deploy/ephemeral-node-talos/generate-eph-node-configs.sh,
# deploy/bootstrap-management-cluster/setup.sh, and
# templates/capi/providers/talos-metal3.yaml.j2 already reference
# individually; this script exists so you download them ONCE, to files,
# rather than each of those needing its own network path to GitHub
# every time it runs.
# ============================================================

TALOS_VERSION="${TALOS_VERSION:-v1.12.12}"
CABPT_VERSION="${CABPT_VERSION:-v0.6.5}"
CACPPT_VERSION="${CACPPT_VERSION:-v0.5.7}"
IRSO_VERSION="${IRSO_VERSION:-v0.11.0}"
BMO_VERSION="${BMO_VERSION:-v0.13.4}"
CERT_MANAGER_VERSION="${CERT_MANAGER_VERSION:-v1.16.2}"
CLUSTERCTL_VERSION="${CLUSTERCTL_VERSION:-v1.14.0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/.bundle/assets"
mkdir -p "${OUT_DIR}/manifests" "${OUT_DIR}/binaries" "${OUT_DIR}/pxe" "${OUT_DIR}/disk-images"

echo "============================================================"
echo " download-assets.sh"
echo "============================================================"
echo

fetch() {
    local url="$1" dest="$2"
    if [[ -f "${dest}" ]]; then
        echo "[OK] already have ${dest}"
        return
    fi
    echo "  ${url}"
    curl -fsSL "${url}" -o "${dest}.part" && mv "${dest}.part" "${dest}"
}

echo "[1/6] Binaries..."
fetch "https://github.com/siderolabs/talos/releases/download/${TALOS_VERSION}/talosctl-linux-amd64" \
    "${OUT_DIR}/binaries/talosctl"
fetch "https://github.com/kubernetes-sigs/cluster-api/releases/download/${CLUSTERCTL_VERSION}/clusterctl-linux-amd64" \
    "${OUT_DIR}/binaries/clusterctl"
chmod +x "${OUT_DIR}/binaries/"* 2>/dev/null || true
echo

echo "[2/6] Talos PXE boot assets (kernel + initramfs) for the ephemeral node..."
fetch "https://github.com/siderolabs/talos/releases/download/${TALOS_VERSION}/vmlinuz-amd64" \
    "${OUT_DIR}/pxe/vmlinuz"
fetch "https://github.com/siderolabs/talos/releases/download/${TALOS_VERSION}/initramfs-amd64.xz" \
    "${OUT_DIR}/pxe/initramfs.xz"
echo

echo "[3/6] Talos disk image (target cluster nodes)..."
fetch "https://github.com/siderolabs/talos/releases/download/${TALOS_VERSION}/metal-amd64.raw.zst" \
    "${OUT_DIR}/disk-images/metal-amd64.raw.zst"
echo

echo "[4/6] CABPT + CACPPT (Talos's own Cluster API providers)..."
fetch "https://github.com/siderolabs/cluster-api-bootstrap-provider-talos/releases/download/${CABPT_VERSION}/bootstrap-components.yaml" \
    "${OUT_DIR}/manifests/cabpt-bootstrap-components.yaml"
fetch "https://github.com/siderolabs/cluster-api-control-plane-provider-talos/releases/download/${CACPPT_VERSION}/control-plane-components.yaml" \
    "${OUT_DIR}/manifests/cacppt-control-plane-components.yaml"
echo

echo "[5/6] cert-manager + IrSO + BMO (deploy/bootstrap-management-cluster/'s own dependencies)..."
fetch "https://github.com/cert-manager/cert-manager/releases/download/${CERT_MANAGER_VERSION}/cert-manager.yaml" \
    "${OUT_DIR}/manifests/cert-manager.yaml"
fetch "https://github.com/metal3-io/ironic-standalone-operator/releases/download/${IRSO_VERSION}/install.yaml" \
    "${OUT_DIR}/manifests/irso-install.yaml"
fetch "https://github.com/metal3-io/baremetal-operator/releases/download/${BMO_VERSION}/baremetal-operator.yaml" \
    "${OUT_DIR}/manifests/bmo.yaml"
echo

echo "[6/6] Done."
echo
echo "============================================================"
echo " Everything is under ${OUT_DIR}/ -- serve this directory over"
echo " HTTP from wherever your customer's actual network can reach it,"
echo " then:"
echo "   - point the PXE config at pxe/vmlinuz + pxe/initramfs.xz from"
echo "     there instead of GitHub"
echo "   - set cluster_spec.image_url (see USAGE.md 1.2) to"
echo "     disk-images/metal-amd64.raw.zst from there"
echo "   - kubectl apply -f the manifests/ files directly instead of"
echo "     their github.com URLs in deploy/bootstrap-management-cluster/setup.sh"
echo "============================================================"
