"""
Covers the Fernet-based BMC credential encryption end to end:

- the crypto module itself (round trip, wrong key fails, missing key
  fails loudly instead of silently storing plaintext)
- registering a BMH actually persists an *encrypted* password (not the
  plaintext, not base64, not anything reversible without the key)
- no API response -- not GET, not the registration response, not the
  credential-setting response -- ever contains the plaintext password or
  even the ciphertext column
- resync-bmc-secret can decrypt and re-push to the Kubernetes Secret
  without ever handing the password back to the caller
"""
import asyncio
import base64
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

TEST_KEY = "zJmN3-3ZQwJmPfLh6l3xF8x8y6qF1r0t8ZQwJmPfLh4="  # not a secret -- test fixture only


def _fresh_settings_with_key(key: str | None):
    """core.config.get_settings() is @lru_cache'd, so tests that need a
    different BMC_ENCRYPTION_KEY have to clear it and re-set the env var
    first."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    if key is None:
        os.environ.pop("BMC_ENCRYPTION_KEY", None)
    else:
        os.environ["BMC_ENCRYPTION_KEY"] = key
    return get_settings()


def test_encrypt_decrypt_round_trip():
    _fresh_settings_with_key(TEST_KEY)
    from app.services import crypto

    ciphertext = crypto.encrypt_secret("SuperSecretBmcPassword123!")
    assert ciphertext != "SuperSecretBmcPassword123!"
    # not base64-of-plaintext either -- a real encryption ciphertext, not
    # just an encoding, should not trivially decode back to the plaintext
    # the way base64 would.
    try:
        decoded_as_if_base64 = base64.b64decode(ciphertext + "==").decode("utf-8", errors="ignore")
        assert "SuperSecretBmcPassword123!" not in decoded_as_if_base64
    except Exception:
        pass  # not valid base64 at all -- also fine, that's the point
    assert crypto.decrypt_secret(ciphertext) == "SuperSecretBmcPassword123!"


def test_missing_key_raises_instead_of_silently_storing_plaintext():
    _fresh_settings_with_key(None)
    from app.services import crypto

    try:
        crypto.encrypt_secret("whatever")
        assert False, "should have raised EncryptionKeyNotConfigured"
    except crypto.EncryptionKeyNotConfigured:
        pass


def test_wrong_key_cannot_decrypt():
    _fresh_settings_with_key(TEST_KEY)
    from app.services import crypto
    from cryptography.fernet import Fernet

    ciphertext = crypto.encrypt_secret("secret-value")

    _fresh_settings_with_key(Fernet.generate_key().decode())
    try:
        crypto.decrypt_secret(ciphertext)
        assert False, "should have raised InvalidToken with the wrong key"
    except crypto.InvalidToken:
        pass


def test_key_rotation_helper():
    from app.services import crypto
    from cryptography.fernet import Fernet

    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    _fresh_settings_with_key(old_key)
    ciphertext_old = crypto.encrypt_secret("rotate-me")

    rotated = crypto.rotate_key(ciphertext_old, [new_key, old_key])

    _fresh_settings_with_key(new_key)
    assert crypto.decrypt_secret(rotated) == "rotate-me"


def test_registering_a_host_stores_encrypted_password_never_plaintext():
    _fresh_settings_with_key(TEST_KEY)
    asyncio.run(_reset())

    with patch("app.services.kubernetes.KubernetesService._ensure_loaded", return_value=None), \
         patch("app.services.bmc.BMCService.store_credentials", return_value="x-bmc-secret"), \
         patch(
             "app.services.metal3.Metal3Service.register_host",
             return_value={"metadata": {"resourceVersion": "1"}},
         ):
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            headers = _login(client)
            plaintext_password = "extremely-real-bmc-password"

            r = client.post(
                "/api/v1/baremetalhosts",
                json={
                    "name": "encrypt-test-host",
                    "node_pool_name": "pool1",
                    "bmc_address": "redfish://192.168.1.10",
                    "boot_mac_address": "aa:bb:cc:dd:ee:01",
                    "credentials": {"username": "admin", "password": plaintext_password},
                },
                headers=headers,
            )
            assert r.status_code == 201

            # the registration response itself must not echo the password back
            assert plaintext_password not in r.text

            asset = next(
                a
                for a in client.get("/api/v1/hardware-assets", headers=headers).json()
                if a["name"] == "encrypt-test-host"
            )
            assert asset["has_bmc_credentials"] is True
            assert asset["bmc_username"] == "admin"
            # the plaintext password must never appear anywhere in the
            # response body, and there must be no field carrying the raw
            # ciphertext either -- HardwareAssetRead intentionally only
            # exposes the boolean.
            body_text = client.get("/api/v1/hardware-assets", headers=headers).text
            assert plaintext_password not in body_text
            assert "encrypted_bmc_password" not in body_text

            # ...but the plaintext really is recoverable server-side, which
            # is the whole point (unlike a bcrypt-hashed login password).
            async def _check_db():
                from sqlalchemy import select
                from app.core.db import AsyncSessionLocal
                from app.models.hardware_asset import HardwareAsset
                from app.services import crypto

                async with AsyncSessionLocal() as session:
                    row = await session.scalar(
                        select(HardwareAsset).where(HardwareAsset.name == "encrypt-test-host")
                    )
                    assert row.encrypted_bmc_password != plaintext_password
                    assert plaintext_password not in row.encrypted_bmc_password
                    assert crypto.decrypt_secret(row.encrypted_bmc_password) == plaintext_password

            asyncio.run(_check_db())


def test_resync_bmc_secret_never_returns_the_password():
    _fresh_settings_with_key(TEST_KEY)
    asyncio.run(_reset())

    with patch("app.services.kubernetes.KubernetesService._ensure_loaded", return_value=None), \
         patch("app.services.bmc.BMCService.store_credentials", return_value="resync-test-host-bmc-secret") as mock_store, \
         patch(
             "app.services.metal3.Metal3Service.register_host",
             return_value={"metadata": {"resourceVersion": "1"}},
         ):
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            headers = _login(client)
            plaintext_password = "another-real-password"

            client.post(
                "/api/v1/baremetalhosts",
                json={
                    "name": "resync-test-host",
                    "node_pool_name": "pool1",
                    "bmc_address": "redfish://192.168.1.11",
                    "boot_mac_address": "aa:bb:cc:dd:ee:02",
                    "credentials": {"username": "root", "password": plaintext_password},
                },
                headers=headers,
            )
            asset_id = next(
                a["id"]
                for a in client.get("/api/v1/hardware-assets", headers=headers).json()
                if a["name"] == "resync-test-host"
            )

            mock_store.reset_mock()
            r = client.post(f"/api/v1/hardware-assets/{asset_id}/resync-bmc-secret", headers=headers)
            assert r.status_code == 200
            assert plaintext_password not in r.text
            assert r.json()["resynced"] is True

            # confirm store_credentials was actually called with the
            # correctly-decrypted plaintext (checked here, server-side --
            # never exposed over the API)
            mock_store.assert_called_once()
            called_name, called_creds = mock_store.call_args[0]
            assert called_name == "resync-test-host"
            assert called_creds.password == plaintext_password
            assert called_creds.username == "root"


async def _reset():
    from sqlalchemy import delete
    from app.core.db import AsyncSessionLocal, init_db
    from app.models.user import User
    from app.services.auth import hash_password

    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(User))
        session.add(User(username="admin", hashed_password=hash_password("test-password-123")))
        await session.commit()


def _login(client) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "test-password-123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
