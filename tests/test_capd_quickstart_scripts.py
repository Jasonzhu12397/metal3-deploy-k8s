"""
Guards the shell syntax of deploy/testing/capd-quickstart/'s scripts --
the same category of check as tests/test_https_setup_scripts.py does for
the HTTPS setup scripts. This is the cheap, always-runnable half of
verifying these scripts; see that directory's README for what could and
couldn't be verified beyond syntax (this sandbox has no Docker, so the
actual kind-cluster-creation and CAPD-provisioning steps couldn't be
run end to end).
"""
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CAPD_QUICKSTART_DIR = PROJECT_ROOT / "deploy" / "testing" / "capd-quickstart"


def test_capd_quickstart_scripts_have_valid_shell_syntax():
    for name in ("setup.sh", "teardown.sh"):
        path = CAPD_QUICKSTART_DIR / name
        assert path.exists(), f"{name} is missing"
        result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, f"{name} has a shell syntax error:\n{result.stderr}"


def test_setup_script_fails_clearly_when_docker_missing():
    """The one behavior actually exercisable without Docker/kind/clusterctl
    installed: the prerequisite check itself. Confirms it exits non-zero
    with a clear message rather than proceeding and failing confusingly
    deep into the script."""
    env = dict(os.environ)
    # Strip PATH down to something with no docker/kind/clusterctl/jq on
    # it, regardless of what's actually installed in whatever environment
    # runs this test -- the point is testing the "missing" branch runs.
    env["PATH"] = "/usr/bin:/bin"
    result = subprocess.run(
        ["bash", str(CAPD_QUICKSTART_DIR / "setup.sh")],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert result.returncode != 0
    assert "is required but not installed" in result.stderr
