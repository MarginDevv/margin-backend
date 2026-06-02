"""High-level iiko sync orchestration."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import IikoIntegrationError, NotFoundError
from app.core.logging import get_logger
from app.repositories.integration_repo import IikoIntegrationRepository
from app.repositories.menu_repo import MenuItemRepository
from app.repositories.order_repo import OrderRepository
from app.services.iiko.client import IikoClient
from app.services.iiko.transformers import (
    nomenclature_to_menu_rows,
    sales_doc_to_order,
)
from app.utils.crypto import decrypt_str
from app.utils.datetime import now_utc

logger = get_logger("iiko.sync")


class IikoSyncService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.integrations = IikoIntegrationRepository(session)
        self.menu = MenuItemRepository(session)
        self.orders = OrderRepository(session)

    async def _build_client(self, restaurant_id: uuid.UUID) -> tuple[IikoClient, Any]:
        integration = await self.integrations.get_by_restaurant(restaurant_id)
        if not integration or not integration.is_active:
            raise NotFoundError("iiko integration is not configured or inactive")
        api_login = decrypt_str(integration.api_login)
        client = IikoClient(
            api_login,
            cached_token=integration.access_token,
            cached_token_expires_at=integration.access_token_expires_at,
        )
        return client, integration

    async def _persist_token(self, integration: Any, client: IikoClient) -> None:
        if client.token and client.token != integration.access_token:
            integration.access_token = client.token
            integration.access_token_expires_at = client.token_expires_at
            await self.session.flush()

    async def sync_nomenclature(self, restaurant_id: uuid.UUID) -> int:
        client, integration = await self._build_client(restaurant_id)
        try:
            if not integration.organization_id:
                orgs = await client.organizations()
                if not orgs:
                    raise IikoIntegrationError("iiko returned no organizations for apiLogin")
                integration.organization_id = orgs[0]["id"]
            data = await client.nomenclature(integration.organization_id)
            rows = nomenclature_to_menu_rows(restaurant_id, data)
            count = await self.menu.upsert_many(rows)
            await self._persist_token(integration, client)
            integration.last_sync_at = now_utc()
            integration.last_sync_error = None
            await self.session.commit()
            logger.info(
                "iiko.nomenclature.synced",
                restaurant_id=str(restaurant_id),
                items=count,
            )
            return count
        except Exception as exc:
            integration.last_sync_error = str(exc)[:1024]
            await self.session.commit()
            raise
        finally:
            await client.aclose()

    async def sync_orders(
        self,
        restaurant_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> int:
        client, integration = await self._build_client(restaurant_id)
        try:
            if not integration.organization_id:
                orgs = await client.organizations()
                if not orgs:
                    raise IikoIntegrationError("iiko returned no organizations for apiLogin")
                integration.organization_id = orgs[0]["id"]

            documents = await client.orders_by_period(
                organization_ids=[integration.organization_id],
                date_from=date_from,
                date_to=date_to,
            )
            menu_items = await self.menu.list_for_restaurant(restaurant_id)
            lookup = {m.iiko_product_id: m for m in menu_items}

            processed = 0
            for doc in documents:
                order_row, item_rows = sales_doc_to_order(restaurant_id, doc, lookup)
                if not order_row.get("iiko_order_id"):
                    continue
                order_id = await self.orders.upsert_order(order_row)
                await self.orders.replace_items(order_id, item_rows)
                processed += 1

            await self._persist_token(integration, client)
            integration.last_sync_at = now_utc()
            integration.last_sync_error = None
            await self.session.commit()
            logger.info(
                "iiko.orders.synced",
                restaurant_id=str(restaurant_id),
                processed=processed,
                date_from=date_from.isoformat(),
                date_to=date_to.isoformat(),
            )
            return processed
        except Exception as exc:
            integration.last_sync_error = str(exc)[:1024]
            await self.session.commit()
            raise
        finally:
            await client.aclose()

    async def incremental_sync(
        self, restaurant_id: uuid.UUID, *, window_minutes: int = 30
    ) -> int:
        """Pull orders changed since last_sync_at (with a small overlap)."""
        integration = await self.integrations.get_by_restaurant(restaurant_id)
        if not integration:
            raise NotFoundError("iiko integration is not configured")
        to = now_utc()
        if integration.last_sync_at:
            frm = integration.last_sync_at - timedelta(minutes=10)
        else:
            frm = to - timedelta(hours=24)
        # Hard floor: never look back further than `window_minutes` for incremental.
        floor = to - timedelta(minutes=window_minutes)
        if frm < floor and integration.last_sync_at:
            frm = floor
        return await self.sync_orders(restaurant_id, frm, to)

    async def full_day_sync(
        self, restaurant_id: uuid.UUID, day: datetime
    ) -> int:
        """Re-sync the full local day for the given timezone of the restaurant."""
        from app.repositories.restaurant_repo import RestaurantRepository
        from app.utils.datetime import day_bounds_local, restaurant_tz

        restaurant = await RestaurantRepository(self.session).get(restaurant_id)
        if not restaurant:
            raise NotFoundError("Restaurant not found")
        tz = restaurant_tz(restaurant.timezone)
        start_utc, end_utc = day_bounds_local(day.date(), tz)
        return await self.sync_orders(restaurant_id, start_utc, end_utc)
