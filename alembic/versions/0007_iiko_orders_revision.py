"""iiko_integrations.last_orders_revision

Revision ID: 0007_iiko_orders_revision
Revises: 0006_iiko_menu_revision
Create Date: 2026-06-03

Symmetrical column to ``last_menu_revision``: stores the latest
``maxRevision`` returned by ``/api/1/deliveries/by_revision`` (or
``/api/1/deliveries/by_delivery_date_and_status``, both return it) so the
incremental orders sync can pass it back as ``startRevision`` and pull
only what changed since.

NULL = the integration has never synced orders, so the first run uses
``/api/1/deliveries/by_delivery_date_and_status`` over a 24-hour window
and seeds this field from the response.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007_iiko_orders_revision"
down_revision: str | None = "0006_iiko_menu_revision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "iiko_integrations",
        sa.Column("last_orders_revision", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("iiko_integrations", "last_orders_revision")
