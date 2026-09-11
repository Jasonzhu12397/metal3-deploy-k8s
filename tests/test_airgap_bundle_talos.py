"""
Guards deploy/airgap-bundle-talos/ -- same category of check as every
other real-infrastructure script in this project, plus a specific
regression guard for a real bug this module's own development caught:
templates/capi/providers/talos-metal3.yaml.j2's default image_url (and
USAGE.md's documented example, and download-assets.sh here) all
referenced metal-amd64.raw.xz -- which 404s. Talos's real, current
release asset for this file is metal-amd64.raw.zst (zstd compression,
not xz) -- confirmed by listing the actual v1.12.12 release assets, not
assumed. Fixed everywhere it appeared; this test keeps it fixed.
"""
from pathlib import Path
import subprocess

MODULE_DIR = Path(__file__).parent.parent / "deploy" / "airgap-bundle-talos"
PROJECT_ROOT = Path(__file__).parent.parent


def test_mirror_images_script_has_valid_shell_syntax():
    script = MODULE_DIR / "mirror-images.sh"
    assert script.exists()
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, f"shell syntax error:\n{result.stderr}"


def test_download_assets_script_has_valid_shell_syntax():
    script = MODULE_DIR / "download-assets.sh"
    assert script.exists()
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, f"shell syntax error:\n{result.stderr}"


def test_image_list_has_no_blank_registry_or_obviously_malformed_entries():
    lines = (MODULE_DIR / "image-list.txt").read_text().splitlines()
    images = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    assert len(images) >= 10, "expected at least the CAPI/CAPM3/CABPT/CACPPT/cert-manager/BMO/IrSO/Talos images"
    for image in images:
        assert "/" in image, f"'{image}' doesn't look like registry/path:tag"
        assert ":" in image, f"'{image}' has no tag -- must be pinned, not floating latest"


def test_registry_mirror_patch_uses_the_real_talos_field_names():
    """machine.registries.mirrors / machine.registries.config /
    machine.install.image are real, current Talos machine-config field
    names (confirmed against official Sidero documentation) -- this
    isn't invented syntax."""
    text = (MODULE_DIR / "registry-mirror-patch.yaml").read_text()
    assert "registries:" in text
    assert "mirrors:" in text
    assert "config:" in text
    assert "install:" in text
    assert "insecureSkipVerify" in text
    # every major registry this project's Talos path actually pulls from
    for registry in ("docker.io", "ghcr.io", "registry.k8s.io", "quay.io"):
        assert registry in text, f"{registry} missing from the mirror config"


def test_no_remaining_reference_to_the_wrong_raw_xz_filename_anywhere_in_the_project():
    """Regression guard for the actual bug this module's own
    development caught: metal-amd64.raw.xz 404s (real Talos releases
    ship .raw.zst, not .raw.xz) -- this was wrong in the Talos template,
    USAGE.md's own documented example, and this module's own first
    draft, until checked against the real release asset list. If this
    ever reappears anywhere in the project, someone reverted the fix or
    copy-pasted from a stale reference."""
    offenders = []
    exempt = {Path(__file__), MODULE_DIR / "README.md"}
    for path in PROJECT_ROOT.rglob("*"):
        if path.is_dir() or ".git" in path.parts or "node_modules" in path.parts:
            continue
        if path.resolve() in {p.resolve() for p in exempt}:
            continue  # these two intentionally document the old, wrong filename as part of explaining the fix
        if path.suffix not in (".py", ".j2", ".md", ".sh", ".yaml", ".yml"):
            continue
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        if "metal-amd64.raw.xz" in text:
            offenders.append(str(path))
    assert not offenders, f"found the wrong (404ing) filename in: {offenders}"


def test_readme_states_what_actually_ran_successfully_versus_what_did_not():
    readme = MODULE_DIR / "README.md"
    assert readme.exists()
    text = readme.read_text()
    assert "没有验证过的" in text or "not verified" in text.lower()
    # the specific, real bug this module's development caught must be
    # documented, not glossed over as if the URLs were always correct
    assert "raw.zst" in text
    assert "raw.xz" in text
    assert "skopeo" in text.lower()
