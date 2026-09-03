"""
Covers templates/capi/providers/docker.yaml.j2 (CAPD) -- pure Jinja2 +
yaml.safe_load, same as every other provider template's tests. CAPD is
the one provider that needs no external infra at all (no cloud
credentials, no flavor/image), which is exactly why it's the answer to
"prove this platform can actually deploy Kubernetes using only
containers" -- see deploy/testing/capd-quickstart/ for the runnable
demonstration this test file backs.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.yaml_generator import YamlGeneratorService  # noqa: E402

gen = YamlGeneratorService()


def test_single_node_control_plane_only():
    spec = {
        "name": "capd-demo",
        "namespace": "metal3",
        "infrastructure_provider": "docker",
        "control_plane_count": 1,
        "worker_pools": [],
    }
    docs = gen.parse_multi(gen.render_cluster_config(spec))
    kinds = [(d["kind"], d["metadata"]["name"]) for d in docs]
    assert kinds == [
        ("Cluster", "capd-demo"),
        ("DockerCluster", "capd-demo"),
        ("DockerMachineTemplate", "capd-demo-control-plane"),
        ("KubeadmControlPlane", "capd-demo-control-plane"),
    ]

    cluster_doc, docker_cluster, machine_template, kcp = docs

    assert cluster_doc["spec"]["infrastructureRef"]["kind"] == "DockerCluster"
    assert cluster_doc["spec"]["controlPlaneRef"]["kind"] == "KubeadmControlPlane"
    # unlike Metal3Cluster/OpenStackCluster/VSphereCluster, DockerCluster
    # doesn't take a controlPlaneEndpoint -- CAPD's own load-balancer
    # container fills that in itself
    assert docker_cluster["spec"] == {}

    assert machine_template["spec"]["template"]["spec"]["extraMounts"] == [
        {"containerPath": "/var/run/docker.sock", "hostPath": "/var/run/docker.sock"}
    ]

    assert kcp["spec"]["replicas"] == 1
    assert kcp["spec"]["machineTemplate"]["spec"]["infrastructureRef"]["kind"] == "DockerMachineTemplate"
    # default true here (opposite of every other provider) -- a
    # single-node CAPD cluster whose only node can't run workloads
    # defeats the point of a quick smoke test
    assert "postKubeadmCommands" in kcp["spec"]["kubeadmConfigSpec"]
    assert "taint node" in kcp["spec"]["kubeadmConfigSpec"]["postKubeadmCommands"][0]


def test_explicit_false_keeps_the_control_plane_taint():
    spec = {
        "name": "capd-demo",
        "namespace": "metal3",
        "infrastructure_provider": "docker",
        "control_plane_count": 3,
        "worker_pools": [],
        "allow_workloads_on_control_plane": False,
    }
    _cluster, _dc, _dmt, kcp = gen.parse_multi(gen.render_cluster_config(spec))
    assert "postKubeadmCommands" not in kcp["spec"]["kubeadmConfigSpec"]
    assert kcp["spec"]["replicas"] == 3


def test_worker_pool_renders_machine_deployment():
    spec = {
        "name": "capd-demo",
        "namespace": "metal3",
        "infrastructure_provider": "docker",
        "control_plane_count": 1,
        "worker_pools": [{"name": "workers", "count": 2, "node_labels": ["role=demo"]}],
    }
    docs = gen.parse_multi(gen.render_cluster_config(spec))
    kinds = [d["kind"] for d in docs]
    assert kinds.count("DockerMachineTemplate") == 2  # one for control-plane, one for the pool
    assert kinds.count("MachineDeployment") == 1
    assert kinds.count("KubeadmConfigTemplate") == 1

    md = next(d for d in docs if d["kind"] == "MachineDeployment")
    assert md["spec"]["replicas"] == 2
    assert md["spec"]["template"]["spec"]["infrastructureRef"]["kind"] == "DockerMachineTemplate"

    kct = next(d for d in docs if d["kind"] == "KubeadmConfigTemplate")
    kubelet_args = kct["spec"]["template"]["spec"]["joinConfiguration"]["nodeRegistration"]["kubeletExtraArgs"]
    labels = next(item["value"] for item in kubelet_args if item["name"] == "node-labels")
    assert labels == "role=demo"


def test_docker_provider_needs_no_flavor_or_image_fields():
    """Unlike openstack/vsphere, which crash under StrictUndefined without
    control_plane_flavor/control_plane_image, CAPD needs neither -- the
    whole point is zero external dependencies."""
    spec = {
        "name": "capd-minimal",
        "namespace": "metal3",
        "infrastructure_provider": "docker",
        "control_plane_count": 1,
        "worker_pools": [],
    }
    # must not raise jinja2.exceptions.UndefinedError
    gen.render_cluster_config(spec)
