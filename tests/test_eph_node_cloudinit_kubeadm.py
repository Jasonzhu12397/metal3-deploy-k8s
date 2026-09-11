"""
Guards deploy/ephemeral-node-cloudinit-kubeadm/ -- same category of check
as every other real-infrastructure script in this project
(test_bootstrap_management_cluster_script.py, test_eph_node_talos_script.py).

This module's own build script actually ran during development, as far
as this sandbox's network allowed: debootstrap genuinely connected to
archive.ubuntu.com (after a real, verified User-Agent fix this
sandbox's egress proxy required) and began downloading real packages,
but individual .deb file transfers stalled well before completion --
see this directory's own README.md for the full, honest breakdown of
what that means and what's still unverified as a result (everything
downstream of debootstrap: chroot package installation, squashfs
packaging, and -- most significantly -- wiring an actual live-boot
initramfs, which was never reached).
"""
from pathlib import Path
import subprocess
import yaml

MODULE_DIR = Path(__file__).parent.parent / "deploy" / "ephemeral-node-cloudinit-kubeadm"


def test_build_script_has_valid_shell_syntax():
    script = MODULE_DIR / "build-eph-node-image.sh"
    assert script.exists(), "build-eph-node-image.sh is missing"
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, f"shell syntax error:\n{result.stderr}"


def test_readme_states_its_own_verification_boundary():
    readme = MODULE_DIR / "README.md"
    assert readme.exists(), "ephemeral-node-cloudinit-kubeadm is missing its README.md"
    text = readme.read_text()
    assert "没有验证过的" in text or "not verified" in text.lower()
    # the two most important things this module must never gloss over:
    # the User-Agent-based proxy quirk this sandbox needed (a real,
    # reusable finding), and that live-boot wiring was never reached.
    assert "user-agent" in text.lower() or "User-Agent" in text
    assert "live-boot" in text.lower() or "casper" in text.lower()


def test_cloud_init_user_data_is_valid_yaml_and_has_the_kubeadm_init_step():
    user_data = MODULE_DIR / "cloud-init" / "user-data.yaml"
    assert user_data.exists()
    text = user_data.read_text()
    assert text.startswith("#cloud-config"), "cloud-init user-data must start with the #cloud-config header"
    # strip the #cloud-config line itself before parsing -- it's a
    # cloud-init-specific marker, not valid standalone YAML syntax on
    # its own line in every parser's eyes, but the rest of the document
    # must be real, valid YAML.
    body = "\n".join(text.splitlines()[1:])
    parsed = yaml.safe_load(body)
    assert "write_files" in parsed
    assert "runcmd" in parsed
    script_content = next(
        f["content"] for f in parsed["write_files"] if f["path"] == "/etc/eph-node-kubeadm-init.sh"
    )
    assert "kubeadm init" in script_content


def test_cloud_init_network_config_is_valid_yaml_with_placeholders_not_guessed_values():
    """The actual point of this file: it must NOT contain a guessed real
    interface name or IP -- a wrong guess here is a real network
    incident, not just a wrong config value."""
    network_config = MODULE_DIR / "cloud-init" / "network-config.yaml"
    assert network_config.exists()
    text = network_config.read_text()
    parsed = yaml.safe_load(text)
    assert parsed["network"]["version"] == 2
    ethernets = parsed["network"]["ethernets"]
    assert len(ethernets) == 1
    iface_name = next(iter(ethernets))
    assert iface_name.startswith("__REPLACE"), "interface name must be a clearly-marked placeholder, not a guess"
    assert any("__REPLACE" in addr for addr in ethernets[iface_name]["addresses"])


def test_meta_data_is_valid_yaml():
    meta_data = MODULE_DIR / "cloud-init" / "meta-data.yaml"
    assert meta_data.exists()
    parsed = yaml.safe_load(meta_data.read_text())
    assert "instance-id" in parsed
