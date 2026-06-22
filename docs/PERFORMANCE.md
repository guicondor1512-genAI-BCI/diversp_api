# Performance — orçamentos e ajustes

## Orçamentos de latência (p95)

| Endpoint | Com cache | Sem cache |
|---|---|---|
| `/api/v1/feed` | < 200 ms | < 500 ms |
| `/api/v1/profiles/{handle}` | < 200 ms | < 500 ms |
| `/api/v1/search` | < 300 ms | < 500 ms |

## Como medir

Com a API rodando (de preferência contra Postgres + Redis reais):

```bash
python -m app.benchmark --base-url http://localhost:8000 --requests 500 --concurrency 32
```

O script mede p50/p95/p99 de feed, perfil e busca, aquece o cache antes de medir
e compara contra os orçamentos acima (sai com código !=0 se algo ficar fora).

Medição de referência (SQLite em memória, sem cache real — pior caso de I/O
serializado): feed p95 ~100 ms, perfil ~40 ms, busca ~55 ms. Com Postgres +
Redis e cache quente, espera-se ficar bem abaixo.

## Ajustes aplicados

**Cache (Redis, com TTL e invalidação na escrita):**
- `feed:*` — TTL `CACHE_TTL_FEED` (30 s); invalidado ao criar post/reply.
- `profile:*` — TTL `CACHE_TTL_PROFILE` (60 s).

**Índices (criados via migrações Alembic):**
- `ix_posts_feed (created_at, parent_id)` — feed cronológico de posts de topo.
- `ix_posts_author_created (author_id, created_at)` — listagem de posts de um
  perfil (filtra por autor, ordena por data).
- `ix_posts_search (search_vector, GIN)` — busca full-text (Postgres).
- Índices em `users.handle`, `users.google_sub`, `users.api_token_hash`.

**Consultas:**
- Paginação por cursor no feed (evita offsets caros).
- `selectinload(Post.author)` evita o problema de N+1.

## Próximos passos de tuning

- Ajustar `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` à concorrência real do deploy.
- Considerar cache de resultados de busca populares com TTL curto.
- Revisar planos de consulta (`EXPLAIN ANALYZE`) sob dados de produção.
