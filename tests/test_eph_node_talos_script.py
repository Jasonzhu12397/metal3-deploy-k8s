"""
Guards the shell syntax of
deploy/ephemeral-node-talos/generate-eph-node-configs.sh -- same category
of check as tests/test_bootstrap_management_cluster_script.py and every
other real-infrastructure script in this project.

This script downloads real binaries and PXE boot assets (talosctl,
Talos's own kernel + initramfs) and generates real cryptographic
material (talosctl gen config's PKI/tokens) -- not something to run as
a side effect of a routine pytest invocation. It WAS run for real during
development, successfully, through config generation; see this
directory's own README.md for exactly what that run did and didn't
manage to verify (a real PXE-bootable, network-connected machine is
needed for the rest, and no sandbox this project has been developed in
has ever had one).
"""
from pathlib import Path
import subprocess

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = PROJECT_ROOT / "deploy" / "ephemeral-node-talos" / "generate-eph-node-configs.sh"


def test_eph_node_talos_script_has_valid_shell_syntax():
    assert SCRIPT_PATH.exists(), "generate-eph-node-configs.sh is missing"
    result = subprocess.run(["bash", "-n", str(SCRIPT_PATH)], capture_output=True, text=True)
    assert result.returncode == 0, f"shell syntax error:\n{result.stderr}"


def test_eph_node_talos_readme_states_verification_boundary():
    readme = SCRIPT_PATH.parent / "README.md"
    assert readme.exists(), "ephemeral-node-talos is missing its README.md"
    text = readme.read_text()
    assert "没有验证过的" in text or "not verified" in text.lower()
    # the two specific things this module must never claim to have
    # solved without a real network-connected machine
    assert "maintenance mode" in text.lower()
    assert "k3s" in text.lower()  # must explain why this is NOT k3s, not just assert it
