"""Perfis públicos: avatar, bio, histórico, contagens de seguidores."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache_get, cache_set
from app.core.settings import get_settings
from app.db.session import get_session
from app.models.entities import Follow, Post, User
from app.schemas.dto import PostOut, ProfileOut

router = APIRouter(prefix="/api/v1", tags=["profiles"])
_settings = get_settings()


def _normalize(handle: str) -> str:
    return handle if handle.startswith("@") else f"@{handle}"


@router.get("/profiles/{handle}", response_model=ProfileOut)
async def get_profile(
    handle: str, session: AsyncSession = Depends(get_session)
) -> ProfileOut:
    handle = _normalize(handle)
    cache_key = f"profile:{handle}"
    if (cached := await cache_get(cache_key)) is not None:
        return ProfileOut(**cached)

    user = (
        await session.execute(select(User).where(User.handle == handle))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    followers = await session.scalar(
        select(func.count()).select_from(Follow).where(Follow.followee_id == user.id)
    )
    following = await session.scalar(
        select(func.count()).select_from(Follow).where(Follow.follower_id == user.id)
    )
    out = ProfileOut.model_validate(user)
    out.follower_count = followers or 0
    out.following_count = following or 0
    await cache_set(cache_key, out.model_dump(), _settings.cache_ttl_profile)
    return out


@router.get("/profiles/{handle}/posts", response_model=list[PostOut])
async def get_profile_posts(
    handle: str, session: AsyncSession = Depends(get_session)
) -> list[PostOut]:
    handle = _normalize(handle)
    user = (
        await session.execute(select(User).where(User.handle == handle))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    stmt = (
        select(Post)
        .where(Post.author_id == user.id, Post.parent_id.is_(None))
        .options(selectinload(Post.author))
        .order_by(Post.created_at.desc())
        .limit(50)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [PostOut.model_validate(p) for p in rows]
