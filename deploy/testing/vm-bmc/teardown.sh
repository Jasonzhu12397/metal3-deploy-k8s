#!/usr/bin/env bash
# Destroys and undefines every VM created by create_test_nodes.py (matched
# by name prefix) and removes their disk images from the given pool.
# Does NOT touch anything you didn't create with that script.
set -euo pipefail

PREFIX="${1:-metal3-test-node}"
POOL="${2:-default}"

echo "Tearing down all libvirt domains matching '${PREFIX}*'..."
for name in $(virsh list --all --name | grep "^${PREFIX}" || true); do
  echo "  destroying + undefining ${name}"
  virsh destroy "$name" 2>/dev/null || true   # ignore if already off
  virsh undefine "$name" --remove-all-storage
done

echo "Done. Remaining domains matching prefix (should be empty):"
virsh list --all --name | grep "^${PREFIX}" || echo "  (none)"
