"""Ambiente Alembic (async).

Usa a DATABASE_URL da aplicação e o metadata dos modelos para autogerar e
aplicar migrações. Funciona com o driver assíncrono asyncpg.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from app.core.settings import get_settings
from app.db.session import Base
# Importa os modelos para que estejam registrados no metadata.
from app.models import entities  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Injeta a URL real da aplicação (sobrepõe o placeholder do alembic.ini).
# O ConfigParser do Alembic trata "%" como interpolação, então escapamos como
# "%%" — necessário p/ senhas URL-encoded (ex.: "@" -> "%40" no pooler Supabase).
config.set_main_option(
    "sqlalchemy.url", get_settings().database_url.replace("%", "%%")
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"}, compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
