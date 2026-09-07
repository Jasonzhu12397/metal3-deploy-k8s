"""
Actually installs an addon onto a target cluster -- the "extension
point" tasks/deployment_tasks.py's own docstring has flagged since this
project's first commit ("Addon install ... is deliberately left as an
extension point"). Not implemented until now.

Two real install mechanisms, matching how each addon's own upstream
project actually recommends installing it -- not one invented uniform
mechanism:

  - "manifest": kubectl apply -f <url> for one or more pre-built release
    manifest URLs, in order. This is KubeVirt's own documented install
    method (kubectl apply the operator manifest, then the CR that
    triggers the operator to actually deploy) -- see
    https://kubevirt.io/user-guide/cluster_admin/installation/.
  - "helm": helm repo add + helm upgrade --install. This is Kube-OVN's
    own documented install method since v1.12.0 -- see
    https://kube-ovn.readthedocs.io/.

Shells out to the real `kubectl` and `helm` binaries rather than
reimplementing "apply this YAML" or "template and apply this chart" via
the Python Kubernetes client -- the same reasoning as services/pivot.py
for clusterctl: correctly handling every resource kind a real manifest
or chart can contain (RBAC, CRDs, webhooks, Helm's own hooks/templating)
is what these tools already do, well-tested, and reimplementing that
surface risks getting a corner case subtly wrong.
"""
from __future__ import annotations

import logging
import subprocess
from typing import Literal, TypedDict

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ManifestInstall(TypedDict):
    method: Literal["manifest"]
    urls: list[str]


class HelmInstall(TypedDict):
    method: Literal["helm"]
    repo_name: str
    repo_url: str
    chart: str
    release_name: str
    namespace: str
    version: str
    values: dict[str, str]  # flat --set key=value pairs, not a values.yaml file


InstallMethod = ManifestInstall | HelmInstall


class AddonInstallError(RuntimeError):
    """Raised when the underlying kubectl/helm command fails -- distinct
    from a generic Exception so callers can log the tool's own stderr."""


# Only entries with real, verified install methods -- see this module's
# own docstring for why the rest of ADDON_CATALOG (services/addon_catalog.py)
# isn't guessed at here. install_addon() raises a clear AddonInstallError
# for any addon name not in this dict, rather than silently doing
# nothing (which would be worse: a user enabling an addon and believing
# it's running when nothing happened).
INSTALL_METHODS: dict[str, InstallMethod] = {
    "kubevirt": {
        "method": "manifest",
        "urls": [
            "https://github.com/kubevirt/kubevirt/releases/download/v1.9.0/kubevirt-operator.yaml",
            "https://github.com/kubevirt/kubevirt/releases/download/v1.9.0/kubevirt-cr.yaml",
        ],
    },
    "kube-ovn": {
        "method": "helm",
        "repo_name": "kubeovn",
        "repo_url": "https://kubeovn.github.io/kube-ovn/",
        "chart": "kubeovn/kube-ovn",
        "release_name": "kube-ovn",
        "namespace": "kube-system",
        "version": "v1.15.24",
        "values": {},
    },
}


def _run(args: list[str], *, kubeconfig_path: str, timeout_seconds: int) -> str:
    result = subprocess.run(
        [*args, "--kubeconfig", kubeconfig_path],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise AddonInstallError(f"{args[0]} failed (exit {result.returncode}):\n{output}")
    return output


def install_addon(
    addon_name: str,
    *,
    kubeconfig_path: str,
    kubectl_binary: str | None = None,
    helm_binary: str | None = None,
    timeout_seconds: int = 600,
) -> str:
    """Installs `addon_name` onto whatever cluster `kubeconfig_path`
    points at (the target/workload cluster -- callers get this the same
    way services/pivot.py does, from
    services/target_cluster.py's fetch_target_cluster_kubeconfig(),
    written to a temp file). Returns the combined tool output on
    success (stored in the Deployment's log field, same as every other
    phase). Raises AddonInstallError on any failure, or if the addon
    has no real install method wired up yet.
    """
    install = INSTALL_METHODS.get(addon_name)
    if install is None:
        raise AddonInstallError(
            f"'{addon_name}' has no install method wired up yet in services/addons.py's "
            f"INSTALL_METHODS -- it exists in the app-store catalog (browsable, toggleable "
            f"as an intent on a cluster) but enabling it does not yet install anything real. "
            f"See that module's docstring."
        )

    kubectl = kubectl_binary or settings.KUBECTL_BINARY_PATH
    helm = helm_binary or settings.HELM_BINARY_PATH

    if install["method"] == "manifest":
        output_parts = []
        for url in install["urls"]:
            output_parts.append(
                _run([kubectl, "apply", "-f", url], kubeconfig_path=kubeconfig_path, timeout_seconds=timeout_seconds)
            )
        logger.info("Installed addon %s via kubectl apply (%d manifests)", addon_name, len(install["urls"]))
        return "\n".join(output_parts)

    # method == "helm"
    _run(
        [helm, "repo", "add", install["repo_name"], install["repo_url"], "--force-update"],
        kubeconfig_path=kubeconfig_path,
        timeout_seconds=timeout_seconds,
    )
    _run([helm, "repo", "update", install["repo_name"]], kubeconfig_path=kubeconfig_path, timeout_seconds=timeout_seconds)

    helm_args = [
        helm, "upgrade", "--install", install["release_name"], install["chart"],
        "--namespace", install["namespace"], "--create-namespace",
        "--version", install["version"], "--wait",
    ]
    for key, value in install["values"].items():
        helm_args += ["--set", f"{key}={value}"]

    output = _run(helm_args, kubeconfig_path=kubeconfig_path, timeout_seconds=timeout_seconds)
    logger.info("Installed addon %s via helm (release=%s)", addon_name, install["release_name"])
    return output
