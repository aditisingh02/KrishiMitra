"""profiles + multi-farm: profiles table, farms.profile_id/name, backfill

Revision ID: 0003_profiles_multifarm
Revises: 0002_crop_calendar
Create Date: 2026-07-18

Introduces the farmer/profile layer above farms. A profile (one per Clerk user)
owns many farms; the AI operates on the profile's `active_farm_id`.

Migration is designed to be non-destructive: existing farms keep their id (which
equals the Clerk user id), so every events/notifications/memories/calendar row
already keyed to them stays valid. We just:
  1. create `profiles`,
  2. add `profile_id` + `name` to `farms`,
  3. backfill one profile per existing farm and point it at that farm.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_profiles_multifarm"
down_revision: Union[str, None] = "0002_crop_calendar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.String(), primary_key=True),  # Clerk user id
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("default_location", sa.String(), nullable=True),
        sa.Column("active_farm_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index("ix_profiles_phone", "profiles", ["phone"])

    op.add_column("farms", sa.Column("profile_id", sa.String(), nullable=True))
    op.add_column("farms", sa.Column("name", sa.String(), nullable=True))
    op.create_index("ix_farms_profile_id", "farms", ["profile_id"])

    # Backfill: every existing farm was keyed by the Clerk user id, so it becomes
    # that user's first farm and its owning profile.
    op.execute(
        """
        INSERT INTO profiles (id, name, phone, language, default_location, active_farm_id, created_at, updated_at)
        SELECT
            f.id,
            COALESCE(f.data->>'farmer', 'Farmer'),
            f.phone,
            f.language,
            f.data->>'location',
            f.id,
            f.created_at,
            f.updated_at
        FROM farms f
        """
    )
    op.execute("UPDATE farms SET profile_id = id WHERE profile_id IS NULL")
    op.execute(
        """
        UPDATE farms
        SET name = COALESCE(data->>'name', data->>'location', 'My Farm'),
            data = jsonb_set(data, '{profile_id}', to_jsonb(id))
        WHERE name IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_farms_profile_id", table_name="farms")
    op.drop_column("farms", "name")
    op.drop_column("farms", "profile_id")
    op.drop_index("ix_profiles_phone", table_name="profiles")
    op.drop_table("profiles")
