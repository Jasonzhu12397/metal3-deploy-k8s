from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.llm_provider import LLMProviderKind


class LLMProviderCredentialCreate(BaseModel):
    label: str
    provider: LLMProviderKind
    # Optional -- falls back to DEFAULT_BASE_URLS[provider] for the four
    # known providers; required in practice for CUSTOM (there's no
    # sensible default for "some other OpenAI-compatible endpoint").
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    api_key: str = Field(min_length=1)


class LLMProviderCredentialRead(BaseModel):
    id: uuid.UUID
    label: str
    provider: LLMProviderKind
    base_url: str
    default_model: Optional[str] = None
    # Never the key itself, encrypted or not -- same principle as
    # HardwareAssetRead.has_bmc_credentials. There's no legitimate reason
    # for any API response to carry this value back out.

    class Config:
        from_attributes = True


class LLMProviderTestResult(BaseModel):
    # model_config needed because `model_used` collides with Pydantic's
    # own reserved "model_" attribute namespace otherwise (a real warning,
    # not just cosmetic -- worth silencing correctly rather than renaming
    # a field that reads clearly as-is).
    model_config = ConfigDict(protected_namespaces=())

    ok: bool
    latency_ms: Optional[float] = None
    model_used: Optional[str] = None
    error: Optional[str] = None
