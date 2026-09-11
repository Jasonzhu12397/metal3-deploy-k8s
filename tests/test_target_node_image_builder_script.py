"""
Guards deploy/target-node-image-builder/ -- same category of check as
every other real-infrastructure script in this project.

This module wraps kubernetes-sigs/image-builder (the real, official
Cluster-API-recommended tool for building kubeadm-ready OS disk images)
rather than reimplementing image building. Its own build was never run
to completion in this project's development sandbox: image-builder's
raw target boots a full Ubuntu Server installer inside QEMU, which
needs either KVM (confirmed unavailable in this sandbox elsewhere in
this project) or an impractically slow software-emulated boot, plus a
~2.5GB installer ISO download that risks the same large-file throttling
already documented for deploy/ephemeral-node-cloudinit-kubeadm/. See
this directory's own README.md for the full breakdown, including a real
mistake caught before being shipped: an earlier draft used a
KUBERNETES_SERIES environment variable that does not exist anywhere in
image-builder's real Makefile -- fixed to use the actual supported
mechanism (PACKER_VAR_FILES pointing at a var-file setting the real
Packer variable, kubernetes_series).
"""
from pathlib import Path
import subprocess

MODULE_DIR = Path(__file__).parent.parent / "deploy" / "target-node-image-builder"


def test_build_script_has_valid_shell_syntax():
    script = MODULE_DIR / "build-target-node-image.sh"
    assert script.exists(), "build-target-node-image.sh is missing"
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, f"shell syntax error:\n{result.stderr}"


def test_build_script_does_not_reference_the_fake_env_var_this_project_caught_and_fixed():
    """Regression guard for the actual mistake this module's own README
    documents catching: KUBERNETES_SERIES is not a real image-builder
    variable (grepped the real Makefile to confirm) -- if this
    reappears, someone reverted the fix or copy-pasted from the
    original wrong draft."""
    script_text = (MODULE_DIR / "build-target-node-image.sh").read_text()
    assert "KUBERNETES_SERIES=" not in script_text.replace("KUBERNETES_SERIES_VAR_FILE", "")
    assert "PACKER_VAR_FILES" in script_text
    assert "kubernetes_series" in script_text


def test_readme_states_its_own_verification_boundary():
    readme = MODULE_DIR / "README.md"
    assert readme.exists(), "target-node-image-builder is missing its README.md"
    text = readme.read_text()
    assert "没有验证过的" in text or "not verified" in text.lower()
    # the two things this module must never gloss over: that a real
    # build was never actually completed here, and the real mistake
    # this project caught in its own first draft rather than shipping
    # it silently.
    assert "kvm" in text.lower()
    assert "KUBERNETES_SERIES" in text
