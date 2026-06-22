"""Feed: posts de topo, ordem cronológica reversa, paginação por cursor, cacheado."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache_get, cache_set
from app.core.settings import get_settings
from app.db.session import get_session
from app.models.entities import Post
from app.schemas.dto import FeedPage, PostOut

router = APIRouter(prefix="/api/v1", tags=["feed"])
_settings = get_settings()


@router.get("/feed", response_model=FeedPage)
async def get_feed(
    cursor: str | None = Query(default=None, description="ISO timestamp do último item"),
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> FeedPage:
    cache_key = f"feed:{cursor or 'head'}:{limit}"
    if (cached := await cache_get(cache_key)) is not None:
        return FeedPage(**cached)

    # Apenas posts de topo (parent_id IS NULL); eager-load do autor (sem N+1).
    stmt = (
        select(Post)
        .where(Post.parent_id.is_(None))
        .options(selectinload(Post.author))
        .order_by(Post.created_at.desc())
        .limit(limit + 1)
    )
    if cursor:
        stmt = stmt.where(Post.created_at < datetime.fromisoformat(cursor))

    rows = (await session.execute(stmt)).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = rows[-1].created_at.isoformat() if has_more and rows else None
    page = FeedPage(
        items=[PostOut.model_validate(p) for p in rows], next_cursor=next_cursor
    )
    await cache_set(cache_key, page.model_dump(), _settings.cache_ttl_feed)
    return page
