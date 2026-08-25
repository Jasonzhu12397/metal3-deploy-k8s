"""
Smoke tests for the cluster manifest rendering path (no live cluster
required -- this only exercises Jinja2 template rendering).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.yaml_generator import YamlGeneratorService  # noqa: E402


def test_render_bmh():
    gen = YamlGeneratorService()
    out = gen.render_bmh(
        [
            {
                "name": "pk-dell8-1-1-sd001-wp01",
                "node_pool_name": "pool1",
                "bmc_address": "sdi+netconf://172.18.37.1/tenant/1001",
                "secret_ref": "pk-dell8-1-1-sd001-wp01-bmc-secret",
                "boot_mac_address": "b4:e9:b8:08:37:c2",
                "online": False,
            }
        ]
    )
    docs = gen.parse_multi(out)
    assert docs[0]["kind"] == "BareMetalHost"
    assert docs[0]["spec"]["bmc"]["credentialsName"] == "pk-dell8-1-1-sd001-wp01-bmc-secret"


def test_render_cluster_config():
    gen = YamlGeneratorService()
    out = gen.render_cluster_config(
        {
            "name": "pk-cnis-pcg",
            "namespace": "metal3",
            "control_plane_count": 3,
            "control_plane_endpoint": "10.138.165.27",
            "worker_pools": [{"name": "pool1", "count": 4, "node_labels": ["role=osd"]}],
        }
    )
    docs = gen.parse_multi(out)
    kinds = {d["kind"] for d in docs}
    assert "Cluster" in kinds
    assert "KubeadmControlPlane" in kinds
    assert "MachineDeployment" in kinds
