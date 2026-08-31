"""
Covers services/target_cluster.py -- this is the piece that lets this
backend talk to a TARGET cluster (one it provisioned) rather than only
ever the management cluster. The critical property is isolation: building
a client for a target cluster must NOT mutate kubernetes-client's global
default Configuration, which services/kubernetes.py's KubernetesService
depends on for the management cluster. If it did, every in-flight
management-cluster call in the same process would silently start hitting
the wrong API server.
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services import target_cluster  # noqa: E402

FAKE_KUBECONFIG = """
apiVersion: v1
kind: Config
clusters:
- name: target-cluster
  cluster:
    server: https://192.0.2.100:6443
    insecure-skip-tls-verify: true
contexts:
- name: target-context
  context:
    cluster: target-cluster
    user: target-user
current-context: target-context
users:
- name: target-user
  user:
    token: fake-test-token
"""


def test_build_client_points_at_the_right_server():
    api_client = target_cluster.build_client_for_kubeconfig(FAKE_KUBECONFIG)
    assert api_client.configuration.host == "https://192.0.2.100:6443"


def test_build_client_never_mutates_the_global_default_configuration():
    from kubernetes import client

    before = client.Configuration.get_default_copy()
    target_cluster.build_client_for_kubeconfig(FAKE_KUBECONFIG)
    after = client.Configuration.get_default_copy()

    assert before.host == after.host
    assert after.host != "https://192.0.2.100:6443"


def test_typed_api_client_built_from_isolated_client_uses_target_host():
    from kubernetes import client

    api_client = target_cluster.build_client_for_kubeconfig(FAKE_KUBECONFIG)
    core_v1 = client.CoreV1Api(api_client=api_client)
    assert core_v1.api_client.configuration.host == "https://192.0.2.100:6443"


def test_build_client_rejects_non_kubeconfig_yaml():
    try:
        target_cluster.build_client_for_kubeconfig("not: a\nkubeconfig: at all\n")
        assert False, "should have raised TargetClusterUnreachable"
    except target_cluster.TargetClusterUnreachable as exc:
        assert "clusters" in str(exc)


def test_build_client_rejects_invalid_yaml():
    try:
        target_cluster.build_client_for_kubeconfig("{not valid yaml: [")
        assert False, "should have raised TargetClusterUnreachable"
    except target_cluster.TargetClusterUnreachable:
        pass


def test_fetch_kubeconfig_decodes_secret_value():
    import base64

    encoded = base64.b64encode(FAKE_KUBECONFIG.encode()).decode()
    fake_secret = MagicMock(data={"value": encoded})

    with patch("app.services.target_cluster.KubernetesService._ensure_loaded", return_value=None), \
         patch(
             "app.services.target_cluster.KubernetesService.core_v1",
             new_callable=lambda: property(lambda self: MagicMock(read_namespaced_secret=MagicMock(return_value=fake_secret))),
         ):
        result = target_cluster.fetch_target_cluster_kubeconfig("my-cluster", "metal3")
        assert result == FAKE_KUBECONFIG


def test_fetch_kubeconfig_raises_clear_error_when_secret_missing():
    from kubernetes.client.rest import ApiException

    with patch("app.services.target_cluster.KubernetesService._ensure_loaded", return_value=None), \
         patch(
             "app.services.target_cluster.KubernetesService.core_v1",
             new_callable=lambda: property(
                 lambda self: MagicMock(read_namespaced_secret=MagicMock(side_effect=ApiException(status=404)))
             ),
         ):
        try:
            target_cluster.fetch_target_cluster_kubeconfig("not-ready", "metal3")
            assert False, "should have raised TargetClusterUnreachable"
        except target_cluster.TargetClusterUnreachable as exc:
            assert "not-ready-kubeconfig" in str(exc)
            assert "control plane probably isn't ready" in str(exc)


def test_fetch_kubeconfig_raises_on_missing_value_key():
    fake_secret = MagicMock(data={"some-other-key": "whatever"})

    with patch("app.services.target_cluster.KubernetesService._ensure_loaded", return_value=None), \
         patch(
             "app.services.target_cluster.KubernetesService.core_v1",
             new_callable=lambda: property(lambda self: MagicMock(read_namespaced_secret=MagicMock(return_value=fake_secret))),
         ):
        try:
            target_cluster.fetch_target_cluster_kubeconfig("weird-cluster", "metal3")
            assert False, "should have raised TargetClusterUnreachable"
        except target_cluster.TargetClusterUnreachable as exc:
            assert "no 'value' key" in str(exc)
