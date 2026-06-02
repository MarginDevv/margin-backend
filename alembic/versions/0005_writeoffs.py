"""writeoffs (списания) for inventory-leak detection

Revision ID: 0005_writeoffs
Revises: 0004_referrals_llm
Create Date: 2026-06-02

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_writeoffs"
down_revision: str | None = "0004_referrals_llm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "writeoffs",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "restaurant_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("iiko_document_id", sa.String(64), nullable=False),
        sa.Column("iiko_document_number", sa.String(32)),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("store_name", sa.String(255)),
        sa.Column("total_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("comment", sa.String(1024)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "restaurant_id", "iiko_document_id", name="uq_writeoff_iiko",
        ),
    )
    op.create_index("ix_writeoffs_restaurant_id", "writeoffs", ["restaurant_id"])
    op.create_index("ix_writeoffs_iiko_document_id", "writeoffs", ["iiko_document_id"])
    op.create_index("ix_writeoffs_occurred_at", "writeoffs", ["occurred_at"])

    op.create_table(
        "writeoff_items",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "writeoff_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("writeoffs.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "menu_item_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_items.id", ondelete="SET NULL"),
        ),
        sa.Column("iiko_product_id", sa.String(64)),
        sa.Column("name_snapshot", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("line_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(255)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_writeoff_items_writeoff_id", "writeoff_items", ["writeoff_id"])
    op.create_index(
        "ix_writeoff_items_menu_item_id", "writeoff_items", ["menu_item_id"],
    )
    op.create_index(
        "ix_writeoff_items_iiko_product_id",
        "writeoff_items", ["iiko_product_id"],
    )


def downgrade() -> None:
    op.drop_table("writeoff_items")
    op.drop_table("writeoffs")
