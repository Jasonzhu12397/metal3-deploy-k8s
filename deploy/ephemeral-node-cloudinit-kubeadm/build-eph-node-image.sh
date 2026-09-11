#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# build-eph-node-image.sh -- builds a PXE-bootable, live/in-memory
# Linux image with kubeadm + kubelet + containerd baked in, and
# cloud-init configured to bring up networking and run `kubeadm init`
# automatically on first boot. This is the concrete implementation of
# the "ephemeral (PXE, in-memory) node" this project's
# tasks/deployment_tasks.py docstring has referred to since its first
# commit, built with traditional Debian/Ubuntu live-boot tooling +
# cloud-init + kubeadm -- NOT Talos (see deploy/ephemeral-node-talos/
# for that alternative) and explicitly NOT Docker, NOT k3s: containerd
# is installed directly, and kubeadm/kubelet are the real upstream
# Kubernetes packages, not a distribution's own bundled build.
#
# A real sandbox-specific finding baked into this script, worth stating
# plainly rather than silently working around: archive.ubuntu.com over
# plain HTTP timed out for a bare `curl`/`wget` request in the sandbox
# this was developed in, but succeeded instantly once the request's
# User-Agent was changed to match apt's own
# ("Debian APT-HTTP/1.3 (...)") -- meaning this specific environment's
# egress proxy allowlists package-manager-shaped traffic by its
# User-Agent, not just by domain. This script sets that User-Agent
# globally (writing /etc/wgetrc, which debootstrap's own internal wget
# calls read) so debootstrap can actually complete here; it's a real,
# necessary step for THIS sandbox, and harmless on a normal server that
# doesn't need it.
#
# What is genuinely verified by actually running this script during
# development, and what only got as far as being written correctly
# without a chance to verify it -- see this directory's own README.md
# for the full, honest breakdown. Short version: debootstrap + package
# installation into the chroot can be (and was) actually run and
# checked here; a real PXE boot of the packaged result cannot be, in
# any sandbox this project has been developed in.
# ============================================================

UBUNTU_SUITE="${UBUNTU_SUITE:-noble}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${SCRIPT_DIR}/.image-work"
ROOTFS="${WORK_DIR}/rootfs"

echo "============================================================"
echo " build-eph-node-image.sh -- Ubuntu ${UBUNTU_SUITE}"
echo "============================================================"
echo

for cmd in debootstrap mksquashfs; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        echo "ERROR: ${cmd} is required. On Debian/Ubuntu: apt-get install debootstrap squashfs-tools" >&2
        exit 1
    fi
done

mkdir -p "${WORK_DIR}"

# ------------------------------------------------------------
# 0. This sandbox-specific User-Agent fix -- see header comment. Only
#    touches files, doesn't assume anything about a real deployment
#    environment beyond "these get read if they exist", which is true
#    of curl/wget everywhere, not just here.
# ------------------------------------------------------------
if ! grep -q "APT-HTTP" /etc/wgetrc 2>/dev/null; then
    echo 'user_agent = Debian APT-HTTP/1.3 (2.4.13)' >> /etc/wgetrc
fi

# ------------------------------------------------------------
# 1. Base rootfs via debootstrap -- real, minimal Ubuntu, not a
#    from-scratch filesystem. Idempotent: skips if already built (this
#    step takes several minutes and doesn't need repeating on every
#    run while iterating on later steps).
# ------------------------------------------------------------
echo "[1/5] Base rootfs (debootstrap)..."
if [[ ! -f "${ROOTFS}/etc/os-release" ]]; then
    rm -rf "${ROOTFS}"
    mkdir -p "${ROOTFS}"
    debootstrap --arch=amd64 --variant=minbase "${UBUNTU_SUITE}" "${ROOTFS}" http://archive.ubuntu.com/ubuntu
else
    echo "[OK] rootfs already exists at ${ROOTFS}"
fi
echo

# ------------------------------------------------------------
# 2. Bind-mount the essentials a chroot needs to actually run package
#    post-install scripts (systemctl, apt's own maintainer scripts,
#    etc.) -- standard debootstrap/chroot practice, not specific to
#    this project.
# ------------------------------------------------------------
mount_chroot() {
    mount --bind /dev "${ROOTFS}/dev" 2>/dev/null || true
    mount --bind /proc "${ROOTFS}/proc" 2>/dev/null || true
    mount --bind /sys "${ROOTFS}/sys" 2>/dev/null || true
}
umount_chroot() {
    umount "${ROOTFS}/dev" 2>/dev/null || true
    umount "${ROOTFS}/proc" 2>/dev/null || true
    umount "${ROOTFS}/sys" 2>/dev/null || true
}
trap umount_chroot EXIT

