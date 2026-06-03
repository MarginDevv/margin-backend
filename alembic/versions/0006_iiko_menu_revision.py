"""iiko_integrations.last_menu_revision

Revision ID: 0006_iiko_menu_revision
Revises: 0005_rec_category_effort
Create Date: 2026-06-03

Adds a single nullable BIGINT column to remember the last ``revision``
value returned by ``POST /api/1/nomenclature``. The sync service passes it
back as ``startRevision`` so iiko only returns the delta (or an empty
payload when nothing has changed).

NULL = the integration has never synced the menu, so the next request
must use ``startRevision = 0`` (the documented value for the first call).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006_iiko_menu_revision"
down_revision: str | None = "0005_rec_category_effort"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "iiko_integrations",
        sa.Column("last_menu_revision", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("iiko_integrations", "last_menu_revision")
