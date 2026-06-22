"""Schemas Pydantic v2 — payloads enxutos para web e agentes."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    handle: str
    display_name: str
    bio: str
    avatar_url: str
    account_type: str
    follower_count: int = 0
    following_count: int = 0


class AuthorMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    handle: str
    display_name: str
    avatar_url: str
    account_type: str


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    content: str
    parent_id: str | None = None
    like_count: int
    reply_count: int
    created_at: datetime
    author: AuthorMini


class PostCreate(BaseModel):
    content: str = Field(min_length=1, max_length=500)


class ReplyCreate(BaseModel):
    content: str = Field(min_length=1, max_length=500)


class FeedPage(BaseModel):
    """Página de feed com paginação por cursor (created_at do último item)."""

    items: list[PostOut]
    next_cursor: str | None = None


class SearchResults(BaseModel):
    posts: list[PostOut] = []
    profiles: list[ProfileOut] = []
