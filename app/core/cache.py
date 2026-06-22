"""Cache de leituras quentes (feed, perfis, busca) via Redis, com TTL."""
from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis

from app.core.settings import get_settings

_settings = get_settings()
_pool = redis.ConnectionPool.from_url(_settings.redis_url, decode_responses=True)


def _client() -> redis.Redis:
    return redis.Redis(connection_pool=_pool)


async def cache_get(key: str) -> Any | None:
    raw = await _client().get(key)
    return json.loads(raw) if raw else None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    await _client().set(key, json.dumps(value, default=str), ex=ttl)


async def cache_invalidate(*patterns: str) -> None:
    """Invalida chaves por padrão glob (ex.: 'feed:*'). Usado após escritas."""
    client = _client()
    for pattern in patterns:
        async for key in client.scan_iter(match=pattern):
            await client.delete(key)
