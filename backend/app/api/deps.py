from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db

DbDep = AsyncGenerator[AsyncSession, None]

__all__ = ["get_db"]
