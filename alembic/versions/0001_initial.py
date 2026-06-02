"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-02

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("phone", sa.String(32)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "restaurants",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("legal_name", sa.String(255)),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/Moscow"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="RUB"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    user_role = sa.Enum("owner", "manager", "staff", name="user_role")
    user_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "user_restaurant_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Enum("owner", "manager", "staff", name="user_role", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "restaurant_id", name="uq_user_restaurant"),
    )
    op.create_index("ix_user_restaurant_roles_user_id", "user_restaurant_roles", ["user_id"])
    op.create_index("ix_user_restaurant_roles_restaurant_id", "user_restaurant_roles", ["restaurant_id"])

    sub_plan = sa.Enum("free_trial", "starter", "pro", "enterprise", name="subscription_plan")
    sub_status = sa.Enum("trial", "active", "past_due", "canceled", "expired", name="subscription_status")
    sub_plan.create(op.get_bind(), checkfirst=True)
    sub_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("plan", sa.Enum("free_trial", "starter", "pro", "enterprise", name="subscription_plan", create_type=False), nullable=False, server_default="free_trial"),
        sa.Column("status", sa.Enum("trial", "active", "past_due", "canceled", "expired", name="subscription_status", create_type=False), nullable=False, server_default="trial"),
        sa.Column("price", sa.Numeric(12, 2)),
        sa.Column("current_period_start", sa.DateTime(timezone=True)),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("canceled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "iiko_integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("api_login", sa.String(255), nullable=False),
        sa.Column("organization_id", sa.String(64), index=True),
        sa.Column("terminal_group_id", sa.String(64)),
        sa.Column("access_token", sa.String(512)),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_sync_error", sa.String(1024)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "menu_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("iiko_product_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(255)),
        sa.Column("unit", sa.String(32)),
        sa.Column("sale_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("food_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_rate", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("restaurant_id", "iiko_product_id", name="uq_menu_item_iiko"),
    )
    op.create_index("ix_menu_items_restaurant_id", "menu_items", ["restaurant_id"])
    op.create_index("ix_menu_items_iiko_product_id", "menu_items", ["iiko_product_id"])
    op.create_index("ix_menu_items_category", "menu_items", ["category"])

    order_status = sa.Enum("new", "closed", "canceled", "deleted", name="order_status")
    order_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("iiko_order_id", sa.String(64), nullable=False),
        sa.Column("iiko_order_number", sa.String(32)),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Enum("new", "closed", "canceled", "deleted", name="order_status", create_type=False), nullable=False, server_default="new"),
        sa.Column("guests_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("waiter_name", sa.String(128)),
        sa.Column("gross_revenue", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("net_revenue", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_food_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("profit", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("restaurant_id", "iiko_order_id", name="uq_order_iiko"),
    )
    op.create_index("ix_orders_restaurant_id", "orders", ["restaurant_id"])
    op.create_index("ix_orders_opened_at", "orders", ["opened_at"])
    op.create_index("ix_orders_closed_at", "orders", ["closed_at"])
    op.create_index(
        "ix_orders_restaurant_closed",
        "orders",
        ["restaurant_id", "closed_at"],
    )

    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("menu_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("menu_items.id", ondelete="SET NULL")),
        sa.Column("iiko_product_id", sa.String(64)),
        sa.Column("name_snapshot", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("unit_food_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("line_revenue", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("line_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("line_profit", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_menu_item_id", "order_items", ["menu_item_id"])
    op.create_index("ix_order_items_iiko_product_id", "order_items", ["iiko_product_id"])

    rec_type = sa.Enum(
        "price_up", "price_down", "cost_reduce", "remove_dish", "promote_dish",
        "inventory_leak", "staff_performance", "day_of_week",
        name="recommendation_type",
    )
    rec_prio = sa.Enum("low", "medium", "high", "critical", name="recommendation_priority")
    rec_status = sa.Enum("new", "seen", "accepted", "rejected", "applied", name="recommendation_status")
    rec_type.create(op.get_bind(), checkfirst=True)
    rec_prio.create(op.get_bind(), checkfirst=True)
    rec_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("type", sa.Enum(
            "price_up", "price_down", "cost_reduce", "remove_dish", "promote_dish",
            "inventory_leak", "staff_performance", "day_of_week",
            name="recommendation_type", create_type=False,
        ), nullable=False),
        sa.Column("priority", sa.Enum("low", "medium", "high", "critical", name="recommendation_priority", create_type=False), nullable=False, server_default="medium"),
        sa.Column("status", sa.Enum("new", "seen", "accepted", "rejected", "applied", name="recommendation_status", create_type=False), nullable=False, server_default="new"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("action", sa.Text()),
        sa.Column("estimated_uplift", sa.Numeric(14, 2)),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_recommendations_restaurant_id", "recommendations", ["restaurant_id"])
    op.create_index("ix_recommendations_for_date", "recommendations", ["for_date"])

    rep_period = sa.Enum("daily", "weekly", "monthly", name="report_period")
    rep_period.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.Enum("daily", "weekly", "monthly", name="report_period", create_type=False), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("orders_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("guests_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gross_revenue", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("net_revenue", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_food_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("profit", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("avg_check", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("margin_percent", sa.Numeric(7, 4), nullable=False, server_default="0"),
        sa.Column("breakdown", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("restaurant_id", "period", "period_start", name="uq_report_restaurant_period"),
    )
    op.create_index("ix_reports_restaurant_id", "reports", ["restaurant_id"])
    op.create_index("ix_reports_period_start", "reports", ["period_start"])


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_table("recommendations")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("menu_items")
    op.drop_table("iiko_integrations")
    op.drop_table("subscriptions")
    op.drop_table("user_restaurant_roles")
    op.drop_table("restaurants")
    op.drop_table("users")
    for enum_name in (
        "report_period", "recommendation_status", "recommendation_priority",
        "recommendation_type", "order_status", "subscription_status",
        "subscription_plan", "user_role",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
