"""User profile endpoints backed by Firebase auth."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.db.models import User, UserOAuthConnection
from backend.db.session import get_db
from backend.schemas.user import UserResponse, UserUpdate

router = APIRouter(prefix="/auth", tags=["auth"])


async def _to_user_response(user: User, db: AsyncSession) -> dict:
    result = await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.user_id == user.id,
            UserOAuthConnection.provider == "openai",
        )
    )
    conn = result.scalar_one_or_none()
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "github_token_set": bool(user.github_token),
        "tier": user.tier,
        "openai_connected": conn is not None and conn.is_valid,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _to_user_response(current_user, db)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.display_name is not None:
        current_user.display_name = data.display_name
    if data.github_token is not None:
        current_user.github_token = data.github_token
    await db.commit()
    await db.refresh(current_user)
    return await _to_user_response(current_user, db)
