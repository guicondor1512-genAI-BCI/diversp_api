"""Testes de segurança: hash de token de agente e JWT de sessão."""
from app.core.security import (
    create_session_jwt,
    decode_session_jwt,
    generate_agent_token,
    hash_token,
)


def test_agent_token_hash():
    raw, digest = generate_agent_token()
    assert raw != digest and len(digest) == 64
    assert hash_token(raw) == digest
    assert hash_token("outro") != digest


def test_session_jwt_roundtrip():
    tok = create_session_jwt("user-123", "a@b.com")
    claims = decode_session_jwt(tok)
    assert claims and claims["sub"] == "user-123" and claims["type"] == "session"
    assert decode_session_jwt(tok + "x") is None
