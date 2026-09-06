"""
Covers services/pivot.py -- the previously-unimplemented "step 6" from
deployment_tasks.py's own module docstring (pivoting CAPI management
from an ephemeral bootstrap node to a newly-self-hosting target
cluster).

Can't test a real `clusterctl move` against two real clusters here (see
this project's other "no real hardware/cluster in this sandbox" notes
throughout its test suite/READMEs for the same limitation) -- these
tests instead verify the part that's actually this project's own code:
correct command construction, correct temp-file lifecycle (written with
the right content, always cleaned up including on failure), and correct
error handling for each real failure mode (non-zero exit, timeout,
binary not found). The actual clusterctl move logic itself is real,
upstream, well-tested code this project intentionally does not
reimplement -- see that module's docstring for why.
"""
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest  # noqa: E402

from app.services.pivot import PivotError, pivot_management_to_target  # noqa: E402


SAMPLE_KUBECONFIG = """
apiVersion: v1
kind: Config
clusters:
- cluster: {server: https://target.example.com:6443}
  name: target
contexts:
- context: {cluster: target, user: admin}
  name: target
current-context: target
users:
- name: admin
  user: {token: fake-token}
"""


def test_successful_pivot_calls_clusterctl_move_with_correct_args():
    captured_args = {}

    def fake_run(args, **kwargs):
        captured_args["args"] = args
        captured_args["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, returncode=0, stdout="Moving Cluster default/my-cluster\nDone.", stderr="")

    with patch("app.services.pivot.subprocess.run", side_effect=fake_run):
        output = pivot_management_to_target(
            source_kubeconfig_path="/tmp/fake-source-kubeconfig.yaml",
            target_kubeconfig_yaml=SAMPLE_KUBECONFIG,
            namespace="metal3",
            clusterctl_binary="/usr/local/bin/clusterctl",
            timeout_seconds=60,
        )

    args = captured_args["args"]
    assert args[0] == "/usr/local/bin/clusterctl"
    assert args[1] == "move"
    assert "--namespace" in args and args[args.index("--namespace") + 1] == "metal3"
    assert "--kubeconfig" in args and args[args.index("--kubeconfig") + 1] == "/tmp/fake-source-kubeconfig.yaml"
    assert "--to-kubeconfig" in args
    assert captured_args["kwargs"]["timeout"] == 60
    assert "Moving Cluster" in output


def test_target_kubeconfig_is_written_to_a_real_temp_file_and_cleaned_up():
    """clusterctl's --to-kubeconfig needs an actual file path, not YAML
    text -- confirms the temp file this function creates actually has
    the target kubeconfig's content, and confirms it's gone afterward
    (not leaking a credentials file with a live cluster's admin token
    onto disk indefinitely)."""
    written_path = {}

    def fake_run(args, **kwargs):
        to_kubeconfig_path = args[args.index("--to-kubeconfig") + 1]
        written_path["path"] = to_kubeconfig_path
        with open(to_kubeconfig_path) as f:
            written_path["content"] = f.read()
        return subprocess.CompletedProcess(args, returncode=0, stdout="ok", stderr="")

    with patch("app.services.pivot.subprocess.run", side_effect=fake_run):
        pivot_management_to_target(
            source_kubeconfig_path="/tmp/fake-source.yaml",
            target_kubeconfig_yaml=SAMPLE_KUBECONFIG,
            namespace="metal3",
            clusterctl_binary="clusterctl",
        )

    assert written_path["content"] == SAMPLE_KUBECONFIG
    assert not os.path.exists(written_path["path"]), "the temp kubeconfig file must be deleted after the move, success or not"


def test_temp_file_is_cleaned_up_even_when_clusterctl_fails():
    written_path = {}

    def fake_run(args, **kwargs):
        written_path["path"] = args[args.index("--to-kubeconfig") + 1]
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="Error: failed to connect to target cluster")

    with patch("app.services.pivot.subprocess.run", side_effect=fake_run):
        with pytest.raises(PivotError, match="failed to connect"):
            pivot_management_to_target(
                source_kubeconfig_path="/tmp/fake-source.yaml",
                target_kubeconfig_yaml=SAMPLE_KUBECONFIG,
                namespace="metal3",
                clusterctl_binary="clusterctl",
            )

    assert not os.path.exists(written_path["path"]), "temp file must still be cleaned up when the move fails"


def test_nonzero_exit_raises_pivot_error_with_clusterctl_output():
    with patch(
        "app.services.pivot.subprocess.run",
        return_value=subprocess.CompletedProcess([], returncode=1, stdout="some progress\n", stderr="Error: namespace not found"),
    ):
        with pytest.raises(PivotError, match="namespace not found"):
            pivot_management_to_target(
                source_kubeconfig_path="/tmp/fake-source.yaml",
                target_kubeconfig_yaml=SAMPLE_KUBECONFIG,
                namespace="metal3",
                clusterctl_binary="clusterctl",
            )


def test_timeout_raises_pivot_error_with_a_clear_warning_about_partial_moves():
    with patch("app.services.pivot.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="clusterctl", timeout=5)):
        with pytest.raises(PivotError, match="partially moved"):
            pivot_management_to_target(
                source_kubeconfig_path="/tmp/fake-source.yaml",
                target_kubeconfig_yaml=SAMPLE_KUBECONFIG,
                namespace="metal3",
                clusterctl_binary="clusterctl",
                timeout_seconds=5,
            )


def test_missing_clusterctl_binary_raises_a_helpful_pivot_error():
    with patch("app.services.pivot.subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(PivotError, match="clusterctl binary not found"):
            pivot_management_to_target(
                source_kubeconfig_path="/tmp/fake-source.yaml",
                target_kubeconfig_yaml=SAMPLE_KUBECONFIG,
                namespace="metal3",
                clusterctl_binary="/nonexistent/clusterctl",
            )


def test_uses_settings_default_binary_path_when_not_overridden():
    with patch("app.services.pivot.settings") as mock_settings:
        mock_settings.CLUSTERCTL_BINARY_PATH = "/opt/tools/clusterctl"
        with patch("app.services.pivot.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr="")
            pivot_management_to_target(
                source_kubeconfig_path="/tmp/fake-source.yaml",
                target_kubeconfig_yaml=SAMPLE_KUBECONFIG,
                namespace="metal3",
            )
            assert mock_run.call_args[0][0][0] == "/opt/tools/clusterctl"