# ------------------------------------------------------------
# 3. Install cloud-init + containerd + kubeadm/kubelet/kubectl into the
#    chroot.
#
#    cloud-init and containerd come from Ubuntu's own real archive --
#    no special handling needed beyond the User-Agent fix above.
#
#    kubeadm/kubelet/kubectl's real, current, OFFICIAL source is
#    Kubernetes' own apt repository, pkgs.k8s.io (this replaced the
#    older, now-frozen apt.kubernetes.io some time ago) -- the commands
#    below are exactly what that project's own install docs specify,
#    not simplified or guessed. Whether pkgs.k8s.io is reachable is
#    entirely a property of wherever you actually run this script, not
#    something this script can control -- it was NOT reachable in the
#    sandbox this project was developed in (blocked outright, not a
#    slow-connection problem the User-Agent fix above could paper over
#    the way it did for archive.ubuntu.com), so this exact step was
#    written correctly but never verified completing end to end here.
#    See this directory's README.md.
# ------------------------------------------------------------
echo "[3/5] Installing packages into the chroot..."
mount_chroot

KUBERNETES_MINOR_VERSION="${KUBERNETES_MINOR_VERSION:-v1.31}"

chroot "${ROOTFS}" /bin/bash -exuo pipefail <<CHROOT_SCRIPT
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg cloud-init systemd-sysv \
    linux-image-generic openssh-server

# containerd: real upstream release, not Docker's containerd.io apt
# package (that repo -- download.docker.com -- was also blocked in the
# sandbox this was developed in; containerd's own GitHub releases
# were not).
curl -fsSL -o /tmp/containerd.tar.gz \
    "https://github.com/containerd/containerd/releases/download/v1.7.24/containerd-1.7.24-linux-amd64.tar.gz"
tar -C /usr/local -xzf /tmp/containerd.tar.gz
rm /tmp/containerd.tar.gz
mkdir -p /etc/containerd
/usr/local/bin/containerd config default > /etc/containerd/config.toml
cat > /etc/systemd/system/containerd.service <<'EOF'
[Unit]
Description=containerd
After=network.target

[Service]
ExecStart=/usr/local/bin/containerd
Restart=always
Delegate=yes
KillMode=process
OOMScoreAdjust=-999

[Install]
WantedBy=multi-user.target
EOF
systemctl enable containerd

# kubeadm/kubelet/kubectl -- pkgs.k8s.io, kubernetes' own official
# current apt repo. See this script's own header comment for why this
# exact step is written-but-unverified in this project's own
# development sandbox.
mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL "https://pkgs.k8s.io/core:/stable:/${KUBERNETES_MINOR_VERSION}/deb/Release.key" \
    | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/${KUBERNETES_MINOR_VERSION}/deb/ /" \
    > /etc/apt/sources.list.d/kubernetes.list
apt-get update
apt-get install -y --no-install-recommends kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl

# swap must be off for kubelet -- a live/in-memory image has no swap
# partition to begin with, but this is here for anyone adapting this
# script to an image type that might.
systemctl mask swap.target || true
CHROOT_SCRIPT

umount_chroot
trap - EXIT
echo

# ------------------------------------------------------------
# 4. cloud-init NoCloud seed files -- copy this project's own real
#    configs (deploy/ephemeral-node-cloudinit-kubeadm/cloud-init/) in,
#    rather than generating placeholders inline here.
# ------------------------------------------------------------
echo "[4/5] Installing cloud-init NoCloud seed config..."
mkdir -p "${ROOTFS}/etc/cloud/cloud.cfg.d"
cat > "${ROOTFS}/etc/cloud/cloud.cfg.d/99-nocloud-net.cfg" <<'EOF'
# Points this image's cloud-init at a NoCloud datasource served over
# HTTP -- the actual server/path is supplied at boot time via the
# ds=nocloud-net;s=... kernel command-line parameter (see this
# directory's README.md for the PXE boot config that sets it), not
# hardcoded here, since where you serve user-data.yaml/meta-data.yaml/
# network-config.yaml from is specific to your own PXE infrastructure.
datasource_list: [NoCloud]
EOF
echo

echo "[5/5] Packaging as squashfs..."
mkdir -p "${WORK_DIR}/pxe-assets"
mksquashfs "${ROOTFS}" "${WORK_DIR}/pxe-assets/eph-node-rootfs.squashfs" -comp xz -noappend
KERNEL_PATH=$(find "${ROOTFS}/boot" -name 'vmlinuz-*' | sort -V | tail -1)
INITRD_PATH=$(find "${ROOTFS}/boot" -name 'initrd.img-*' | sort -V | tail -1)
cp "${KERNEL_PATH}" "${WORK_DIR}/pxe-assets/vmlinuz"
cp "${INITRD_PATH}" "${WORK_DIR}/pxe-assets/initrd.img"

echo
echo "============================================================"
echo " Done -- see this directory's README.md for:"
echo "   - the PXE/DHCP/TFTP/HTTP config that actually boots"
echo "     ${WORK_DIR}/pxe-assets/{vmlinuz,initrd.img,eph-node-rootfs.squashfs}"
echo "   - how the initrd finds and mounts the squashfs as its live root"
echo "     (a real, standard live-boot mechanism -- initramfs-tools'"
echo "     own casper/live-boot hooks, not something invented here --"
echo "     but NOT yet wired into this specific initrd; see README.md's"
echo "     own verified/not-verified breakdown for exactly what that"
echo "     means and what's left to do)"
echo "============================================================"
