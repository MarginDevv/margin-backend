"""switch iiko auth to v2 (apiKey + appId + clientSecret)

Revision ID: 0009_iiko_auth_v2
Revises: 0008_drop_terminal_group_id
Create Date: 2026-06-03

iikoCloud Transport API marks /api/1/access_token as deprecated; the
modern entry point is /api/v2/access_token, which authenticates with
three credentials instead of the legacy single apiLogin:

  apiKey       — generated in iikoWeb under "Integrations → API Keys".
  appId        — UUID issued by the iiko Developer Portal when an
                 application is registered.
  clientSecret — the application's secret, shown only once at creation
                 time in the portal. Stored encrypted at rest.

Migration:
  * drop the api_login column (was used as the v1 apiLogin payload),
  * add api_key, app_id, client_secret as nullable columns. Nullable
    rather than NOT NULL so the migration is reversible even if some
    leftover rows exist; the application validates non-null at the
    point of use and raises IikoIntegrationError if credentials are
    missing.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0009_iiko_auth_v2"
down_revision: str | None = "0008_drop_terminal_group_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("iiko_integrations", "api_login")
    op.add_column(
        "iiko_integrations",
        sa.Column("api_key", sa.String(255), nullable=True),
    )
    op.add_column(
        "iiko_integrations",
        sa.Column("app_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "iiko_integrations",
        sa.Column("client_secret", sa.String(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("iiko_integrations", "client_secret")
    op.drop_column("iiko_integrations", "app_id")
    op.drop_column("iiko_integrations", "api_key")
    op.add_column(
        "iiko_integrations",
        sa.Column("api_login", sa.String(255), nullable=True),
    )
