"""Menu item / dish, synced from iiko nomenclature."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase
from app.models.mixins import RestaurantMixin

if TYPE_CHECKING:
    from app.models.order import OrderItem
    from app.models.restaurant import Restaurant


class MenuItem(TimestampedBase, RestaurantMixin):
    __tablename__ = "menu_items"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "iiko_product_id", name="uq_menu_item_iiko"),
    )

    iiko_product_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(255), index=True)
    unit: Mapped[str | None] = mapped_column(String(32))

    # Pricing — sale price (with tax) and food cost / self-cost per unit.
    sale_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False,
    )
    food_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False,
    )
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    restaurant: Mapped[Restaurant] = relationship(back_populates="menu_items")
    order_items: Mapped[list[OrderItem]] = relationship(back_populates="menu_item")

    @property
    def margin_per_unit(self) -> Decimal:
        """Profit per unit = sale_price * (1 - tax_rate) - food_cost."""
        net = self.sale_price * (Decimal("1") - self.tax_rate)
        return net - self.food_cost

    @property
    def margin_percent(self) -> Decimal:
        """Margin as % of net revenue. Zero-safe."""
        net = self.sale_price * (Decimal("1") - self.tax_rate)
        if net == 0:
            return Decimal("0")
        return (self.margin_per_unit / net) * Decimal("100")
