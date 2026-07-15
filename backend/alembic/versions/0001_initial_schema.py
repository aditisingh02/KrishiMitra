"""initial schema: farms, events, notifications, memories (+ pgvector)

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

from app.core.config import settings

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "farms",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index("ix_farms_phone", "farms", ["phone"])

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("farm_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detail", JSONB(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_events_farm_id", "events", ["farm_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("farm_id", sa.String(), nullable=False),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_notifications_farm_id", "notifications", ["farm_id"])

    op.create_table(
        "memories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("farm_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(settings.embed_dim), nullable=False),
        sa.Column("meta", JSONB(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_memories_farm_id", "memories", ["farm_id"])
    # HNSW index for fast cosine-distance similarity search.
    op.execute(
        "CREATE INDEX ix_memories_embedding_hnsw ON memories "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.drop_index("ix_memories_embedding_hnsw", table_name="memories")
    op.drop_index("ix_memories_farm_id", table_name="memories")
    op.drop_table("memories")
    op.drop_index("ix_notifications_farm_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_events_farm_id", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_farms_phone", table_name="farms")
    op.drop_table("farms")
