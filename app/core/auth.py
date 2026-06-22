"""Autenticação.

Dois caminhos resolvem para um User:
  - Humanos: JWT de sessão (emitido após login Google), no header Bearer.
  - Agentes: token de API no header Bearer, comparado pelo seu hash SHA-256.

Tokens de agente nunca são guardados em claro — apenas o hash. JWT de humano é
validado por assinatura/expiração.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_session_jwt, hash_token
from app.db.session import get_session
from app.models.entities import User


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais ausentes",
        )
    token = authorization.split(" ", 1)[1].strip()

    # Caminho do agente: compara pelo hash do token.
    digest = hash_token(token)
    res = await session.execute(select(User).where(User.api_token_hash == digest))
    user = res.scalar_one_or_none()
    if user is not None:
        return user

    # Caminho humano: JWT de sessão assinado pela aplicação.
    claims = decode_session_jwt(token)
    if claims is not None:
        res = await session.execute(select(User).where(User.id == claims["sub"]))
        user = res.scalar_one_or_none()
        if user is not None:
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido",
    )


async def optional_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Para rotas de leitura públicas que se enriquecem se houver usuário."""
    if not authorization:
        return None
    try:
        return await get_current_user(authorization, session)
    except HTTPException:
        return None
