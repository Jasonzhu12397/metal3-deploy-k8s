"""
External LLM API provider credentials -- OpenAI/DeepSeek/Qwen(DashScope)/
Doubao(Volcengine Ark), or a custom OpenAI-compatible endpoint. Every one
of these providers speaks the same OpenAI Chat Completions wire format
(same as vLLM's own server, deliberately -- that's what "OpenAI-compatible"
means in practice), so this app only ever needs one client code path
(services/llm_provider.py) regardless of which provider a credential
points at.

Encrypted the same way BMC passwords are (services/crypto.py, Fernet) --
see that module's docstring for why this is a fundamentally different
problem from hashing a login password. The key has to come back out as
plaintext to actually call the provider's API, so hashing is not an
option here either.
"""
from __future__ import annotations

import enum

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class LLMProviderKind(str, enum.Enum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"  # DashScope / 阿里云百炼, OpenAI-compatible mode
    DOUBAO = "doubao"  # Volcengine Ark / 火山方舟, OpenAI-compatible mode
    CUSTOM = "custom"  # any other OpenAI-compatible endpoint (self-hosted vLLM elsewhere, a proxy, etc.)


# Real, verified base URLs (checked 2026-08-31 -- these do drift; Qwen in
# particular has multiple regional endpoints, this is just the Beijing
# one) so a user picking a known provider doesn't have to go find their
# own base_url. CUSTOM has no default -- the caller must supply one.
DEFAULT_BASE_URLS: dict[LLMProviderKind, str] = {
    LLMProviderKind.OPENAI: "https://api.openai.com/v1",
    LLMProviderKind.DEEPSEEK: "https://api.deepseek.com/v1",
    LLMProviderKind.QWEN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    LLMProviderKind.DOUBAO: "https://ark.cn-beijing.volces.com/api/v3",
}


class LLMProviderCredential(TimestampedModel):
    __tablename__ = "llm_provider_credentials"

    # User-given nickname, not the provider name itself -- you might have
    # two OpenAI keys (personal + team billing), so this has to be
    # distinguishable from `provider`.
    label: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider: Mapped[LLMProviderKind] = mapped_column(Enum(LLMProviderKind))
    base_url: Mapped[str] = mapped_column(String(255))
    # What to use for the test-connection call and as a sensible default
    # elsewhere -- not a hard restriction on which models this key can
    # call (most providers' keys can call any model in their catalog).
    default_model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    encrypted_api_key: Mapped[str] = mapped_column(String(512))
