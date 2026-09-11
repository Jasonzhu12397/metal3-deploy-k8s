#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# build-golden-image.sh -- builds a real, disk-installable Ubuntu image
# with containerd + kubeadm/kubelet/kubectl pre-baked in, for the
# TARGET cluster's control-plane/worker nodes (Ironic writes this to
# disk via a Metal3MachineTemplate's image.url, same mechanism as any
# other OS image this project already references there).
#
# Different problem from deploy/ephemeral-node-*/, and a genuinely
# optional one -- state this plainly rather than implying every
# deployment needs it: the STANDARD, default way this project's own
# kubeadm-based templates already work needs no custom image at all --
# CABPK generates cloud-init data, Ironic delivers it via a real
# official cloud vendor image's own cloud-init (e.g. Ubuntu's own
# published server cloud image), and kubeadm/kubelet/containerd get
# installed AT BOOT TIME from the real internet. That's less to build
# and maintain, and is how this ecosystem is designed to work by
# default.
#
# This script exists for the case where that default doesn't fit: a
# restricted-network production environment where target nodes can't
# reach pkgs.k8s.io / apt mirrors / container registries at boot time
# (the same category of restriction, for real, this project's own
# development sandbox hit repeatedly -- see deploy/bootstrap-management-cluster/
# and deploy/ephemeral-node-*/'s own READMEs). Baking the packages in
# ahead of time avoids needing that access at provisioning time.
#
# NOT a live/in-memory image like deploy/ephemeral-node-cloudinit-kubeadm/'s
# -- this one gets an actual bootloader (GRUB) and boots from a real
# installed disk, since target cluster nodes are meant to persist,
# unlike the ephemeral bootstrap node.
# ============================================================

UBUNTU_SUITE="${UBUNTU_SUITE:-noble}"
KUBERNETES_MINOR_VERSION="${KUBERNETES_MINOR_VERSION:-v1.31}"
IMAGE_SIZE_MB="${IMAGE_SIZE_MB:-4096}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${SCRIPT_DIR}/.image-work"
ROOTFS="${WORK_DIR}/rootfs"
IMAGE_PATH="${WORK_DIR}/golden-image.raw"

echo "============================================================"
echo " build-golden-image.sh -- Ubuntu ${UBUNTU_SUITE}, k8s ${KUBERNETES_MINOR_VERSION}"
echo "============================================================"
echo

for cmd in debootstrap parted losetup mkfs.ext4 grub-install; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        echo "ERROR: ${cmd} is required. On Debian/Ubuntu:" >&2
        echo "  apt-get install debootstrap parted util-linux e2fsprogs grub-pc-bin grub-efi-amd64-bin" >&2
        exit 1
    fi
done

mkdir -p "${WORK_DIR}"

if ! grep -q "APT-HTTP" /etc/wgetrc 2>/dev/null; then
    echo 'user_agent = Debian APT-HTTP/1.3 (2.4.13)' >> /etc/wgetrc
fi

# ------------------------------------------------------------
# 1. Base rootfs
# ------------------------------------------------------------
echo "[1/6] Base rootfs (debootstrap)..."
if [[ ! -f "${ROOTFS}/etc/os-release" ]]; then
    rm -rf "${ROOTFS}"
    mkdir -p "${ROOTFS}"
    debootstrap --arch=amd64 --variant=minbase "${UBUNTU_SUITE}" "${ROOTFS}" http://archive.ubuntu.com/ubuntu
else
    echo "[OK] rootfs already exists at ${ROOTFS}"
fi
echo

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
# 2. Packages -- cloud-init (still needed: real network config /
#    hostname / SSH keys per-node still come from CABPK's cloud-init
#    data at provisioning time, exactly like the default path -- only
#    the PACKAGES are pre-baked here, not the whole provisioning
#    mechanism replaced), containerd, kubeadm/kubelet/kubectl, GRUB +
#    a real Linux kernel (debootstrap's minbase does not include one).
# ------------------------------------------------------------
echo "[2/6] Installing packages into the chroot..."
mount_chroot

chroot "${ROOTFS}" /bin/bash -exuo pipefail <<CHROOT_SCRIPT
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg cloud-init systemd-sysv \
    linux-image-generic grub-pc openssh-server

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

# kubeadm/kubelet/kubectl -- see this script's own header comment and
# README.md for why this exact step is written-but-unverified in this
# project's own development sandbox (pkgs.k8s.io is blocked there
# outright -- a different, harder failure than archive.ubuntu.com's own
# slow-transfer issue this script's User-Agent fix addresses).
mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL "https://pkgs.k8s.io/core:/stable:/${KUBERNETES_MINOR_VERSION}/deb/Release.key" \
    | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/${KUBERNETES_MINOR_VERSION}/deb/ /" \
    > /etc/apt/sources.list.d/kubernetes.list
