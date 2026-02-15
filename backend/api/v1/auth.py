"""User profile endpoints backed by Firebase auth."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.db.models import User
from backend.db.session import get_db
from backend.schemas.user import UserResponse, UserUpdate

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_user_response(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "github_token_set": bool(user.github_token),
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return _to_user_response(current_user)


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
    return _to_user_response(current_user)
