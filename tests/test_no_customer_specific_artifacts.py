"""
Guards against customer-specific example data creeping back into this
codebase -- addresses, hostnames, and file-path conventions that were
originally lifted directly from a real customer's config (uploaded early
in this project's development) rather than written as generic examples.

This isn't about the technology (Metal3/Ironic/CAPI are open source and
fine to reference by name) -- it's specifically about the literal
IPs/hostnames/paths/filenames that trace back to one real deployment.
Run as a normal pytest so it fails loudly in CI if anyone pastes another
real example back in, rather than relying on someone remembering to grep
for it by hand.
"""
import os
import re

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")

# Each pattern is deliberately specific (not e.g. a bare IP octet) so this
# doesn't produce false positives on unrelated, legitimately generic
# examples elsewhere in the codebase.
FORBIDDEN_PATTERNS = [
    r"pk-dell8",
    r"pk-cnis",
    r"172\.18\.37\.\d+",
    r"b4:e9:b8:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}",
    r"10\.138\.\d+\.\d+",
    r"sdi\+netconf",
    r"mtn\.co\.za",
    r"ccdadm-config\.yaml",
    r"\bSEMC\b",
    r"10\.0\.10\.\d+",
    r"10\.0\.70\.\d+",
    r"10\.217\.\d+\.\d+",
    r"\bccdadm\b",  # the bare tool name itself, not just "ccdadm-config.yaml" --
    # this exact gap (checking only the filename, not the word) is why
    # ~7 occurrences of the bare word survived the original cleanup pass
    # entirely undetected across README.md/USAGE.md/several .py files'
    # comments until a later, unrelated pass happened to spot one by eye.
    r"\bSDI3\b",
    r"EricssonCCD",
]

# Directories that legitimately never need scanning (build output,
# dependencies, VCS internals) -- keeps this fast and avoids false
# positives from third-party code we don't control.
SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".pytest_cache"}

SCAN_EXTENSIONS = {".py", ".ts", ".tsx", ".md", ".j2", ".yaml", ".yml", ".conf"}


def _iter_source_files():
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for filename in files:
            if os.path.splitext(filename)[1] in SCAN_EXTENSIONS:
                yield os.path.join(root, filename)


def test_no_customer_specific_example_data():
    compiled = [(p, re.compile(p)) for p in FORBIDDEN_PATTERNS]
    violations: list[str] = []

    for path in _iter_source_files():
        # this test file itself necessarily contains the forbidden
        # strings (as regex patterns, to check for them) -- skip it.
        if os.path.abspath(path) == os.path.abspath(__file__):
            continue
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for pattern_str, pattern in compiled:
            if pattern.search(text):
                rel = os.path.relpath(path, PROJECT_ROOT)
                violations.append(f"{rel}: matches forbidden pattern `{pattern_str}`")

    assert not violations, (
        "Found customer-specific example data that should be generic "
        "placeholders instead:\n" + "\n".join(violations)
    )
