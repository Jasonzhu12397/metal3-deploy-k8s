"""
Cluster API "pivoting" -- moving CAPI's own management of a cluster's
resources (Cluster, Metal3Cluster, KubeadmControlPlane, MachineDeployment,
BareMetalHost, and everything CAPI/CAPM3 owns underneath them) from one
Kubernetes cluster to another, live, without recreating the workload
cluster itself.

This is the step deployment_tasks.py's own module docstring has
documented as planned since this project's first commit ("6. (optionally)
pivot CAPI management from the ephemeral node to the newly-created target
cluster, then decommission the ephemeral node") but never actually
implemented, until now.

Why this shells out to the real `clusterctl move` binary instead of
reimplementing the move in Python: clusterctl's mover
(cluster-api/cmd/clusterctl/client/cluster/mover.go upstream) handles
real complexity that's easy to get subtly wrong reimplementing from
scratch -- pausing reconciliation on the source before moving, moving
objects in an order that respects owner references (a Machine can't be
created on the target before the MachineSet/Deployment that owns it
exists there), rewriting cross-cluster UID references, discovering
every CAPI-related CRD type dynamically rather than a hardcoded list,
and only deleting from the source once the target confirms receipt.
Getting any of that wrong risks orphaned or duplicated cluster objects
-- not something to risk shipping a from-scratch reimplementation of
when upstream has already solved it and this project already shells out
to clusterctl elsewhere (see deploy/testing/capd-quickstart/,
deploy/bootstrap-management-cluster/) for the same reason.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PivotError(RuntimeError):
    """Raised when `clusterctl move` itself fails -- distinct from a
    generic Exception so callers can log clusterctl's own stderr rather
    than a bare traceback."""


def pivot_management_to_target(
    *,
    source_kubeconfig_path: str,
    target_kubeconfig_yaml: str,
    namespace: str,
    clusterctl_binary: str | None = None,
    timeout_seconds: int = 300,
) -> str:
    """Moves CAPI management of everything in `namespace` from the
    source cluster (typically the ephemeral bootstrap node acting as a
    temporary management cluster) to the target cluster (the one CAPI
    just finished provisioning, which is about to become self-hosting).

    `target_kubeconfig_yaml` is the raw kubeconfig YAML text -- callers
    get this from services/target_cluster.py's
    fetch_target_cluster_kubeconfig(), the same CAPI-standard
    "<cluster-name>-kubeconfig" Secret this project already reads for
    AI workload deployment. clusterctl's --to-kubeconfig flag needs an
    actual file path, not YAML text, so this writes it to a private
    temp file for the duration of the move and always cleans up
    afterward, including on failure.

    Returns clusterctl's combined stdout+stderr (useful to store in the
    Deployment's own log field, same as every other phase in
    deployment_tasks.py already does) on success. Raises PivotError with
    that same output on failure -- callers should treat a failed pivot
    as fatal for the deployment, not something to silently continue
    past, since it leaves CAPI management split across two clusters in
    an undefined state.
    """
    binary = clusterctl_binary or settings.CLUSTERCTL_BINARY_PATH

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as target_kubeconfig_file:
        target_kubeconfig_file.write(target_kubeconfig_yaml)
        target_kubeconfig_path = target_kubeconfig_file.name

    try:
        result = subprocess.run(
            [
                binary,
                "move",
                "--namespace", namespace,
                "--kubeconfig", source_kubeconfig_path,
                "--to-kubeconfig", target_kubeconfig_path,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            raise PivotError(f"clusterctl move failed (exit {result.returncode}):\n{output}")
        logger.info("Pivot complete for namespace %s", namespace)
        return output
    except subprocess.TimeoutExpired as exc:
        raise PivotError(
            f"clusterctl move did not finish within {timeout_seconds}s -- it may have "
            f"partially moved objects; check both clusters by hand before retrying."
        ) from exc
    except FileNotFoundError as exc:
        raise PivotError(
            f"clusterctl binary not found at '{binary}' -- set CLUSTERCTL_BINARY_PATH, "
            f"or bundle clusterctl into this image (see deploy/bootstrap-management-cluster/ "
            f"for where this project already downloads it)."
        ) from exc
    finally:
        Path(target_kubeconfig_path).unlink(missing_ok=True)
