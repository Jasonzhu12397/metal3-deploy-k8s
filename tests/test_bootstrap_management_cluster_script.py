"""
Guards the shell syntax of deploy/bootstrap-management-cluster/setup.sh --
same category of check as tests/test_capd_quickstart_scripts.py,
tests/test_https_setup_scripts.py, and tests/test_live_apply_script.py.

This script downloads real binaries (k3s, clusterctl), starts a real
background Kubernetes process, and applies real upstream release
manifests -- not something to run as a side effect of a routine pytest
invocation. It WAS run for real during development; see this directory's
own README.md for exactly what that run did and didn't manage to verify
(a GitHub API rate limit and this sandbox's own disk pressure blocked
full end-to-end completion -- both stated plainly there, not glossed
over).
"""
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = PROJECT_ROOT / "deploy" / "bootstrap-management-cluster" / "setup.sh"


def test_bootstrap_management_cluster_has_valid_shell_syntax():
    assert SCRIPT_PATH.exists(), "setup.sh is missing"
    result = subprocess.run(["bash", "-n", str(SCRIPT_PATH)], capture_output=True, text=True)
    assert result.returncode == 0, f"setup.sh has a shell syntax error:\n{result.stderr}"


def test_bootstrap_management_cluster_readme_exists():
    readme = SCRIPT_PATH.parent / "README.md"
    assert readme.exists(), "bootstrap-management-cluster is missing its README.md"
    text = readme.read_text()
    # the two things this module must never silently gloss over: what it
    # can't decide for the user (network config), and what wasn't
    # actually verified end to end during development.
    assert "networking" in text.lower()
    assert "没有验证过" in text or "not verified" in text.lower()
