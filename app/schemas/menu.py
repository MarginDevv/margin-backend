"""Menu item schemas."""
from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.schemas.common import ORMModel, TimestampedSchema


class MenuItemRead(TimestampedSchema):
    iiko_product_id: str
    name: str
    category: str | None
    unit: str | None
    sale_price: Decimal
    food_cost: Decimal
    tax_rate: Decimal
    is_active: bool


class MenuItemUpdate(ORMModel):
    sale_price: Decimal | None = Field(default=None, ge=0)
    food_cost: Decimal | None = Field(default=None, ge=0)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1)
    is_active: bool | None = None
