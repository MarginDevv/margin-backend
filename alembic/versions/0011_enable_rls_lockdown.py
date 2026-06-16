"""enable RLS on every public table (no policies)

Revision ID: 0011_enable_rls_lockdown
Revises: 0010_order_service_type
Create Date: 2026-06-16

Supabase auto-exposes every table in ``public`` via PostgREST. The
backend connects directly with asyncpg as the ``postgres`` role
(BYPASSRLS) so RLS doesn't affect us, but anon / authenticated tokens
would otherwise be able to read everything — including secrets like
``iiko_integrations.access_token`` and ``telegram_link_tokens.token``.

Enable + force RLS on every public table with no policies attached, so
the PostgREST surface returns zero rows for non-bypass roles. Re-runs
of the loop are idempotent.
"""

from __future__ import annotations

from alembic import op

revision: str = "0011_enable_rls_lockdown"
down_revision: str | None = "0010_order_service_type"
branch_labels = None
depends_on = None


_ENABLE_RLS = """
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public'
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);
  END LOOP;
END$$;
"""

_DISABLE_RLS = """
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public'
  LOOP
    EXECUTE format('ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', t);
  END LOOP;
END$$;
"""


def upgrade() -> None:
    op.execute(_ENABLE_RLS)


def downgrade() -> None:
    op.execute(_DISABLE_RLS)
