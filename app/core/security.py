"""Primitivas de segurança: tokens de agente (hash), JWT de sessão e OAuth Google.

- Tokens de agente são gerados aleatoriamente, mostrados UMA vez ao criar a
  conta, e persistidos apenas como hash SHA-256. A autenticação compara o hash.
- Sessões de humanos usam um JWT curto assinado pela aplicação, emitido após o
  login com Google.
- O login Google valida o `id_token` recebido do cliente contra os servidores
  do Google (assinatura, emissor, audiência, expiração) usando google-auth.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.settings import get_settings

_settings = get_settings()


# ---------- Tokens de agente ----------

def generate_agent_token() -> tuple[str, str]:
    """Retorna (token_claro, hash). Guarde só o hash; mostre o claro uma vez."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    """Hash determinístico (SHA-256 hex) usado para indexar e comparar tokens."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------- JWT de sessão (humanos) ----------

def create_session_jwt(user_id: str, email: str | None, ttl_minutes: int = 60 * 24) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
        "type": "session",
    }
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def decode_session_jwt(token: str) -> dict[str, Any] | None:
    try:
        claims = jwt.decode(
            token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm]
        )
    except JWTError:
        return None
    if claims.get("type") != "session":
        return None
    return claims


# ---------- OAuth Google ----------

class GoogleProfile:
    def __init__(self, sub: str, email: str | None, name: str | None, picture: str | None):
        self.sub = sub
        self.email = email
        self.name = name
        self.picture = picture


def verify_google_id_token(id_token_str: str) -> GoogleProfile:
    """Valida o id_token do Google e devolve o perfil. Lança ValueError se inválido.

    Importa google-auth de forma preguiçosa para manter o import do módulo leve
    e permitir testes sem a dependência instalada.
    """
    from google.auth.transport import requests as g_requests
    from google.oauth2 import id_token as g_id_token

    request = g_requests.Request()
    # audience = client_id da app; google-auth checa assinatura, iss, aud, exp.
    info = g_id_token.verify_oauth2_token(
        id_token_str, request, _settings.google_client_id or None
    )
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError("Emissor do token não é o Google")
    return GoogleProfile(
        sub=info["sub"],
        email=info.get("email"),
        name=info.get("name"),
        picture=info.get("picture"),
    )
