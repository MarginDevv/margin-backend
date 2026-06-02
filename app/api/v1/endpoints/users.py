"""User self-service endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.core.exceptions import AuthenticationError
from app.core.security import hash_password, verify_password
from app.schemas.user import PasswordChange, UserRead, UserUpdate

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def get_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me", response_model=UserRead)
async def update_me(payload: UserUpdate, user: CurrentUser, session: DbSession) -> UserRead:
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.phone is not None:
        user.phone = payload.phone
    await session.commit()
    await session.refresh(user)
    return UserRead.model_validate(user)


@router.post("/me/password", status_code=204)
async def change_password(
    payload: PasswordChange, user: CurrentUser, session: DbSession
) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise AuthenticationError("Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    await session.commit()
