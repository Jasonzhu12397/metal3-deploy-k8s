#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# mirror-images.sh -- copies every image in image-list.txt from the
# public internet into a local registry, using skopeo (a real,
# standard tool for registry-to-registry copying that needs no local
# Docker daemon and no actual container execution -- just an HTTPS
# client talking the real OCI registry API on both ends).
#
# Run this on a machine that DOES have internet access (a "jump box" /
# bastion, in air-gapped-deployment terminology) but can also reach the
# local registry you're populating for the actual (disconnected)
# customer environment -- these are very likely two different networks,
# which is the entire point of an air-gapped deployment.
#
# What this project's own development sandbox could verify: skopeo
# itself is real, installs cleanly (`apt-get install skopeo`), and
# produces a real, correctly-formed error distinguishing "network
# policy blocked this" from an actual tool malfunction -- confirmed
# directly: `skopeo inspect docker://registry.k8s.io/kube-apiserver:v1.31.0`
# fails with "pinging container registry registry.k8s.io: StatusCode:
# 403, Host not in allowlist: registry.k8s.io" -- this sandbox's own
# network policy blocks registry.k8s.io/quay.io/ghcr.io/docker.io
# outright (same finding as everywhere else in this project that
# touches a container registry), so actually copying any real image
# was never possible to verify here. Real network access, which this
# sandbox categorically does not have, is the only thing standing
# between this script and actually working -- not its own logic.
# ============================================================

LOCAL_REGISTRY="${LOCAL_REGISTRY:?Set LOCAL_REGISTRY to your local mirror, e.g. registry.airgap.local:5000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_LIST="${SCRIPT_DIR}/image-list.txt"

if ! command -v skopeo >/dev/null 2>&1; then
    echo "ERROR: skopeo is required. On Debian/Ubuntu: apt-get install skopeo" >&2
    exit 1
fi

echo "============================================================"
echo " mirror-images.sh -> ${LOCAL_REGISTRY}"
echo "============================================================"
echo

FAILED=()
while IFS= read -r image || [[ -n "$image" ]]; do
    # skip blank lines and comments
    [[ -z "$image" || "$image" == \#* ]] && continue

    # image-list.txt entries are "registry/path:tag" -- the local copy
    # keeps the same path+tag under the local registry host, so
    # RegistryMirrorConfig's per-registry endpoint redirect (see
    # registry-mirror-patch.yaml) transparently resolves the same
    # reference a node already asks for, without needing every
    # manifest/machine-config in this project rewritten to reference
    # the local registry explicitly.
    dest="${LOCAL_REGISTRY}/${image#*/}"

    echo "  ${image}"
    echo "    -> ${dest}"
    if skopeo copy --all "docker://${image}" "docker://${dest}"; then
        echo "    [OK]"
    else
        echo "    [FAILED]"
        FAILED+=("${image}")
    fi
    echo
done < "${IMAGE_LIST}"

echo "============================================================"
if [[ ${#FAILED[@]} -eq 0 ]]; then
    echo " Done -- every image in ${IMAGE_LIST} mirrored to ${LOCAL_REGISTRY}"
else
    echo " Done with failures -- ${#FAILED[@]} image(s) did not copy:"
    printf '   %s\n' "${FAILED[@]}"
    exit 1
fi
echo "============================================================"
