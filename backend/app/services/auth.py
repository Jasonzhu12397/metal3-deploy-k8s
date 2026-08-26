"""
Deliberately minimal username/password auth -- a starting point, not a
destination. This is a single flat User table with bcrypt-hashed
passwords and JWT bearer tokens; it doesn't do SSO, MFA, password
rotation policies, or account lockout. Swap it for real SSO (this
platform's own Dex/LDAP, if you're running it) when this stops being
"internal test environment only".

Hashing uses the `bcrypt` package directly rather than passlib's bcrypt
wrapper -- passlib 1.7.4 (its latest release) has a known incompatibility
with bcrypt>=4.1 (it looks for a `bcrypt.__about__.__version__` attribute
that newer bcrypt releases removed, and mishandles the resulting error by
raising instead of falling back), and passlib itself hasn't been updated
since 2020. bcrypt's own API is simple enough not to need the wrapper.
"""
from __future__ import annotations

import logging
import secrets
from typing import Optional

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()

# bcrypt silently ignores input past 72 bytes rather than erroring, which
# would let two different long passwords hash identically -- reject
# instead of truncating.
_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {_MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        # malformed/foreign hash format -- never let this bubble up as a 500
        return False


async def authenticate(db: AsyncSession, username: str, password: str) -> Optional[User]:
    user = await db.scalar(select(User).where(User.username == username))
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def ensure_seed_admin(db: AsyncSession) -> None:
    """Creates the first admin account if the users table is empty. Never
    seeds a fixed/guessable password -- either uses ADMIN_PASSWORD from
    settings, or generates a random one and logs it once so there's
    nothing to look up in source code or documentation."""
    count = await db.scalar(select(func.count()).select_from(User))
    if count:
        return

    password = settings.ADMIN_PASSWORD or secrets.token_urlsafe(18)
    user = User(username=settings.ADMIN_USERNAME, hashed_password=hash_password(password))
    db.add(user)
    await db.commit()

    if settings.ADMIN_PASSWORD:
        logger.warning(
            "Seeded initial admin account '%s' using ADMIN_PASSWORD from settings.",
            settings.ADMIN_USERNAME,
        )
    else:
        logger.warning(
            "=" * 72 + "\n"
            "Seeded initial admin account -- this password is shown ONCE and\n"
            "is not stored anywhere else. Log in and change it immediately via\n"
            "POST /api/v1/auth/change-password, or set ADMIN_PASSWORD in .env\n"
            "before first startup to control it yourself.\n\n"
            "  username: %s\n"
            "  password: %s\n" + "=" * 72,
            settings.ADMIN_USERNAME,
            password,
        )
