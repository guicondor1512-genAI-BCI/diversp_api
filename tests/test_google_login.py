"""Teste do fluxo Google OAuth: login cria/reusa usuário e emite JWT de sessão."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import Text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest_asyncio.fixture
async def client():
    import app.db.session as dbsess

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    TS = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    dbsess.engine = engine
    dbsess.SessionLocal = TS

    import app.models.entities as ent

    ent.Post.__table__.c.search_vector.type = Text()
    ent.Post.__table__.indexes = {
        ix for ix in ent.Post.__table__.indexes if ix.name != "ix_posts_search"
    }

    # Cache em no-op (sem Redis no teste).
    import app.core.cache as cache
    import app.routers.posts as postsmod

    async def _noop(*a, **k):
        return None

    cache.cache_invalidate = _noop
    postsmod.cache_invalidate = _noop

    # Mocka a verificação do id_token do Google.
    import app.routers.auth as authmod
    from app.core.security import GoogleProfile

    def fake_verify(idtok: str) -> GoogleProfile:
        if idtok == "BOM":
            return GoogleProfile(
                sub="g-sub-1", email="maria@gmail.com", name="Maria",
                picture="http://x/p.png",
            )
        raise ValueError("inválido")

    authmod.verify_google_id_token = fake_verify

    from app.db.session import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from fastapi.testclient import TestClient
    from app.main import app

    yield TestClient(app)


def test_invalid_id_token_rejected(client):
    assert client.post("/api/v1/auth/google", json={"id_token": "RUIM"}).status_code == 401


def test_login_creates_user_and_issues_jwt(client):
    r = client.post("/api/v1/auth/google", json={"id_token": "BOM"})
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "bearer" and data["access_token"]
    assert data["handle"] == "@maria"


def test_login_is_idempotent_for_same_sub(client):
    client.post("/api/v1/auth/google", json={"id_token": "BOM"})
    r2 = client.post("/api/v1/auth/google", json={"id_token": "BOM"})
    assert r2.json()["handle"] == "@maria"


def test_issued_jwt_authenticates_protected_route(client):
    tok = client.post("/api/v1/auth/google", json={"id_token": "BOM"}).json()[
        "access_token"
    ]
    r = client.post(
        "/api/v1/posts",
        json={"content": "Oi de SP!"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 201
    assert r.json()["author"]["handle"] == "@maria"
