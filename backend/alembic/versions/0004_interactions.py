"""chat history: interactions (consult / diagnose) per farm

Revision ID: 0004_interactions
Revises: 0003_profiles_multifarm
Create Date: 2026-07-18

Full, displayable conversation history - separate from `events` (short activity
summaries that feed prompts) and `memories` (pgvector recall). Purely additive.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004_interactions"
down_revision: Union[str, None] = "0003_profiles_multifarm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("farm_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),  # consult | diagnose
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answer_en", sa.Text(), nullable=True),
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("blocked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_interactions_farm_id", "interactions", ["farm_id"])
    op.create_index("ix_interactions_farm_kind", "interactions", ["farm_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_interactions_farm_kind", table_name="interactions")
    op.drop_index("ix_interactions_farm_id", table_name="interactions")
    op.drop_table("interactions")
