"""faz4_pgvector_vector_column

Revision ID: b2c3d4e5f6a7b
Revises: a1b2c3d4e5f6
Create Date: 2026-08-25

Faz4: pgvector vector sütunu ekle — iddia kaldırma yerine gerçekleştirme.
memory_items.embedding_vector Vector(1536) eklenir; pgvector extension zaten initdb'de var.
"""
from typing import Union
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7b'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # extension zaten 01-init.sql'de ama migration idempotent olsun
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # embedding_vector Vector(1536) — pgvector yoksa fallback olarak JSONB de çalışır ama biz Vector deneriz
    # SQLAlchemy import'u olmadan ham SQL ile oluştur
    # pgvector kuruluysa Vector tipi mevcuttur
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='memory_items' AND column_name='embedding_vector'
            ) THEN
                ALTER TABLE memory_items ADD COLUMN embedding_vector vector(1536);
            END IF;
        END $$;
    """)
    # HNSW/IVFFLAT index — cosine için; veri yokken bile oluşturulabilir
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_memory_embedding_vector
        ON memory_items USING hnsw (embedding_vector vector_cosine_ops);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memory_embedding_vector;")
    op.execute("ALTER TABLE memory_items DROP COLUMN IF EXISTS embedding_vector;")
