"""Portable column types so tests on sqlite don't reject Postgres dialects."""
from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on Postgres (native, indexable), JSON elsewhere — lets us run sqlite
# integration tests that build the schema with `Base.metadata.create_all`.
JsonB = JSON().with_variant(JSONB(), "postgresql")
