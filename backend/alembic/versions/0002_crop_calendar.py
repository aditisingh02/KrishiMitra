"""crop calendar: crop_cycles + calendar_tasks

Revision ID: 0002_crop_calendar
Revises: 0001_initial
Create Date: 2026-07-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_crop_calendar"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crop_cycles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("farm_id", sa.String(), nullable=False),
        sa.Column("crop", sa.String(), nullable=False),
        sa.Column("sown_on", sa.String(), nullable=False),  # ISO date
        sa.Column("expected_harvest_on", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_crop_cycles_farm_id", "crop_cycles", ["farm_id"])

    op.create_table(
        "calendar_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("farm_id", sa.String(), nullable=False),
        sa.Column("cycle_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False, server_default="other"),
        sa.Column("due_on", sa.String(), nullable=False),  # ISO date
        sa.Column("done", sa.Integer(), nullable=False, server_default="0"),
        # NULL until a reminder is sent - this is the de-dupe that stops a daily
        # monitor re-reminding the same task every day.
        sa.Column("notified_on", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_calendar_tasks_farm_id", "calendar_tasks", ["farm_id"])
    op.create_index("ix_calendar_tasks_cycle_id", "calendar_tasks", ["cycle_id"])
    op.create_index("ix_calendar_tasks_due_on", "calendar_tasks", ["due_on"])
    # The reminder query: undone + un-notified + due soon, per farm.
    op.create_index(
        "ix_calendar_tasks_reminder_queue",
        "calendar_tasks",
        ["farm_id", "done", "due_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_calendar_tasks_reminder_queue", table_name="calendar_tasks")
    op.drop_index("ix_calendar_tasks_due_on", table_name="calendar_tasks")
    op.drop_index("ix_calendar_tasks_cycle_id", table_name="calendar_tasks")
    op.drop_index("ix_calendar_tasks_farm_id", table_name="calendar_tasks")
    op.drop_table("calendar_tasks")
    op.drop_index("ix_crop_cycles_farm_id", table_name="crop_cycles")
    op.drop_table("crop_cycles")
