"""drop iiko_integrations.terminal_group_id

Revision ID: 0008_drop_terminal_group_id
Revises: 0007_iiko_orders_revision
Create Date: 2026-06-03

Dead column: nothing in the codebase ever reads it after insert. The REST
API exposed it (POST/PATCH /integrations accepted it, GET returned it)
but no sync path consumed it — the deliveries / nomenclature endpoints
we use take ``organizationIds`` only, not ``terminalGroupId``. The
client method that fetched ``/api/1/terminal_groups`` was never called.

Dropping the column, the corresponding pydantic schema fields and the
client method together in this commit so the audit surface is clean.
If a future feature needs terminal-group routing (stop-list sync,
order creation), re-add explicitly.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008_drop_terminal_group_id"
down_revision: str | None = "0007_iiko_orders_revision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("iiko_integrations", "terminal_group_id")


def downgrade() -> None:
    op.add_column(
        "iiko_integrations",
        sa.Column("terminal_group_id", sa.String(64), nullable=True),
    )