apt-get update
apt-get install -y --no-install-recommends kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl

# kubeadm join/init itself is still driven by CABPK's own cloud-init
# data at provisioning time (the standard mechanism, unchanged) -- this
# image only pre-installs the BINARIES so that step doesn't also need
# network access to pkgs.k8s.io at boot. Nothing here runs kubeadm
# itself; that stays cloud-init's job, same as the default (no custom
# image) path.

# A minimal fstab -- the real root partition's UUID gets fixed up by
# this script's own disk-writing step below, after the filesystem
# (and therefore its real UUID) actually exists.
cat > /etc/fstab <<'EOF'
# root filesystem UUID is patched in by build-golden-image.sh after
# mkfs -- see that script's own step 5.
UUID=PLACEHOLDER_ROOT_UUID / ext4 defaults 0 1
EOF
CHROOT_SCRIPT

umount_chroot
trap - EXIT
echo

# ------------------------------------------------------------
# 3. cloud-init: NoCloud/ConfigDrive datasource only -- this is what
#    Ironic + CABPK actually deliver on real Metal3 provisioning
#    (config-drive), not the NoCloud-over-HTTP setup
#    deploy/ephemeral-node-cloudinit-kubeadm/ needs for its own,
#    different PXE-boot scenario. Nothing project-specific to write
#    here beyond making sure the datasource list includes it -- CABPK's
#    own generated cloud-init content (real kubeadm join/init commands,
#    real per-node network config) is what actually drives the node,
#    unchanged from the default (no custom image) path.
# ------------------------------------------------------------
echo "[3/6] cloud-init datasource config..."
mkdir -p "${ROOTFS}/etc/cloud/cloud.cfg.d"
cat > "${ROOTFS}/etc/cloud/cloud.cfg.d/99-datasource.cfg" <<'EOF'
datasource_list: [ConfigDrive, NoCloud]
EOF
echo

# ------------------------------------------------------------
# 4. Build a real disk image: partition, format, install GRUB. This is
#    what makes it different from the ephemeral node's squashfs -- an
#    actual bootable disk Ironic can write byte-for-byte.
# ------------------------------------------------------------
echo "[4/6] Building the disk image (${IMAGE_SIZE_MB}MB)..."
rm -f "${IMAGE_PATH}"
truncate -s "${IMAGE_SIZE_MB}M" "${IMAGE_PATH}"
parted -s "${IMAGE_PATH}" mklabel gpt
parted -s "${IMAGE_PATH}" mkpart primary ext4 1MiB 100%
parted -s "${IMAGE_PATH}" set 1 boot on

LOOP_DEV=$(losetup --show -f -P "${IMAGE_PATH}")
trap 'losetup -d "${LOOP_DEV}" 2>/dev/null || true; umount_chroot' EXIT

mkfs.ext4 -F -L rootfs "${LOOP_DEV}p1"
ROOT_UUID=$(blkid -s UUID -o value "${LOOP_DEV}p1")

MOUNT_DIR="${WORK_DIR}/mnt"
mkdir -p "${MOUNT_DIR}"
mount "${LOOP_DEV}p1" "${MOUNT_DIR}"
echo "[5/6] Copying rootfs onto the disk image and installing GRUB..."
cp -a "${ROOTFS}/." "${MOUNT_DIR}/"
sed -i "s/PLACEHOLDER_ROOT_UUID/${ROOT_UUID}/" "${MOUNT_DIR}/etc/fstab"

mount --bind /dev "${MOUNT_DIR}/dev"
mount --bind /proc "${MOUNT_DIR}/proc"
mount --bind /sys "${MOUNT_DIR}/sys"
chroot "${MOUNT_DIR}" grub-install --target=i386-pc "${LOOP_DEV}"
chroot "${MOUNT_DIR}" update-grub
umount "${MOUNT_DIR}/dev" "${MOUNT_DIR}/proc" "${MOUNT_DIR}/sys"
umount "${MOUNT_DIR}"
losetup -d "${LOOP_DEV}"
trap - EXIT

echo
echo "[6/6] Done."
echo "============================================================"
echo " Image: ${IMAGE_PATH}"
echo " Compress it (e.g. xz -T0 ${IMAGE_PATH}) and host it somewhere"
echo " Ironic can reach, then set your cluster's spec.image_url /"
echo " spec.image_checksum to point at it -- see USAGE.md's own"
echo " cluster-creation examples for exactly where those fields go."
echo "============================================================"
