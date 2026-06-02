"""recommendations.category + recommendations.effort

Revision ID: 0005_rec_category_effort
Revises: 0004_referrals_llm
Create Date: 2026-06-02

Adds two classification fields used by the recommendation engine:

- ``category`` — which area of the business the rec touches
  (menu / pricing / stock / promotion / staff / operations).
- ``effort``   — rough estimate of how hard it is to apply
  (low / medium / high).

Both are non-null. Existing rows are backfilled with safe defaults
(``operations`` / ``medium``) via ``server_default``.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005_rec_category_effort"
down_revision: str | None = "0004_referrals_llm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    category = sa.Enum(
        "menu", "pricing", "stock", "promotion", "staff", "operations",
        name="recommendation_category",
    )
    effort = sa.Enum("low", "medium", "high", name="recommendation_effort")
    category.create(op.get_bind(), checkfirst=True)
    effort.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "recommendations",
        sa.Column(
            "category",
            sa.Enum(
                "menu", "pricing", "stock", "promotion", "staff", "operations",
                name="recommendation_category", create_type=False,
            ),
            nullable=False,
            server_default="operations",
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "effort",
            sa.Enum("low", "medium", "high", name="recommendation_effort", create_type=False),
            nullable=False,
            server_default="medium",
        ),
    )
    op.create_index(
        "ix_recommendations_category",
        "recommendations",
        ["category"],
    )


def downgrade() -> None:
    op.drop_index("ix_recommendations_category", table_name="recommendations")
    op.drop_column("recommendations", "effort")
    op.drop_column("recommendations", "category")
    op.execute("DROP TYPE IF EXISTS recommendation_effort")
    op.execute("DROP TYPE IF EXISTS recommendation_category")
