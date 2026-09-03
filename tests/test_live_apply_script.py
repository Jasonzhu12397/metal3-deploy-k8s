"""
Guards the shell syntax of deploy/testing/live-apply-test.sh -- same
category of check as tests/test_capd_quickstart_scripts.py and
tests/test_https_setup_scripts.py.

This is deliberately just a syntax check, not a run of the script
itself: live-apply-test.sh downloads a real k3s binary and starts a
real Kubernetes control plane, which isn't something to do as a side
effect of a routine pytest run (slow, needs network access to GitHub,
leaves a background process). That script was run for real, manually,
multiple times during development -- see its own header comment and
README's "Manifest schema validation" section for what that actually
proved (including a real bug it caught that offline schema validation
alone had missed: vsphere.yaml.j2's unquoted `default('')` on
networkName rendering as YAML null, which a real API server rejects but
which every existing test's fixture data happened to never exercise).
"""
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = PROJECT_ROOT / "deploy" / "testing" / "live-apply-test.sh"


def test_live_apply_test_has_valid_shell_syntax():
    assert SCRIPT_PATH.exists(), "live-apply-test.sh is missing"
    result = subprocess.run(["bash", "-n", str(SCRIPT_PATH)], capture_output=True, text=True)
    assert result.returncode == 0, f"live-apply-test.sh has a shell syntax error:\n{result.stderr}"


def test_live_apply_test_references_crd_fixtures_that_actually_exist():
    """The script hardcodes paths into backend/tests_data/crd_schemas/ --
    confirm every file it references is actually there, so a future
    rename of one of those fixtures doesn't silently break this script
    without anything catching it."""
    script_text = SCRIPT_PATH.read_text()
    crd_dir = PROJECT_ROOT / "backend" / "tests_data" / "crd_schemas"

    for crd_file in crd_dir.glob("*.yaml"):
        # every schema file this project ships should be referenced by
        # *something* in the script (either applied directly, or a
        # deliberate comment explaining why not, e.g. KubeVirt's
        # v1alpha1-only CRDs aren't snapshotted at all so wouldn't
        # appear here in the first place)
        if crd_file.name not in script_text:
            raise AssertionError(
                f"backend/tests_data/crd_schemas/{crd_file.name} exists but "
                f"live-apply-test.sh never references it -- either it should "
                f"be installed too, or this test's assumption needs updating."
            )
