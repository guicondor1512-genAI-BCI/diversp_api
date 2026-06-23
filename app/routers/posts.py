"""Posts e replies. Escritas invalidam o cache de feed."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import get_current_user
from app.core.cache import cache_invalidate
from app.db.session import get_session
from app.models.entities import Like, Post, User
from app.schemas.dto import PostCreate, PostOut, ReplyCreate

router = APIRouter(prefix="/api/v1", tags=["posts"])


async def _load_with_author(session: AsyncSession, post_id: str) -> Post:
    stmt = (
        select(Post).where(Post.id == post_id).options(selectinload(Post.author))
    )
    post = (await session.execute(stmt)).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post não encontrado")
    return post


@router.post("/posts", response_model=PostOut, status_code=201)
async def create_post(
    body: PostCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PostOut:
    post = Post(author_id=user.id, content=body.content)
    session.add(post)
    await session.commit()
    await cache_invalidate("feed:*")
    return PostOut.model_validate(await _load_with_author(session, post.id))


@router.get("/posts/{post_id}", response_model=PostOut)
async def get_post(
    post_id: str, session: AsyncSession = Depends(get_session)
) -> PostOut:
    return PostOut.model_validate(await _load_with_author(session, post_id))


@router.get("/posts/{post_id}/replies", response_model=list[PostOut])
async def list_replies(
    post_id: str, session: AsyncSession = Depends(get_session)
) -> list[PostOut]:
    stmt = (
        select(Post)
        .where(Post.parent_id == post_id)
        .options(selectinload(Post.author))
        .order_by(Post.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [PostOut.model_validate(p) for p in rows]


@router.post("/posts/{post_id}/replies", response_model=PostOut, status_code=201)
async def create_reply(
    post_id: str,
    body: ReplyCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PostOut:
    await _load_with_author(session, post_id)  # garante que o pai existe
    reply = Post(author_id=user.id, content=body.content, parent_id=post_id)
    session.add(reply)
    await session.execute(
        update(Post)
        .where(Post.id == post_id)
        .values(reply_count=Post.reply_count + 1)
    )
    await session.commit()
    await cache_invalidate("feed:*")
    return PostOut.model_validate(await _load_with_author(session, reply.id))


async def _like_count(session: AsyncSession, post_id: str) -> int:
    return (
        await session.execute(select(Post.like_count).where(Post.id == post_id))
    ).scalar_one()


@router.post("/posts/{post_id}/likes")
async def like_post(
    post_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Curte um post (idempotente). Retorna {liked, like_count}."""
    await _load_with_author(session, post_id)  # 404 se o post não existir
    already = (
        await session.execute(
            select(Like).where(Like.user_id == user.id, Like.post_id == post_id)
        )
    ).scalar_one_or_none()
    if already is None:
        session.add(Like(user_id=user.id, post_id=post_id))
        await session.execute(
            update(Post).where(Post.id == post_id).values(like_count=Post.like_count + 1)
        )
        await session.commit()
        await cache_invalidate("feed:*")
    return {"liked": True, "like_count": await _like_count(session, post_id)}


@router.delete("/posts/{post_id}/likes")
async def unlike_post(
    post_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Descurte um post (idempotente). Retorna {liked, like_count}."""
    await _load_with_author(session, post_id)
    already = (
        await session.execute(
            select(Like).where(Like.user_id == user.id, Like.post_id == post_id)
        )
    ).scalar_one_or_none()
    if already is not None:
        await session.execute(
            delete(Like).where(Like.user_id == user.id, Like.post_id == post_id)
        )
        await session.execute(
            update(Post)
            .where(Post.id == post_id, Post.like_count > 0)
            .values(like_count=Post.like_count - 1)
        )
        await session.commit()
        await cache_invalidate("feed:*")
    return {"liked": False, "like_count": await _like_count(session, post_id)}
