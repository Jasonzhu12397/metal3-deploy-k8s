"""
Guards deploy/golden-image-target-node/ -- same category of check as
every other real-infrastructure script in this project. debootstrap
stalled during a second, independent attempt to build a real image with
this script's exact approach (confirmed reproducible, not a one-off --
see this directory's own README.md), so this script itself was never
run to completion; these tests cover what can actually be checked
without a working build.
"""
from pathlib import Path
import subprocess

MODULE_DIR = Path(__file__).parent.parent / "deploy" / "golden-image-target-node"


def test_build_script_has_valid_shell_syntax():
    script = MODULE_DIR / "build-golden-image.sh"
    assert script.exists(), "build-golden-image.sh is missing"
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, f"shell syntax error:\n{result.stderr}"


def test_readme_states_this_is_optional_not_a_hard_requirement():
    """The most important thing this README must never lose in a future
    edit: this whole module is optional (restricted-network production
    environments only) -- the project's default path needs no custom
    image at all. Losing this framing would make every standard
    deployment look like it's missing a required build step."""
    readme = MODULE_DIR / "README.md"
    assert readme.exists()
    text = readme.read_text()
    assert "不是必须的" in text or "not required" in text.lower() or "optional" in text.lower()


def test_readme_states_its_own_verification_boundary():
    readme = MODULE_DIR / "README.md"
    text = readme.read_text()
    assert "没有验证过的" in text or "not verified" in text.lower()
    assert "grub" in text.lower()  # the specific, furthest-downstream unverified step
