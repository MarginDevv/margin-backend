"""telegram + activity feed

Revision ID: 0003_telegram_activity
Revises: 0002_restaurant_hours
Create Date: 2026-06-02

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_telegram_activity"
down_revision: str | None = "0002_restaurant_hours"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users.telegram_chat_id, users.telegram_username
    op.add_column(
        "users",
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("telegram_username", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_users_telegram_chat_id", "users", ["telegram_chat_id"], unique=True
    )

    # per-membership opt-out
    op.add_column(
        "user_restaurant_roles",
        sa.Column(
            "telegram_notifications",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    op.create_table(
        "telegram_link_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_telegram_link_tokens_user_id", "telegram_link_tokens", ["user_id"])
    op.create_index("ix_telegram_link_tokens_token", "telegram_link_tokens", ["token"], unique=True)

    tg_kind = sa.Enum("daily_digest", "weekly_digest", "alert", "system", name="telegram_delivery_kind")
    tg_kind.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "telegram_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Enum("daily_digest", "weekly_digest", "alert", "system", name="telegram_delivery_kind", create_type=False), nullable=False),
        sa.Column("for_date", sa.String(10)),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.String(1024)),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("restaurant_id", "user_id", "kind", "for_date", name="uq_telegram_delivery"),
    )
    op.create_index("ix_telegram_deliveries_restaurant_id", "telegram_deliveries", ["restaurant_id"])
    op.create_index("ix_telegram_deliveries_user_id", "telegram_deliveries", ["user_id"])

    activity_kind = sa.Enum(
        "iiko.sync.success",
        "iiko.sync.failed",
        "report.daily.built",
        "report.weekly.built",
        "recommendations.generated",
        "recommendation.status_changed",
        "telegram.delivery.sent",
        "telegram.delivery.failed",
        "telegram.linked",
        "telegram.unlinked",
        "menu.item.updated",
        name="activity_kind",
    )
    activity_severity = sa.Enum("info", "warning", "error", name="activity_severity")
    activity_kind.create(op.get_bind(), checkfirst=True)
    activity_severity.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "activity_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "kind",
            sa.Enum(
                "iiko.sync.success", "iiko.sync.failed",
                "report.daily.built", "report.weekly.built",
                "recommendations.generated", "recommendation.status_changed",
                "telegram.delivery.sent", "telegram.delivery.failed",
                "telegram.linked", "telegram.unlinked",
                "menu.item.updated",
                name="activity_kind", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("severity", sa.Enum("info", "warning", "error", name="activity_severity", create_type=False), nullable=False, server_default="info"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_activity_events_restaurant_id", "activity_events", ["restaurant_id"])
    op.create_index("ix_activity_events_kind", "activity_events", ["kind"])
    op.create_index(
        "ix_activity_events_restaurant_created",
        "activity_events",
        ["restaurant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("activity_events")
    op.drop_table("telegram_deliveries")
    op.drop_table("telegram_link_tokens")
    op.drop_column("user_restaurant_roles", "telegram_notifications")
    op.drop_index("ix_users_telegram_chat_id", table_name="users")
    op.drop_column("users", "telegram_username")
    op.drop_column("users", "telegram_chat_id")
    for enum_name in ("activity_severity", "activity_kind", "telegram_delivery_kind"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
