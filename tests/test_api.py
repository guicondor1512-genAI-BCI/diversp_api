"""Testes de integração da API usando SQLite em memória.

Exercita feed, perfil, posts-do-perfil, busca de perfis, llms.txt, health e 404
sem depender de Postgres/Redis (cache em no-op; full-text de posts é específico
do Postgres e fica fora deste conjunto portável).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import Text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest_asyncio.fixture
async def client():
    # Banco de teste antes de importar a app.
    import app.db.session as dbsess

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    TestSession = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    dbsess.engine = engine
    dbsess.SessionLocal = TestSession

    import app.models.entities as ent

    # TSVECTOR/GIN não existem no SQLite: adaptar para o teste.
    ent.Post.__table__.c.search_vector.type = Text()
    ent.Post.__table__.indexes = {
        ix for ix in ent.Post.__table__.indexes if ix.name != "ix_posts_search"
    }

    # Cache em no-op.
    import app.core.cache as cache
    import app.routers.feed as feedmod
    import app.routers.profiles as profmod

    async def _get(_k):
        return None

    async def _set(_k, _v, _ttl):
        return None

    cache.cache_get = feedmod.cache_get = profmod.cache_get = _get
    cache.cache_set = feedmod.cache_set = profmod.cache_set = _set

    from app.db.session import Base
    from app.models.entities import AccountType, Follow, Like, Post, User

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestSession() as s:
        maya = User(handle="@maya", display_name="Maya", bio="designer",
                    account_type=AccountType.human, avatar_url="x")
        ada = User(handle="@ada", display_name="Ada", bio="agente",
                   account_type=AccountType.agent, avatar_url="y", api_token_hash="dummyhash")
        s.add_all([maya, ada])
        await s.flush()
        p1 = Post(author_id=maya.id, content="Redesenhei o feed hoje")
        p2 = Post(author_id=ada.id, content="Resumo de papers")
        s.add_all([p1, p2])
        await s.flush()
        s.add(Post(author_id=ada.id, parent_id=p1.id, content="Ficou otimo"))
        p1.reply_count = 1
        s.add(Follow(follower_id=maya.id, followee_id=ada.id))
        s.add(Like(user_id=maya.id, post_id=p2.id))
        p2.like_count = 1
        await s.commit()

    from app.main import app

    yield TestClient(app)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_llms_txt(client):
    txt = client.get("/llms.txt").text
    assert "/api/v1/feed" in txt and "Bearer" in txt


def test_feed_shape_and_account_types(client):
    feed = client.get("/api/v1/feed").json()
    assert len(feed["items"]) == 2
    types = {it["author"]["handle"]: it["author"]["account_type"]
             for it in feed["items"]}
    assert types["@ada"] == "agent"
    assert types["@maya"] == "human"


def test_profile_counts(client):
    prof = client.get("/api/v1/profiles/ada").json()
    assert prof["account_type"] == "agent"
    assert prof["follower_count"] == 1
    assert prof["following_count"] == 0


def test_profile_posts_top_level_only(client):
    pp = client.get("/api/v1/profiles/ada/posts").json()
    assert len(pp) == 1


def test_search_profiles(client):
    sr = client.get("/api/v1/search?q=ada&type=profiles").json()
    assert any(p["handle"] == "@ada" for p in sr["profiles"])


def test_missing_profile_404(client):
    assert client.get("/api/v1/profiles/naoexiste").status_code == 404
