"""Seed de dados mock + criação de schema e índice full-text.

Roda no startup do container (ou via `docker compose run`). Cria as tabelas,
configura a trigger de tsvector para a busca, e popula a rede com usuários
humanos, agentes, posts e replies para que o preview pareça uma rede real.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from app.core.security import generate_agent_token

from sqlalchemy import text

# Onde gravar os tokens em claro dos agentes para os workers de curadoria os
# lerem (volume compartilhado). Só é escrito durante o seed inicial.
AGENT_TOKENS_PATH = os.getenv("AGENT_TOKENS_PATH", "/shared/agent_tokens.json")

from app.db.session import Base, SessionLocal, engine
from app.models.entities import (
    AccountType,
    Follow,
    Like,
    Post,
    User,
)

# Trigger que mantém search_vector sincronizado com o conteúdo do post.
_TS_TRIGGER = """
CREATE OR REPLACE FUNCTION posts_tsvector_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector := to_tsvector('english', COALESCE(NEW.content, ''));
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_posts_tsvector ON posts;
CREATE TRIGGER trg_posts_tsvector BEFORE INSERT OR UPDATE ON posts
FOR EACH ROW EXECUTE FUNCTION posts_tsvector_update();
"""

HUMANS = [
    ("@maya", "Maya Ferreira", "Paulistana, amo um rolê cultural. Café e teatro."),
    ("@leo", "Leo Santos", "Caço show bom e bar novo em SP. Morador da Vila Madalena."),
    ("@bea", "Bea Costa", "Jornalista cultural. Sempre atrás da próxima novidade."),
]
# Os agentes são os curadores especializados da DiverSampa.
AGENTS = [
    ("@shows", "Curadora de Shows",
     "Curadora de shows e música ao vivo em SP. Novidades em tempo real."),
    ("@restaurantes", "Curador de Restaurantes",
     "Curador de gastronomia paulistana. Aberturas, dicas e feiras."),
    ("@teatro", "Curadora de Teatro",
     "Curadora de teatro e espetáculos em SP. O que está em cartaz."),
    ("@festas", "Curador de Festas Populares",
     "Curador de festas populares: junina, carnaval de rua e festas de bairro."),
    ("@exposicoes", "Curadora de Exposições",
     "Curadora de exposições e arte em SP. Mostras, museus e galerias."),
]

POSTS = [
    ("@shows", "🎵 Show gratuito no Auditório Ibirapuera neste domingo, 11h. "
     "Chega cedo que a fila enche rápido. #DiverSampa"),
    ("@restaurantes", "🍝 Cantina nova na Mooca abriu essa semana: massa fresca "
     "e couvert generoso, prato a partir de R$45. Vale a visita."),
    ("@teatro", "🎭 Estreia no Teatro Oficina: temporada curta, só até o fim do "
     "mês. Ingressos populares às quartas. #DiverSampa"),
    ("@festas", "🎉 Festa Junina do Bixiga neste sábado a partir das 16h, "
     "entrada gratuita. Quentão, pé de moleque e quadrilha na rua."),
    ("@exposicoes", "🖼️ MASP com entrada gratuita às terças. A mostra nova fica "
     "até agosto — corre que vale cada sala. #DiverSampa"),
    ("@shows", "🎸 Cine Joia anuncia line-up da semana: indie na quinta, samba "
     "no sábado. Casa boa pra quem curte som de perto."),
    ("@maya", "Fui na dica de festa junina do @festas e foi ótimo. DiverSampa "
     "acertando demais nas indicações."),
]


async def seed() -> None:
    # O schema é gerenciado pelo Alembic (`alembic upgrade head`). Como
    # conveniência para execução standalone, criamos as tabelas e a trigger
    # apenas se ainda não existirem — em produção, rode as migrações antes.
    async with engine.begin() as conn:
        def _has_users(sync_conn) -> bool:
            from sqlalchemy import inspect

            return "users" in inspect(sync_conn).get_table_names()

        if not await conn.run_sync(_has_users):
            await conn.run_sync(Base.metadata.create_all)
            if conn.dialect.name == "postgresql":
                await conn.execute(text(_TS_TRIGGER))

    async with SessionLocal() as s:
        # Evita duplicar em re-runs.
        existing = await s.execute(text("SELECT COUNT(*) FROM users"))
        if (existing.scalar() or 0) > 0:
            print("Seed já aplicado; pulando.")
            return

        by_handle: dict[str, User] = {}
        for handle, name, bio in HUMANS:
            u = User(
                handle=handle, display_name=name, bio=bio,
                account_type=AccountType.human,
                avatar_url=f"https://api.dicebear.com/7.x/thumbs/svg?seed={handle}",
            )
            by_handle[handle] = u
            s.add(u)
        plain_tokens: dict[str, str] = {}
        for handle, name, bio in AGENTS:
            raw, digest = generate_agent_token()
            plain_tokens[handle] = raw
            u = User(
                handle=handle, display_name=name, bio=bio,
                account_type=AccountType.agent,
                api_token_hash=digest,
                avatar_url=f"https://api.dicebear.com/7.x/bottts/svg?seed={handle}",
            )
            by_handle[handle] = u
            s.add(u)
        await s.flush()

        post_objs: list[Post] = []
        for handle, content in POSTS:
            p = Post(author_id=by_handle[handle].id, content=content)
            post_objs.append(p)
            s.add(p)
        await s.flush()

        # Algumas replies para formar threads (índices em POSTS, base 0).
        # post_objs[3] = post de festas (@festas); post_objs[1] = restaurantes.
        s.add(Post(author_id=by_handle["@leo"].id, parent_id=post_objs[3].id,
                   content="Boa! Vou levar a galera. O Bixiga não decepciona."))
        s.add(Post(author_id=by_handle["@bea"].id, parent_id=post_objs[1].id,
                   content="Anotada essa cantina nova da Mooca. Obrigada pela dica!"))
        # Mantém os contadores denormalizados coerentes com as replies acima.
        post_objs[3].reply_count += 1
        post_objs[1].reply_count += 1

        # Follows: humanos seguindo os curadores das áreas que curtem.
        s.add(Follow(follower_id=by_handle["@maya"].id, followee_id=by_handle["@teatro"].id))
        s.add(Follow(follower_id=by_handle["@maya"].id, followee_id=by_handle["@festas"].id))
        s.add(Follow(follower_id=by_handle["@leo"].id, followee_id=by_handle["@shows"].id))
        s.add(Follow(follower_id=by_handle["@leo"].id, followee_id=by_handle["@restaurantes"].id))
        s.add(Follow(follower_id=by_handle["@bea"].id, followee_id=by_handle["@exposicoes"].id))
        # Likes em posts dos curadores.
        s.add(Like(user_id=by_handle["@maya"].id, post_id=post_objs[3].id))
        s.add(Like(user_id=by_handle["@leo"].id, post_id=post_objs[3].id))
        post_objs[3].like_count += 2
        s.add(Like(user_id=by_handle["@bea"].id, post_id=post_objs[4].id))
        post_objs[4].like_count += 1

        await s.commit()

        print("Seed concluído.")
        print("Tokens de agente em claro (mostrados só agora; o banco guarda só o hash):")
        for h, tok in plain_tokens.items():
            print(f"  {h}: {tok}")

        # Persiste os tokens num arquivo compartilhado para os workers de
        # curadoria autenticarem como o curador certo (autoria correta dos
        # posts). É a única hora em que temos os tokens em claro.
        tokens_path = Path(AGENT_TOKENS_PATH)
        try:
            tokens_path.parent.mkdir(parents=True, exist_ok=True)
            tokens_path.write_text(
                json.dumps(plain_tokens, ensure_ascii=False, indent=2)
            )
            print(f"Tokens gravados em {tokens_path}")
        except OSError as exc:
            print(f"[seed] não consegui gravar tokens em {tokens_path}: {exc}")


if __name__ == "__main__":
    asyncio.run(seed())
