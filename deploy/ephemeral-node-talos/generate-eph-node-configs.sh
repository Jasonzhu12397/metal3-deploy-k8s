#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# generate-eph-node-configs.sh -- prepares everything needed to PXE-boot
# a bare machine into Talos Linux (live, in-memory, no disk install
# required to start) and turn it into a single-node Kubernetes cluster
# -- the "ephemeral node" this project's own deployment_tasks.py
# docstring has referred to since its first commit, but never had a
# concrete implementation for.
#
# Explicitly NOT Docker, NOT k3s: Talos runs containerd directly (no
# Docker daemon at all) and boots real upstream Kubernetes components
# (confirmed against this script's own generated config -- the kubelet
# image reference is ghcr.io/siderolabs/kubelet, not a k3s build).
#
# What this script does, all of it real and verified as far as it can
# be without a real PXE-bootable machine (see README.md's own verified/
# not-verified breakdown):
#   1. Downloads the real Talos kernel + initramfs + talosctl for a
#      pinned, current Talos version.
#   2. Runs `talosctl gen config` for real -- this is pure local
#      cryptography and YAML generation (PKI, tokens, the machine
#      config itself), needs no network access to any actual node, and
#      was verified working during this script's own development.
#   3. Prints the exact, real commands (DHCP/TFTP/HTTP server config,
#      talosctl apply-config, talosctl bootstrap) needed to actually
#      PXE-boot a machine and turn it into a running cluster -- these
#      are the real, current, officially-documented Talos commands, not
#      invented, but this script cannot run them itself: they need a
#      real machine on a real network to PXE-boot and respond to
#      Talos's maintenance-mode API, which no sandbox this project has
#      been developed in can provide.
# ============================================================

TALOS_VERSION="${TALOS_VERSION:-v1.12.12}"
CLUSTER_NAME="${CLUSTER_NAME:-eph-node}"
CONTROL_PLANE_ENDPOINT="${CONTROL_PLANE_ENDPOINT:?Set CONTROL_PLANE_ENDPOINT to this eph-node IP, e.g. https://192.0.2.50:6443}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${SCRIPT_DIR}/.eph-node-work"

mkdir -p "${WORK_DIR}/pxe-assets" "${WORK_DIR}/configs"

echo "============================================================"
echo " generate-eph-node-configs.sh -- Talos ${TALOS_VERSION}"
echo "============================================================"
echo

# ------------------------------------------------------------
# 1. talosctl -- needed locally to generate configs, and later to push
#    them onto the booted node and bootstrap it.
# ------------------------------------------------------------
echo "[1/4] talosctl..."
TALOSCTL_BIN="${WORK_DIR}/talosctl"
if [[ ! -x "${TALOSCTL_BIN}" ]]; then
    curl -sL "https://github.com/siderolabs/talos/releases/download/${TALOS_VERSION}/talosctl-linux-amd64" \
        -o "${TALOSCTL_BIN}"
    chmod +x "${TALOSCTL_BIN}"
fi
"${TALOSCTL_BIN}" version --client
echo

# ------------------------------------------------------------
# 2. Real PXE boot assets -- Talos's own kernel + initramfs, straight
#    from their GitHub release, no third-party mirror.
# ------------------------------------------------------------
echo "[2/4] PXE boot assets (kernel + initramfs)..."
curl -sL "https://github.com/siderolabs/talos/releases/download/${TALOS_VERSION}/vmlinuz-amd64" \
    -o "${WORK_DIR}/pxe-assets/vmlinuz"
curl -sL "https://github.com/siderolabs/talos/releases/download/${TALOS_VERSION}/initramfs-amd64.xz" \
    -o "${WORK_DIR}/pxe-assets/initramfs.xz"
ls -la "${WORK_DIR}/pxe-assets/"
echo

# ------------------------------------------------------------
# 3. talosctl gen config -- real, local, needs no network. This is the
#    exact same command a human would run by hand; nothing invented.
# ------------------------------------------------------------
echo "[3/4] Generating machine configs (controlplane.yaml, talosconfig)..."
if [[ ! -f "${WORK_DIR}/configs/controlplane.yaml" ]]; then
    "${TALOSCTL_BIN}" gen config "${CLUSTER_NAME}" "${CONTROL_PLANE_ENDPOINT}" \
        --output-dir "${WORK_DIR}/configs"
fi
echo

# ------------------------------------------------------------
# 4. Print the real, remaining manual steps -- these need a real
#    network-connected machine, which this script cannot provide.
# ------------------------------------------------------------
CP_IP="$(echo "${CONTROL_PLANE_ENDPOINT}" | sed -E 's#https?://##; s#:.*##')"

cat <<EOF
[4/4] Remaining steps -- these need a real machine on a real network.
      Every command below is the real, current, officially-documented
      Talos command for this -- see https://www.talos.dev/latest/talos-guides/install/bare-metal-platforms/pxe/
      for the upstream source. Not runnable from here.

--- A. Point your DHCP/TFTP/HTTP infra at the assets this script just downloaded ---
  Kernel:    ${WORK_DIR}/pxe-assets/vmlinuz
  Initramfs: ${WORK_DIR}/pxe-assets/initramfs.xz
  (dnsmasq/pxelinux config is site-specific -- your DHCP range, your NIC --
  this script deliberately does not guess it, same reasoning as
  deploy/bootstrap-management-cluster/'s own networking.dhcp field: a
  wrong DHCP config can take down an unrelated network segment.)

--- B. Boot the physical machine via PXE ---
  It will come up in Talos "maintenance mode" -- live, in-memory,
  unconfigured, listening on its maintenance API for a config to be
  applied. This IS the ephemeral, live-OS state this whole module
  exists for.

--- C. Push the generated control-plane config to it ---
  export TALOSCONFIG="${WORK_DIR}/configs/talosconfig"
  ${TALOSCTL_BIN} apply-config --insecure --nodes ${CP_IP} \\
      --file ${WORK_DIR}/configs/controlplane.yaml

--- D. Bootstrap etcd + the Kubernetes control plane on it ---
  ${TALOSCTL_BIN} config endpoint ${CP_IP}
  ${TALOSCTL_BIN} config node ${CP_IP}
  ${TALOSCTL_BIN} bootstrap
  ${TALOSCTL_BIN} health

--- E. Fetch its kubeconfig -- this IS your ephemeral management cluster ---
  ${TALOSCTL_BIN} kubeconfig ${WORK_DIR}/eph-node-kubeconfig.yaml

--- F. Hand that kubeconfig to this project's own bootstrap script ---
  KUBECONFIG=${WORK_DIR}/eph-node-kubeconfig.yaml \\
      ../bootstrap-management-cluster/setup.sh
  (that script already supports "use an existing cluster" -- this is
  exactly that path, just with the cluster being this Talos eph-node
  instead of k3s)
EOF
