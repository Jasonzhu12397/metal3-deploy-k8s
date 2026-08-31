"""
Covers deploy/testing/fake-bmc/generate_fake_nodes.py's output shape --
this doesn't need libvirt/KVM (verified live against a real sushy-emulator
--fake process in the environment this was developed in, see that
directory's README) so this can run as a normal pytest.

Also guards against deploy/testing/vm-bmc/register_with_backend.py and
deploy/testing/fake-bmc/register_with_backend.py silently drifting apart
-- they're deliberately the same script (same registration logic works
regardless of whether libvirt or sushy's --fake driver produced the
node list), kept as two copies for each directory's self-containment
rather than a shared import, which means nothing stops someone editing
one and forgetting the other without an explicit check for it.
"""
import importlib.util
import json
import os
import sys
import tempfile

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
FAKE_BMC_DIR = os.path.join(PROJECT_ROOT, "deploy", "testing", "fake-bmc")
VM_BMC_DIR = os.path.join(PROJECT_ROOT, "deploy", "testing", "vm-bmc")


def _load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_generate_fake_nodes_output_shape():
    generator = _load_module(os.path.join(FAKE_BMC_DIR, "generate_fake_nodes.py"), "generate_fake_nodes")

    with tempfile.TemporaryDirectory() as tmp:
        conf_path = os.path.join(tmp, "sushy-fake.conf")
        nodes_path = os.path.join(tmp, "test_nodes.json")

        sys.argv = [
            "generate_fake_nodes.py",
            "--count", "3",
            "--conf-out", conf_path,
            "--nodes-out", nodes_path,
        ]
        generator.main()

        nodes = json.loads(open(nodes_path).read())
        assert len(nodes) == 3
        uuids = {n["redfish_uuid"] for n in nodes}
        macs = {n["boot_mac_address"] for n in nodes}
        names = {n["name"] for n in nodes}
        assert len(uuids) == 3, "each node must get a distinct UUID"
        assert len(macs) == 3, "each node must get a distinct MAC"
        assert len(names) == 3

        # sushy-emulator's config file is Python source (Flask
        # Config.from_pyfile) -- confirm it's at least syntactically
        # valid Python and defines what generate_fake_nodes.py promises.
        conf_source = open(conf_path).read()
        conf_globals: dict = {}
        exec(compile(conf_source, conf_path, "exec"), conf_globals)
        assert conf_globals["SUSHY_EMULATOR_LISTEN_PORT"] == 8000
        assert len(conf_globals["SUSHY_EMULATOR_FAKE_SYSTEMS"]) == 3
        conf_uuids = {s["uuid"] for s in conf_globals["SUSHY_EMULATOR_FAKE_SYSTEMS"]}
        assert conf_uuids == uuids, "conf file and nodes.json must reference the same UUIDs"


def test_register_with_backend_scripts_stay_in_sync():
    """The two copies exist for each testing directory's
    self-containment, not because they're meant to differ -- if this
    fails, someone edited one without the other."""
    fake_bmc_copy = open(os.path.join(FAKE_BMC_DIR, "register_with_backend.py")).read()
    vm_bmc_copy = open(os.path.join(VM_BMC_DIR, "register_with_backend.py")).read()

    def normalize(text: str) -> str:
        # Strip each file's own docstring (deliberately worded
        # differently -- one mentions libvirt, the other mentions
        # sushy's --fake driver) before comparing; everything else
        # (the actual login/register_node/main logic) must be identical.
        marker = '"""\nfrom __future__ import annotations'
        idx = text.find(marker)
        assert idx != -1, "expected docstring to end right before 'from __future__ import annotations'"
        return text[idx:]

    assert normalize(fake_bmc_copy) == normalize(vm_bmc_copy), (
        "deploy/testing/fake-bmc/register_with_backend.py and "
        "deploy/testing/vm-bmc/register_with_backend.py have drifted apart -- "
        "keep their logic (everything after the docstring) identical, or "
        "explicitly decide they should differ and update this test."
    )
