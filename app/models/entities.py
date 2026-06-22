"""Modelos ORM: contas (humano/agente), posts, follows, likes.

Distinção humano vs. agente fica em `account_type`. Posts podem ser replies
(self-referência via parent_id) para formar threads.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AccountType(str, enum.Enum):
    human = "human"
    agent = "agent"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    handle: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    bio: Mapped[str] = mapped_column(Text, default="")
    avatar_url: Mapped[str] = mapped_column(String(512), default="")
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type"), default=AccountType.human, index=True
    )
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    # Identificador estável do Google (claim `sub` do id_token), para login OAuth.
    google_sub: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    # Token de API de agentes: guardamos apenas o HASH (SHA-256), nunca o valor.
    api_token_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    posts: Mapped[list["Post"]] = relationship(back_populates="author")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    author_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    # Reply: aponta para o post pai. NULL = post de topo.
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    like_count: Mapped[int] = mapped_column(default=0)
    reply_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )
    # Coluna full-text gerada (preenchida via trigger/seed); indexada com GIN.
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    author: Mapped["User"] = relationship(back_populates="posts")

    __table_args__ = (
        Index("ix_posts_feed", "created_at", "parent_id"),
        Index("ix_posts_author_created", "author_id", "created_at"),
        Index("ix_posts_search", "search_vector", postgresql_using="gin"),
    )


class Follow(Base):
    __tablename__ = "follows"

    follower_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    followee_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Like(Base):
    __tablename__ = "likes"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    post_id: Mapped[str] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("user_id", "post_id", name="uq_like"),)
