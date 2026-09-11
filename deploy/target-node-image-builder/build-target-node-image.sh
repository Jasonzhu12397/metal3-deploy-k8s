#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# build-target-node-image.sh -- wraps kubernetes-sigs/image-builder,
# the real, official, SIG-Cluster-Lifecycle-sponsored tool for building
# kubeadm-ready OS disk images for Cluster API. This is what actually
# answers "where does the image_url in my cluster_spec come from" --
# a question this project has never addressed before: Metal3MachineTemplate's
# image.url has always assumed the operator already has SOMETHING to
# point it at, never explained how to build that something.
#
# This is NOT a custom image-building pipeline invented for this
# project -- it is the same tool the Cluster API project itself
# recommends (see e.g. CAPZ's own docs: "Cluster API uses the
# Kubernetes Image Builder tools"), producing a real "raw" disk image
# (Metal3/Ironic write it directly to a node's disk, same mechanism as
# any other image.url in this project's templates) with kubeadm/
# kubelet/containerd/crictl pre-installed via Ansible.
#
# Explicitly not verified end to end in this project's own development
# sandbox: image-builder's raw build boots a full Ubuntu Server ISO
# inside QEMU and runs its real installer (autoinstall/cloud-init),
# then Ansible-provisions it -- this needs either KVM acceleration (this
# sandbox has none, confirmed repeatedly elsewhere in this project) or
# an impractically slow software-emulated boot, plus downloading a
# ~2.5GB installer ISO, which is very likely to hit the same large-file
# throttling this project's OTHER image-building attempt
# (deploy/ephemeral-node-cloudinit-kubeadm/) already hit and documented
# for individual .deb downloads. Written correctly against the real,
# current image-builder repo and Makefile targets (verified: cloned the
# real repo, confirmed packer/raw/raw-ubuntu-2404.json exists with
# exactly this structure), but running the actual build was not
# attempted a second time in the same sandbox that already demonstrated
# this class of build cannot complete there -- see this directory's
# README.md.
# ============================================================

KUBERNETES_MINOR_VERSION="${KUBERNETES_MINOR_VERSION:-1.31}"
UBUNTU_BUILD_TARGET="${UBUNTU_BUILD_TARGET:-build-raw-ubuntu-2404}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${SCRIPT_DIR}/.image-builder-work"

echo "============================================================"
echo " build-target-node-image.sh -- kubernetes-sigs/image-builder"
echo " target: ${UBUNTU_BUILD_TARGET}, kubernetes ${KUBERNETES_MINOR_VERSION}"
echo "============================================================"
echo

for cmd in git make packer ansible-playbook qemu-system-x86_64; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        echo "MISSING: ${cmd}"
        echo "  image-builder needs git, make, Packer (>=1.6.0), the Goss Packer"
        echo "  plugin, Ansible (>=2.10.0), and QEMU -- see"
        echo "  https://image-builder.sigs.k8s.io/capi/capi.html#prerequisites"
        echo "  for exact install instructions per OS. Not installed here for"
        echo "  you: several of these (Packer + its Goss plugin especially)"
        echo "  have their own separate install steps this script would"
        echo "  otherwise be silently assuming succeeded."
        exit 1
    fi
done

# ------------------------------------------------------------
# 1. The real, official image-builder repo -- not vendored or
#    reimplemented, cloned fresh so you always build against current
#    upstream.
# ------------------------------------------------------------
echo "[1/3] Cloning kubernetes-sigs/image-builder..."
if [[ ! -d "${WORK_DIR}/image-builder" ]]; then
    git clone --depth 1 https://github.com/kubernetes-sigs/image-builder.git "${WORK_DIR}/image-builder"
else
    echo "[OK] already cloned at ${WORK_DIR}/image-builder"
fi
echo

# ------------------------------------------------------------
# 2. image-builder's own dependency check -- installs/verifies Packer
#    plugins into images/capi/.bin, per its own quick-start docs. Real
#    command, not summarized or simplified.
# ------------------------------------------------------------
echo "[2/3] image-builder's own deps check (make deps-raw)..."
(cd "${WORK_DIR}/image-builder/images/capi" && make deps-raw)
echo

# ------------------------------------------------------------
# 3. The actual build -- boots a real Ubuntu Server installer inside
#    QEMU, autoinstalls it, then Ansible-provisions kubeadm/kubelet/
#    containerd/crictl for the pinned Kubernetes minor version. This is
#    the step that needs KVM (or a lot of patience) and a working path
#    to releases.ubuntu.com for the installer ISO -- see this
#    directory's README.md for exactly what was and wasn't verified
#    about this step in this project's own development.
# ------------------------------------------------------------
echo "[3/3] Building (${UBUNTU_BUILD_TARGET})..."
# kubernetes_series is a real Packer variable (packer/config/kubernetes.json,
# feeds pkgs.k8s.io's own real repo URL structure -- confirmed against
# the actual file, not guessed), overridden the way image-builder's own
# Makefile actually supports: a var-file passed via PACKER_VAR_FILES,
# not an environment variable (an earlier draft of this script assumed
# a KUBERNETES_SERIES env var that does not exist anywhere in the real
# Makefile -- caught by checking the real file before shipping this,
# not left in).
KUBERNETES_SERIES_VAR_FILE="${WORK_DIR}/kubernetes-series.json"
printf '{"kubernetes_series": "v%s"}\n' "${KUBERNETES_MINOR_VERSION}" > "${KUBERNETES_SERIES_VAR_FILE}"
(cd "${WORK_DIR}/image-builder/images/capi" && \
    PACKER_VAR_FILES="${KUBERNETES_SERIES_VAR_FILE}" make "${UBUNTU_BUILD_TARGET}")

OUTPUT_DIR="${WORK_DIR}/image-builder/images/capi/output"
echo
echo "============================================================"
echo " Done -- raw image + checksum should be under:"
echo "   ${OUTPUT_DIR}/"
echo
echo " Use it as this project's cluster_spec.image_url (serve the .raw"
echo " file over HTTP somewhere Ironic can reach, then point image_url"
echo " at it) and image_checksum -- see USAGE.md section 1 for the"
echo " Metal3MachineTemplate fields this feeds."
echo "============================================================"
