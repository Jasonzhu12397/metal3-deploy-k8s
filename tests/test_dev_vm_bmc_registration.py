"""
Tests register_with_backend.py's HTTP-calling logic in isolation (mocked
requests) -- this is the one part of deploy/testing/vm-bmc/ that doesn't
need real libvirt/KVM to verify: does it build the right bmc_address
format, call the right endpoints, send the right payload shape matching
BareMetalHostCreate, and attach the auth header correctly. The
libvirt-facing half (create_test_nodes.py) can only be verified on a
real Linux host with KVM -- this sandbox has neither, so that part is
syntax-checked only, not run.
"""
import importlib.util
import os
import sys
from unittest.mock import MagicMock, patch

MODULE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "deploy", "testing", "vm-bmc", "register_with_backend.py"
)
spec = importlib.util.spec_from_file_location("register_with_backend", MODULE_PATH)
register_with_backend = importlib.util.module_from_spec(spec)
sys.modules["register_with_backend"] = register_with_backend
spec.loader.exec_module(register_with_backend)


def test_login_posts_correct_payload_and_returns_token():
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"access_token": "fake-token-123"}
    fake_resp.raise_for_status = MagicMock()

    with patch("register_with_backend.requests.post", return_value=fake_resp) as mock_post:
        token = register_with_backend.login("http://localhost:8000", "admin", "hunter2")

    assert token == "fake-token-123"
    mock_post.assert_called_once_with(
        "http://localhost:8000/api/v1/auth/login",
        json={"username": "admin", "password": "hunter2"},
    )


def test_register_node_builds_correct_bmc_address_and_payload():
    node = {"name": "metal3-test-node-01", "libvirt_uuid": "abc-123-uuid", "boot_mac_address": "52:54:00:aa:bb:cc"}
    fake_resp = MagicMock(status_code=201, text="")

    with patch("register_with_backend.requests.post", return_value=fake_resp) as mock_post:
        register_with_backend.register_node(
            api_base="http://localhost:8000",
            token="tok",
            node=node,
            sushy_host="192.168.122.1",
            sushy_port=8000,
            node_pool_name="test-pool",
            bmc_username="admin",
            bmc_password="sushy-pass",
        )

    mock_post.assert_called_once()
    call = mock_post.call_args
    assert call.args[0] == "http://localhost:8000/api/v1/baremetalhosts"
    assert call.kwargs["headers"] == {"Authorization": "Bearer tok"}

    payload = call.kwargs["json"]
    # exact format this project's docs/examples use elsewhere for redfish
    # bmc_address strings -- must match, since the backend just stores
    # this string verbatim into the BareMetalHost CR for baremetal-operator.
    assert payload["bmc_address"] == "redfish://192.168.122.1:8000/redfish/v1/Systems/abc-123-uuid"
    assert payload["name"] == "metal3-test-node-01"
    assert payload["boot_mac_address"] == "52:54:00:aa:bb:cc"
    assert payload["node_pool_name"] == "test-pool"
    assert payload["credentials"] == {"username": "admin", "password": "sushy-pass"}
    assert payload["online"] is False


def test_register_node_reports_failure_without_raising():
    node = {"name": "bad-node", "libvirt_uuid": "x", "boot_mac_address": "52:54:00:00:00:01"}
    fake_resp = MagicMock(status_code=422, text='{"detail": "validation error"}')

    with patch("register_with_backend.requests.post", return_value=fake_resp):
        # should not raise -- a single node failing shouldn't abort
        # registering the rest of the batch
        register_with_backend.register_node(
            api_base="http://localhost:8000",
            token="tok",
            node=node,
            sushy_host="127.0.0.1",
            sushy_port=8000,
            node_pool_name="pool1",
            bmc_username="admin",
            bmc_password="pw",
        )
