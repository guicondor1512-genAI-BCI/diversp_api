"""Busca full-text em posts e perfis usando o índice GIN do Postgres."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.entities import Post, User
from app.schemas.dto import PostOut, ProfileOut, SearchResults

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.get("/search", response_model=SearchResults)
async def search(
    q: str = Query(min_length=1),
    type: str = Query(default="posts", pattern="^(posts|profiles|all)$"),
    session: AsyncSession = Depends(get_session),
) -> SearchResults:
    results = SearchResults()

    if type in ("posts", "all"):
        ts_query = func.plainto_tsquery("english", q)
        stmt = (
            select(Post)
            .where(Post.search_vector.op("@@")(ts_query))
            .options(selectinload(Post.author))
            .order_by(Post.created_at.desc())
            .limit(25)
        )
        rows = (await session.execute(stmt)).scalars().all()
        results.posts = [PostOut.model_validate(p) for p in rows]

    if type in ("profiles", "all"):
        like = f"%{q}%"
        stmt = (
            select(User)
            .where(or_(User.handle.ilike(like), User.display_name.ilike(like)))
            .limit(25)
        )
        rows = (await session.execute(stmt)).scalars().all()
        results.profiles = [ProfileOut.model_validate(u) for u in rows]

    return results
