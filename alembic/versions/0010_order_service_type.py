"""orders.service_type + OrderStatus.IN_PROGRESS

Revision ID: 0010_order_service_type
Revises: 0009_iiko_auth_v2
Create Date: 2026-06-03

Two related additions on the orders table:

* New enum value ``in_progress`` on ``order_status`` — iiko's ``Bill``
  status (receipt printed, awaiting payment) used to collapse into
  ``new`` because we had nowhere better to put it. Now surfaced
  distinctly so dashboards can show «awaiting payment» tickets
  separate from brand-new ones.
* New ``service_type`` column with its own enum (``order_service_type``)
  populated from iiko's ``orderServiceType`` field:
    common               — dine-in / table service (the default)
    delivery_by_courier  — courier delivery
    delivery_by_client   — pickup
  Indexed so the dashboard can split «hall vs delivery» revenue
  without re-parsing payloads.

Existing rows get backfilled to ``common`` (the overwhelmingly common
case in practice; rest can be re-synced from iiko if needed).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0010_order_service_type"
down_revision: str | None = "0009_iiko_auth_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Extend the existing order_status enum with the new value.
    #    Postgres requires ALTER TYPE ... ADD VALUE outside a transaction
    #    block; alembic's online runner already commits each migration in
    #    its own tx, but we still need COMMIT before the ALTER and BEGIN
    #    after, hence op.execute("COMMIT"). The behaviour is idempotent
    #    via IF NOT EXISTS so re-runs don't blow up.
    op.execute("COMMIT")
    op.execute("ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'in_progress'")
    op.execute("BEGIN")

    # 2. New service_type enum + column with server_default so existing
    #    rows backfill to the dine-in case.
    service_type = sa.Enum(
        "common", "delivery_by_courier", "delivery_by_client",
        name="order_service_type",
    )
    service_type.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "orders",
        sa.Column(
            "service_type",
            sa.Enum(
                "common", "delivery_by_courier", "delivery_by_client",
                name="order_service_type", create_type=False,
            ),
            nullable=False,
            server_default="common",
        ),
    )
    op.create_index(
        "ix_orders_service_type", "orders", ["service_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_orders_service_type", table_name="orders")
    op.drop_column("orders", "service_type")
    op.execute("DROP TYPE IF EXISTS order_service_type")
    # Note: Postgres has no ALTER TYPE ... DROP VALUE — the `in_progress`
    # enum value stays even on downgrade. Re-adding via upgrade is
    # idempotent (IF NOT EXISTS), so this is safe to live with.
