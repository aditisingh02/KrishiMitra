"""price snapshots: daily mandi price history (day-over-day market trend)

Revision ID: 0006_price_history
Revises: 0005_planner_tasks
Create Date: 2026-07-19

Agmarknet's daily API only returns *today's* prices, so we persist one snapshot
per (commodity, region, day) on every fetch to accumulate a real time series -
the day-over-day trend the market page shows. Global, not per-farm: mandi prices
are public and shared, keyed by region ("ALL" = all-India).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_price_history"
down_revision: Union[str, None] = "0005_planner_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("commodity", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False, server_default="ALL"),
        sa.Column("date", sa.String(), nullable=False),
        sa.Column("modal", sa.Integer(), nullable=False),
        sa.Column("low", sa.Integer(), nullable=False),
        sa.Column("high", sa.Integer(), nullable=False),
        sa.Column("markets", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_price_snapshots_commodity", "price_snapshots", ["commodity"])
    op.create_index(
        "ix_price_snapshots_lookup",
        "price_snapshots",
        ["commodity", "state", "date"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_price_snapshots_lookup", table_name="price_snapshots")
    op.drop_index("ix_price_snapshots_commodity", table_name="price_snapshots")
    op.drop_table("price_snapshots")
