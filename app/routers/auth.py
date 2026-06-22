"""Rotas de autenticação.

Fluxo Google OAuth (lado servidor):
  1. O cliente faz login com Google e obtém um `id_token` (JWT do Google).
  2. Envia esse id_token para POST /api/v1/auth/google.
  3. O servidor valida o id_token contra o Google, cria/atualiza o usuário e
     devolve um JWT de sessão da própria aplicação, usado nas chamadas seguintes.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_session_jwt, verify_google_id_token
from app.db.session import get_session
from app.models.entities import AccountType, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class GoogleLogin(BaseModel):
    id_token: str


class SessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    handle: str
    display_name: str


def _handle_from_email(email: str | None, sub: str) -> str:
    base = (email.split("@")[0] if email else f"user{sub[:6]}").lower()
    base = re.sub(r"[^a-z0-9_]+", "", base) or f"user{sub[:6]}"
    return f"@{base}"


@router.post("/google", response_model=SessionOut)
async def login_google(
    body: GoogleLogin, session: AsyncSession = Depends(get_session)
) -> SessionOut:
    try:
        profile = verify_google_id_token(body.id_token)
    except Exception as exc:  # google-auth lança ValueError/GoogleAuthError
        # Log server-side do motivo real (não exposto ao cliente) para diagnóstico.
        logger.warning("login_google: id_token rejeitado: %s: %s",
                       type(exc).__name__, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="id_token do Google inválido",
        )

    # Procura usuário existente por google_sub e, em fallback, por email.
    user = (
        await session.execute(select(User).where(User.google_sub == profile.sub))
    ).scalar_one_or_none()
    if user is None and profile.email:
        user = (
            await session.execute(select(User).where(User.email == profile.email))
        ).scalar_one_or_none()

    if user is None:
        # Cria conta humana nova a partir do perfil Google.
        handle = _handle_from_email(profile.email, profile.sub)
        # Garante unicidade do handle.
        suffix = 0
        base_handle = handle
        while (
            await session.execute(select(User).where(User.handle == handle))
        ).scalar_one_or_none() is not None:
            suffix += 1
            handle = f"{base_handle}{suffix}"
        user = User(
            handle=handle,
            display_name=profile.name or handle.lstrip("@"),
            avatar_url=profile.picture or "",
            account_type=AccountType.human,
            email=profile.email,
            google_sub=profile.sub,
        )
        session.add(user)
    else:
        # Mantém google_sub e avatar atualizados.
        user.google_sub = profile.sub
        if profile.picture:
            user.avatar_url = profile.picture
    await session.commit()
    await session.refresh(user)

    jwt_token = create_session_jwt(user.id, user.email)
    return SessionOut(
        access_token=jwt_token,
        handle=user.handle,
        display_name=user.display_name,
    )
