from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import create_access_token, get_current_subject
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, MeResponse, TokenResponse
from app.services.auth import authenticate, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate(db, payload.username, payload.password)
    if not user:
        # Same message either way -- don't reveal whether the username
        # exists.
        raise HTTPException(401, "Invalid username or password")
    token = create_access_token(subject=user.username)
    return TokenResponse(access_token=token, username=user.username)


@router.get("/me", response_model=MeResponse)
async def me(username: str = Depends(get_current_subject)):
    return MeResponse(username=username)


@router.post("/change-password", status_code=204)
async def change_password(
    payload: ChangePasswordRequest,
    username: str = Depends(get_current_subject),
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(select(User).where(User.username == username))
    if not user or not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(401, "Current password is incorrect")
    user.hashed_password = hash_password(payload.new_password)
    await db.commit()
