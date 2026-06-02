"""referral codes + referral_payouts

Revision ID: 0004_referrals_llm
Revises: 0003_telegram_activity
Create Date: 2026-06-02

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_referrals_llm"
down_revision: str | None = "0003_telegram_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users.referral_code (public, unique, lazily issued)
    op.add_column(
        "users",
        sa.Column("referral_code", sa.String(16), nullable=True),
    )
    op.create_index(
        "ix_users_referral_code",
        "users",
        ["referral_code"],
        unique=True,
    )

    # restaurants.referrer_user_id — who brought this restaurant in
    op.add_column(
        "restaurants",
        sa.Column(
            "referrer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_restaurants_referrer_user_id",
        "restaurants",
        ["referrer_user_id"],
    )

    payout_status = sa.Enum(
        "pending", "approved", "paid", "reversed",
        name="referral_payout_status",
    )
    payout_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "referral_payouts",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "referrer_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "restaurant_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("invoice_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "commission_rate", sa.Numeric(5, 4),
            nullable=False, server_default="0.1000",
        ),
        sa.Column("commission_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="RUB"),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "approved", "paid", "reversed",
                name="referral_payout_status", create_type=False,
            ),
            nullable=False, server_default="pending",
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.String(512)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_referral_payouts_referrer_user_id",
        "referral_payouts", ["referrer_user_id"],
    )
    op.create_index(
        "ix_referral_payouts_restaurant_id",
        "referral_payouts", ["restaurant_id"],
    )


def downgrade() -> None:
    op.drop_table("referral_payouts")
    op.execute("DROP TYPE IF EXISTS referral_payout_status")
    op.drop_index("ix_restaurants_referrer_user_id", table_name="restaurants")
    op.drop_column("restaurants", "referrer_user_id")
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_column("users", "referral_code")
