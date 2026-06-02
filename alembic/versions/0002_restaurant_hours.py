"""restaurant working hours + report delay

Revision ID: 0002_restaurant_hours
Revises: 0001_initial
Create Date: 2026-06-02

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_restaurant_hours"
down_revision: str | None = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "restaurants",
        sa.Column("working_hours", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "restaurants",
        sa.Column(
            "report_delay_minutes",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
    )


def downgrade() -> None:
    op.drop_column("restaurants", "report_delay_minutes")
    op.drop_column("restaurants", "working_hours")
