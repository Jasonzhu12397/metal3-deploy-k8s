"""
Covers LLM provider credential CRUD + the test-connection endpoint --
create/list/delete through the real API, encryption verified the same
way tests/test_bmc_credential_encryption.py verifies it for BMC
passwords (ciphertext != plaintext, API responses never leak the key),
and test-connection's HTTP call mocked (this sandbox has no real
OpenAI/DeepSeek/Qwen/Doubao API key to test against, and shouldn't burn
one even if it did).
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

TEST_KEY = "zJmN3-3ZQwJmPfLh6l3xF8x8y6qF1r0t8ZQwJmPfLh4="  # not a secret -- test fixture only, same as test_bmc_credential_encryption.py


def _fresh_settings_with_key(key: str | None):
    from app.core.config import get_settings

    get_settings.cache_clear()
    if key is None:
        os.environ.pop("BMC_ENCRYPTION_KEY", None)
    else:
        os.environ["BMC_ENCRYPTION_KEY"] = key
    return get_settings()


async def _reset():
    from sqlalchemy import delete
    from app.core.db import AsyncSessionLocal, init_db
    from app.models.user import User
    from app.models.llm_provider import LLMProviderCredential
    from app.services.auth import hash_password

    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(User))
        await session.execute(delete(LLMProviderCredential))
        session.add(User(username="admin", hashed_password=hash_password("test-password-123")))
        await session.commit()


def _login(client) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "test-password-123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_create_uses_known_default_base_url():
    _fresh_settings_with_key(TEST_KEY)
    asyncio.run(_reset())
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        headers = _login(client)
        r = client.post(
            "/api/v1/llm-providers",
            json={"label": "my-deepseek", "provider": "deepseek", "api_key": "sk-real-secret-key"},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["base_url"] == "https://api.deepseek.com/v1"
        # the plaintext key must never appear in the response
        assert "sk-real-secret-key" not in r.text
        assert "api_key" not in body
        assert "encrypted_api_key" not in body


def test_custom_provider_requires_explicit_base_url():
    _fresh_settings_with_key(TEST_KEY)
    asyncio.run(_reset())
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        headers = _login(client)
        r = client.post(
            "/api/v1/llm-providers",
            json={"label": "self-hosted", "provider": "custom", "api_key": "whatever"},
            headers=headers,
        )
        assert r.status_code == 422


def test_stored_key_is_actually_encrypted_not_plaintext():
    _fresh_settings_with_key(TEST_KEY)
    asyncio.run(_reset())
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import crypto

    plaintext_key = "sk-extremely-real-openai-key-123"

    with TestClient(app) as client:
        headers = _login(client)
        r = client.post(
            "/api/v1/llm-providers",
            json={"label": "my-openai", "provider": "openai", "api_key": plaintext_key},
            headers=headers,
        )
        credential_id = r.json()["id"]

    async def _check_db():
        import uuid as uuid_module
        from sqlalchemy import select
        from app.core.db import AsyncSessionLocal
        from app.models.llm_provider import LLMProviderCredential

        async with AsyncSessionLocal() as session:
            row = await session.get(LLMProviderCredential, uuid_module.UUID(credential_id))
            assert row.encrypted_api_key != plaintext_key
            assert plaintext_key not in row.encrypted_api_key
            assert crypto.decrypt_secret(row.encrypted_api_key) == plaintext_key

    asyncio.run(_check_db())


def test_duplicate_label_rejected():
    _fresh_settings_with_key(TEST_KEY)
    asyncio.run(_reset())
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        headers = _login(client)
        payload = {"label": "dup", "provider": "openai", "api_key": "sk-1"}
        client.post("/api/v1/llm-providers", json=payload, headers=headers)
        r = client.post("/api/v1/llm-providers", json=payload, headers=headers)
        assert r.status_code == 409


def test_test_connection_success_never_returns_the_key():
    _fresh_settings_with_key(TEST_KEY)
    asyncio.run(_reset())
    from fastapi.testclient import TestClient
    from app.main import app

    real_key = "sk-should-never-appear-in-any-response"

    with patch(
        "app.api.llm_providers.llm_provider_service.test_connection",
        new=AsyncMock(return_value={"ok": True, "latency_ms": 123.4, "model_used": "gpt-4o-mini", "error": None}),
    ) as mock_test:
        with TestClient(app) as client:
            headers = _login(client)
            create_resp = client.post(
                "/api/v1/llm-providers",
                json={"label": "test-openai", "provider": "openai", "api_key": real_key},
                headers=headers,
            )
            credential_id = create_resp.json()["id"]

            r = client.post(f"/api/v1/llm-providers/{credential_id}/test-connection", headers=headers)
            assert r.status_code == 200
            assert r.json()["ok"] is True
            assert real_key not in r.text

            # confirm the service actually got called with the real,
            # correctly-decrypted key -- checked here server-side, never
            # exposed over the API
            mock_test.assert_called_once()
            called_base_url, called_api_key, called_model = mock_test.call_args[0]
            assert called_api_key == real_key
            assert called_base_url == "https://api.openai.com/v1"


def test_test_connection_failure_is_reported_not_raised():
    _fresh_settings_with_key(TEST_KEY)
    asyncio.run(_reset())
    from fastapi.testclient import TestClient
    from app.main import app

    with patch(
        "app.api.llm_providers.llm_provider_service.test_connection",
        new=AsyncMock(
            return_value={"ok": False, "latency_ms": 50.0, "model_used": "deepseek-chat", "error": "HTTP 401: invalid key"}
        ),
    ):
        with TestClient(app) as client:
            headers = _login(client)
            create_resp = client.post(
                "/api/v1/llm-providers",
                json={"label": "bad-key", "provider": "deepseek", "api_key": "sk-wrong"},
                headers=headers,
            )
            credential_id = create_resp.json()["id"]

            r = client.post(f"/api/v1/llm-providers/{credential_id}/test-connection", headers=headers)
            assert r.status_code == 200  # the HTTP call to our own API succeeded; the LLM call itself failed
            body = r.json()
            assert body["ok"] is False
            assert "invalid key" in body["error"]


def test_delete_provider():
    _fresh_settings_with_key(TEST_KEY)
    asyncio.run(_reset())
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        headers = _login(client)
        create_resp = client.post(
            "/api/v1/llm-providers",
            json={"label": "to-delete", "provider": "qwen", "api_key": "sk-x"},
            headers=headers,
        )
        credential_id = create_resp.json()["id"]

        r = client.delete(f"/api/v1/llm-providers/{credential_id}", headers=headers)
        assert r.status_code == 204

        listing = client.get("/api/v1/llm-providers", headers=headers).json()
        assert credential_id not in [c["id"] for c in listing]
