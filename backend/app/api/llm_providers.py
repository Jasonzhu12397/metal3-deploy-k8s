from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.llm_provider import DEFAULT_BASE_URLS, LLMProviderCredential, LLMProviderKind
from app.schemas.llm_provider import (
    LLMProviderCredentialCreate,
    LLMProviderCredentialRead,
    LLMProviderTestResult,
)
from app.services import crypto
from app.services import llm_provider as llm_provider_service

router = APIRouter(prefix="/llm-providers", tags=["llm-providers"])


@router.get("", response_model=list[LLMProviderCredentialRead])
async def list_providers(db: AsyncSession = Depends(get_db)):
    result = await db.scalars(select(LLMProviderCredential).order_by(LLMProviderCredential.label))
    return result.all()


@router.post("", response_model=LLMProviderCredentialRead, status_code=201)
async def create_provider(payload: LLMProviderCredentialCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(LLMProviderCredential).where(LLMProviderCredential.label == payload.label))
    if existing:
        raise HTTPException(409, f"A provider credential named '{payload.label}' already exists")

    base_url = payload.base_url or DEFAULT_BASE_URLS.get(payload.provider)
    if not base_url:
        raise HTTPException(
            422, f"base_url is required for provider={payload.provider.value} -- no default is known for it"
        )

    try:
        encrypted = crypto.encrypt_secret(payload.api_key)
    except crypto.EncryptionKeyNotConfigured as exc:
        # Unlike BMC credentials (where the Secret write still succeeds
        # and only the local convenience copy is skipped), there's
        # nothing else this credential is good for if it can't be
        # encrypted -- refuse outright rather than silently creating a
        # useless row.
        raise HTTPException(500, str(exc)) from exc

    credential = LLMProviderCredential(
        label=payload.label,
        provider=payload.provider,
        base_url=base_url,
        default_model=payload.default_model,
        encrypted_api_key=encrypted,
    )
    db.add(credential)
    await db.commit()
    await db.refresh(credential)
    return credential


@router.delete("/{credential_id}", status_code=204)
async def delete_provider(credential_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    credential = await db.get(LLMProviderCredential, credential_id)
    if not credential:
        raise HTTPException(404, "Provider credential not found")
    await db.delete(credential)
    await db.commit()


@router.post("/{credential_id}/test-connection", response_model=LLMProviderTestResult)
async def test_provider_connection(credential_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Decrypts the key server-side, fires one real minimal chat-completion
    request, and returns whether it worked -- the key itself never
    appears in the request or response this endpoint returns to the
    caller, only the pass/fail/latency/error-message result."""
    credential = await db.get(LLMProviderCredential, credential_id)
    if not credential:
        raise HTTPException(404, "Provider credential not found")

    try:
        api_key = crypto.decrypt_secret(credential.encrypted_api_key)
    except crypto.EncryptionKeyNotConfigured as exc:
        raise HTTPException(500, str(exc)) from exc
    except crypto.InvalidToken as exc:
        raise HTTPException(
            500,
            "Stored credential could not be decrypted with the configured BMC_ENCRYPTION_KEY "
            "(this same key encrypts both BMC passwords and LLM provider API keys -- it's a "
            "general-purpose credential-encryption key despite the name) -- likely it was "
            "rotated/changed without re-encrypting this row first.",
        ) from exc

    result = await llm_provider_service.test_connection(credential.base_url, api_key, credential.default_model)
    return LLMProviderTestResult(**result)


__all__ = ["router", "LLMProviderKind"]
