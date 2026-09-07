"""
Covers services/addons.py -- the "extension point" tasks/deployment_tasks.py's
own docstring has flagged as unimplemented since this project's first
commit ("Addon install ... is deliberately left as an extension point").
Not implemented until now, specifically for kubevirt (kubectl apply, its
own documented install method) and kube-ovn (helm install, its own
documented install method since v1.12.0).
"""
import os
import subprocess
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest  # noqa: E402

from app.services.addons import AddonInstallError, INSTALL_METHODS, install_addon  # noqa: E402


def _completed(returncode=0, stdout="ok", stderr=""):
    return subprocess.CompletedProcess([], returncode=returncode, stdout=stdout, stderr=stderr)


def test_unknown_addon_raises_clearly_instead_of_silently_doing_nothing():
    """The exact gap this module closes: enabling an addon that isn't
    actually wired up must fail loudly, not silently succeed while
    installing nothing -- that's strictly worse than a clear error, since
    a user would believe it's running."""
    with pytest.raises(AddonInstallError, match="no install method wired up"):
        install_addon("totally-not-a-real-addon", kubeconfig_path="/tmp/fake.yaml")


def test_kubevirt_applies_both_manifests_in_order_via_kubectl():
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _completed(stdout=f"applied {args[-1]}")

    with patch("app.services.addons.subprocess.run", side_effect=fake_run):
        output = install_addon(
            "kubevirt", kubeconfig_path="/tmp/fake-kubeconfig.yaml", kubectl_binary="kubectl", timeout_seconds=30
        )

    assert len(calls) == 2
    assert calls[0][:3] == ["kubectl", "apply", "-f"]
    assert "kubevirt-operator.yaml" in calls[0][3]
    assert calls[1][:3] == ["kubectl", "apply", "-f"]
    assert "kubevirt-cr.yaml" in calls[1][3]
    # kubeconfig must be passed to BOTH calls, not just the first
    assert all("--kubeconfig" in c and "/tmp/fake-kubeconfig.yaml" in c for c in calls)
    assert "applied" in output


def test_kubevirt_stops_and_raises_if_the_operator_manifest_fails():
    """The CR must never be applied if the operator itself failed to
    install -- applying it against a cluster with no KubeVirt CRDs yet
    would just fail differently and more confusingly."""
    with patch("app.services.addons.subprocess.run", return_value=_completed(returncode=1, stderr="connection refused")):
        with pytest.raises(AddonInstallError, match="connection refused"):
            install_addon("kubevirt", kubeconfig_path="/tmp/fake.yaml")


def test_kube_ovn_runs_helm_repo_add_update_then_install():
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _completed()

    with patch("app.services.addons.subprocess.run", side_effect=fake_run):
        install_addon("kube-ovn", kubeconfig_path="/tmp/fake-kubeconfig.yaml", helm_binary="helm", timeout_seconds=30)

    assert calls[0][:3] == ["helm", "repo", "add"]
    assert calls[0][3] == "kubeovn"
    assert calls[1][:3] == ["helm", "repo", "update"]
    assert calls[2][:4] == ["helm", "upgrade", "--install", "kube-ovn"]
    assert "kubeovn/kube-ovn" in calls[2]
    assert "--namespace" in calls[2] and "kube-system" in calls[2]
    assert "--version" in calls[2]


def test_kube_ovn_helm_install_failure_raises_addon_install_error():
    with patch(
        "app.services.addons.subprocess.run",
        side_effect=[_completed(), _completed(), _completed(returncode=1, stderr="chart not found")],
    ):
        with pytest.raises(AddonInstallError, match="chart not found"):
            install_addon("kube-ovn", kubeconfig_path="/tmp/fake.yaml")


def test_timeout_propagates_as_a_subprocess_timeout_not_swallowed():
    with patch("app.services.addons.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="kubectl", timeout=5)):
        with pytest.raises(subprocess.TimeoutExpired):
            install_addon("kubevirt", kubeconfig_path="/tmp/fake.yaml", timeout_seconds=5)


def test_install_methods_registry_only_has_verified_entries():
    """Documents the honest scope: only addons with a real, checked
    install method belong here. If this test starts failing because
    someone added a new entry, that's a prompt to make sure it was
    actually researched (real manifest URLs / real chart name+repo),
    not guessed."""
    assert set(INSTALL_METHODS.keys()) == {"kubevirt", "kube-ovn"}
    assert INSTALL_METHODS["kubevirt"]["method"] == "manifest"
    assert INSTALL_METHODS["kube-ovn"]["method"] == "helm"
