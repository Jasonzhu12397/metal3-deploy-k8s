"""
Everything this backend has done so far talks to the *management*
cluster (Metal3/Ironic/CAPI live there) via services/kubernetes.py, whose
`_ensure_loaded()` calls `kubernetes.config.load_kube_config()`/
`load_incluster_config()` -- these mutate the kubernetes-client library's
GLOBAL default Configuration. That's fine as long as this process only
ever needs to talk to one cluster.

Deploying a workload (vLLM, or anything else) onto a *target* cluster --
one CAPI actually provisioned -- needs a second, genuinely different
cluster connection, live at the same time as the management-cluster one.
Naively calling load_kube_config() again would silently clobber the
global default and make every other in-flight management-cluster call
in this process start hitting the wrong API server. So this module never
touches the global config at all: it builds an isolated
client.Configuration + client.ApiClient pair per target cluster,
scoped to that one kubeconfig, and hands that back for callers to build
typed API clients (CoreV1Api, AppsV1Api, ...) from explicitly.

Where the target cluster's kubeconfig comes from: Cluster API's own,
well-established convention (not something this project invented) --
once a Cluster's control plane is ready, the relevant CAPI controller
creates a Secret named "<cluster-name>-kubeconfig" in the same namespace
as the Cluster object, with the kubeconfig YAML (not JSON) base64-encoded
under a data key literally named "value". `clusterctl get kubeconfig`
is just a thin wrapper around reading exactly that Secret.
"""
from __future__ import annotations

import base64
import logging

import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from app.services.kubernetes import KubernetesService

logger = logging.getLogger(__name__)


class TargetClusterUnreachable(RuntimeError):
    """Raised when the target cluster's kubeconfig Secret doesn't exist
    yet (cluster still provisioning) or can't be parsed -- distinct from
    a generic Exception so callers can show "not ready yet" rather than
    a raw stack trace."""


def fetch_target_cluster_kubeconfig(cluster_name: str, namespace: str) -> str:
    """Reads "<cluster-name>-kubeconfig" from the MANAGEMENT cluster
    (via the existing, global-config-based KubernetesService -- this one
    read is fine to share, it's everything built from the result that
    needs isolation) and returns the decoded kubeconfig YAML text."""
    mgmt_k8s = KubernetesService()
    secret_name = f"{cluster_name}-kubeconfig"
    try:
        secret = mgmt_k8s.core_v1.read_namespaced_secret(name=secret_name, namespace=namespace)
    except ApiException as exc:
        if exc.status == 404:
            raise TargetClusterUnreachable(
                f"Secret {namespace}/{secret_name} doesn't exist yet -- the cluster's control "
                f"plane probably isn't ready. Check the deployment's status first."
            ) from exc
        raise

    encoded = (secret.data or {}).get("value")
    if not encoded:
        raise TargetClusterUnreachable(
            f"Secret {namespace}/{secret_name} exists but has no 'value' key -- not a "
            f"CAPI-generated kubeconfig Secret, or its format has changed."
        )

    try:
        return base64.b64decode(encoded).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise TargetClusterUnreachable(f"Secret {namespace}/{secret_name}'s value isn't valid base64/UTF-8") from exc


def build_client_for_kubeconfig(kubeconfig_yaml: str) -> client.ApiClient:
    """Turns kubeconfig YAML text into an isolated ApiClient that never
    touches kubernetes-client's global default Configuration -- safe to
    use alongside the management-cluster KubernetesService in the same
    process without either one clobbering the other."""
    try:
        kubeconfig_dict = yaml.safe_load(kubeconfig_yaml)
    except yaml.YAMLError as exc:
        raise TargetClusterUnreachable(f"kubeconfig is not valid YAML: {exc}") from exc

    if not isinstance(kubeconfig_dict, dict) or "clusters" not in kubeconfig_dict:
        raise TargetClusterUnreachable("kubeconfig YAML doesn't look like a kubeconfig (no top-level 'clusters' key)")

    configuration = client.Configuration()
    config.load_kube_config_from_dict(kubeconfig_dict, client_configuration=configuration)
    return client.ApiClient(configuration=configuration)


def get_client_for_cluster(cluster_name: str, namespace: str) -> client.ApiClient:
    """Convenience wrapper: fetch the Secret + build the isolated client
    in one call. Most callers want this; the two split functions above
    exist mainly so tests can exercise the YAML-parsing/client-building
    logic without needing a real Secret read."""
    kubeconfig_yaml = fetch_target_cluster_kubeconfig(cluster_name, namespace)
    return build_client_for_kubeconfig(kubeconfig_yaml)


def apply_deployment_and_service(
    target_api_client: client.ApiClient, deployment_manifest: dict, service_manifest: dict
) -> None:
    """Applies a plain Deployment + Service to the target cluster (create,
    or replace on 409 -- same create-or-replace convention
    services/kubernetes.py's apply_custom_object uses for the management
    cluster's CAPI objects, kept consistent rather than inventing a
    second convention)."""
    apps_v1 = client.AppsV1Api(api_client=target_api_client)
    core_v1 = client.CoreV1Api(api_client=target_api_client)

    namespace = deployment_manifest["metadata"]["namespace"]
    name = deployment_manifest["metadata"]["name"]

    try:
        apps_v1.create_namespaced_deployment(namespace=namespace, body=deployment_manifest)
    except ApiException as exc:
        if exc.status == 409:
            apps_v1.replace_namespaced_deployment(name=name, namespace=namespace, body=deployment_manifest)
        else:
            raise

    try:
        core_v1.create_namespaced_service(namespace=namespace, body=service_manifest)
    except ApiException as exc:
        if exc.status == 409:
            existing = core_v1.read_namespaced_service(name=name, namespace=namespace)
            service_manifest["metadata"]["resourceVersion"] = existing.metadata.resource_version
            # Services need the existing clusterIP carried forward on
            # replace, or the API server rejects the update outright.
            service_manifest.setdefault("spec", {})["clusterIP"] = existing.spec.cluster_ip
            core_v1.replace_namespaced_service(name=name, namespace=namespace, body=service_manifest)
        else:
            raise


def delete_deployment_and_service(target_api_client: client.ApiClient, namespace: str, name: str) -> None:
    apps_v1 = client.AppsV1Api(api_client=target_api_client)
    core_v1 = client.CoreV1Api(api_client=target_api_client)
    for fn, kind in ((apps_v1.delete_namespaced_deployment, "Deployment"), (core_v1.delete_namespaced_service, "Service")):
        try:
            fn(name=name, namespace=namespace)
        except ApiException as exc:
            if exc.status != 404:
                logger.warning("Failed to delete %s %s/%s: %s", kind, namespace, name, exc)
