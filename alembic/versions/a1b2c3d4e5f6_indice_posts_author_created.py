"""indice posts author_created

Adiciona índice composto (author_id, created_at) para acelerar a listagem de
posts de um perfil (filtra por autor, ordena por data).

Revision ID: a1b2c3d4e5f6
Revises: 0cb5d87006c6
Create Date: 2026-06-21 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "0cb5d87006c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_posts_author_created", "posts", ["author_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_posts_author_created", table_name="posts")
