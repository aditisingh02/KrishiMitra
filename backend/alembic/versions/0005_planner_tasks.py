"""planner tasks: nullable cycle_id/due_on + source (cycle-less consult tasks)

Revision ID: 0005_planner_tasks
Revises: 0004_interactions
Create Date: 2026-07-18

Additive/metadata-only: lets a calendar task exist without a crop cycle (added
from a consult answer) and without a firm date ("next planting season").
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_planner_tasks"
down_revision: Union[str, None] = "0004_interactions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("calendar_tasks", "cycle_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("calendar_tasks", "due_on", existing_type=sa.String(), nullable=True)
    op.add_column("calendar_tasks", sa.Column("source", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("calendar_tasks", "source")
    # Re-adding NOT NULL fails if any cycle-less / undated rows exist; backfill
    # placeholders first so the downgrade is best-effort rather than crashing.
    op.execute("UPDATE calendar_tasks SET cycle_id = 0 WHERE cycle_id IS NULL")
    op.execute("UPDATE calendar_tasks SET due_on = created_at WHERE due_on IS NULL")
    op.alter_column("calendar_tasks", "due_on", existing_type=sa.String(), nullable=False)
    op.alter_column("calendar_tasks", "cycle_id", existing_type=sa.Integer(), nullable=False)
