"""High-level iiko sync orchestration."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import IikoIntegrationError, NotFoundError
from app.core.logging import get_logger
from app.models.activity_event import ActivityKind, ActivitySeverity
from app.repositories.integration_repo import IikoIntegrationRepository
from app.repositories.menu_repo import MenuItemRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.restaurant_repo import RestaurantRepository
from app.services.activity.event_service import ActivityEventService
from app.services.iiko.client import IikoClient
from app.services.iiko.transformers import (
    nomenclature_to_menu_rows,
    sales_doc_to_order,
)
from app.utils.crypto import decrypt_str
from app.utils.datetime import now_utc, restaurant_tz

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
        if not (integration.api_key and integration.app_id and integration.client_secret):
            # All three are required by /api/v2/access_token; the model
            # holds them as nullable for migration-reversibility only.
            raise IikoIntegrationError(
                "iiko integration is missing apiKey / appId / clientSecret"
            )
        client = IikoClient(
            api_key=integration.api_key,
            app_id=integration.app_id,
            client_secret=decrypt_str(integration.client_secret),
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
                    raise IikoIntegrationError("iiko returned no organizations for this apiKey")
                integration.organization_id = orgs[0]["id"]
            start_revision = integration.last_menu_revision or 0
            data = await client.nomenclature(
                integration.organization_id, start_revision=start_revision
            )
            new_revision = int(data.get("revision") or 0)

            # iiko returns the same revision + empty lists when nothing changed.
            if new_revision == start_revision and start_revision != 0:
                await self._persist_token(integration, client)
                integration.last_sync_at = now_utc()
                integration.last_sync_error = None
                await self.session.commit()
                logger.info(
                    "iiko.nomenclature.unchanged",
                    restaurant_id=str(restaurant_id),
                    revision=new_revision,
                )
                return 0

            rows = nomenclature_to_menu_rows(restaurant_id, data)
            count = await self.menu.upsert_many(rows)
            integration.last_menu_revision = new_revision
            await self._persist_token(integration, client)
            integration.last_sync_at = now_utc()
            integration.last_sync_error = None
            await self.session.commit()
            logger.info(
                "iiko.nomenclature.synced",
                restaurant_id=str(restaurant_id),
                items=count,
                revision=new_revision,
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
        """Backfill orders for a date range via ``/api/1/deliveries/by_delivery_date_and_status``.

        Despite the URL, the endpoint returns dine-in (``orderServiceType=Common``),
        pickup and courier-delivery orders alike. The response's ``maxRevision``
        is captured into ``last_orders_revision`` so the next incremental sync
        can resume from it.
        """
        client, integration = await self._build_client(restaurant_id)
        restaurant = await RestaurantRepository(self.session).get(restaurant_id)
        if not restaurant:
            await client.aclose()
            raise NotFoundError("Restaurant not found")
        local_tz = restaurant_tz(restaurant.timezone)
        try:
            if not integration.organization_id:
                orgs = await client.organizations()
                if not orgs:
                    raise IikoIntegrationError("iiko returned no organizations for this apiKey")
                integration.organization_id = orgs[0]["id"]

            max_revision, order_infos = await client.orders_by_date_range(
                organization_ids=[integration.organization_id],
                date_from=date_from,
                date_to=date_to,
                local_tz=local_tz,
            )
            processed = await self._persist_orders(restaurant_id, order_infos)

            if max_revision:
                integration.last_orders_revision = max_revision
            await self._persist_token(integration, client)
            integration.last_sync_at = now_utc()
            integration.last_sync_error = None
            await ActivityEventService(self.session).emit(
                restaurant_id,
                ActivityKind.IIKO_SYNC_SUCCESS,
                title=f"iiko: синхронизировано заказов: {processed}",
                payload={
                    "processed": processed,
                    "date_from": date_from.isoformat(),
                    "date_to": date_to.isoformat(),
                    "max_revision": max_revision,
                },
            )
            await self.session.commit()
            logger.info(
                "iiko.orders.synced",
                restaurant_id=str(restaurant_id),
                processed=processed,
                date_from=date_from.isoformat(),
                date_to=date_to.isoformat(),
                max_revision=max_revision,
            )
            return processed
        except Exception as exc:
            integration.last_sync_error = str(exc)[:1024]
            await ActivityEventService(self.session).emit(
                restaurant_id,
                ActivityKind.IIKO_SYNC_FAILED,
                title="iiko: ошибка синхронизации заказов",
                severity=ActivitySeverity.ERROR,
                payload={"error": str(exc)[:1024]},
            )
            await self.session.commit()
            raise
        finally:
            await client.aclose()

    async def _persist_orders(
        self, restaurant_id: uuid.UUID, order_infos: list[dict[str, Any]]
    ) -> int:
        """Map OrderInfo dicts through the transformer and upsert."""
        menu_items = await self.menu.list_for_restaurant(restaurant_id)
        lookup = {m.iiko_product_id: m for m in menu_items}
        processed = 0
        for info in order_infos:
            order_row, item_rows = sales_doc_to_order(restaurant_id, info, lookup)
            if not order_row.get("iiko_order_id"):
                continue
            order_id = await self.orders.upsert_order(order_row)
            await self.orders.replace_items(order_id, item_rows)
            processed += 1
        return processed

    async def incremental_sync(
        self, restaurant_id: uuid.UUID, *, window_minutes: int = 30
    ) -> int:
        """Pull orders that changed since the last successful sync.

        Prefers ``/api/1/deliveries/by_revision`` (cheap delta) when we have
        a stored revision; falls back to the date-range backfill for the
        first run or when the integration was idle long enough that the
        revision may be outside iiko's 3-hour offset window.
        """
        integration = await self.integrations.get_by_restaurant(restaurant_id)
        if not integration:
            raise NotFoundError("iiko integration is not configured")

        # No prior revision OR last sync is older than iiko's 3-hour offset
        # window — by_revision will reject our startRevision. Fall back to
        # a bounded date-range backfill.
        revision_window = timedelta(hours=3)
        too_stale = (
            integration.last_sync_at is not None
            and (now_utc() - integration.last_sync_at) > revision_window
        )
        if integration.last_orders_revision is None or too_stale:
            to = now_utc()
            if integration.last_sync_at:
                frm = integration.last_sync_at - timedelta(minutes=10)
            else:
                frm = to - timedelta(hours=24)
            floor = to - timedelta(minutes=window_minutes)
            if frm < floor and integration.last_sync_at:
                frm = floor
            return await self.sync_orders(restaurant_id, frm, to)

        return await self._sync_orders_by_revision(
            restaurant_id, integration.last_orders_revision
        )

    async def _sync_orders_by_revision(
        self, restaurant_id: uuid.UUID, start_revision: int
    ) -> int:
        client, integration = await self._build_client(restaurant_id)
        try:
            if not integration.organization_id:
                orgs = await client.organizations()
                if not orgs:
                    raise IikoIntegrationError("iiko returned no organizations for this apiKey")
                integration.organization_id = orgs[0]["id"]

            max_revision, order_infos = await client.orders_by_revision(
                organization_ids=[integration.organization_id],
                start_revision=start_revision,
            )
            if max_revision == start_revision:
                # Nothing changed since the previous sync — short-circuit.
                await self._persist_token(integration, client)
                integration.last_sync_at = now_utc()
                integration.last_sync_error = None
                await self.session.commit()
                logger.info(
                    "iiko.orders.unchanged",
                    restaurant_id=str(restaurant_id),
                    revision=max_revision,
                )
                return 0

            processed = await self._persist_orders(restaurant_id, order_infos)
            if max_revision:
                integration.last_orders_revision = max_revision
            await self._persist_token(integration, client)
            integration.last_sync_at = now_utc()
            integration.last_sync_error = None
            await ActivityEventService(self.session).emit(
                restaurant_id,
                ActivityKind.IIKO_SYNC_SUCCESS,
                title=f"iiko: синхронизировано заказов: {processed}",
                payload={
                    "processed": processed,
                    "start_revision": start_revision,
                    "max_revision": max_revision,
                },
            )
            await self.session.commit()
            logger.info(
                "iiko.orders.synced",
                restaurant_id=str(restaurant_id),
                processed=processed,
                start_revision=start_revision,
                max_revision=max_revision,
            )
            return processed
        except Exception as exc:
            integration.last_sync_error = str(exc)[:1024]
            await ActivityEventService(self.session).emit(
                restaurant_id,
                ActivityKind.IIKO_SYNC_FAILED,
                title="iiko: ошибка синхронизации заказов",
                severity=ActivitySeverity.ERROR,
                payload={"error": str(exc)[:1024]},
            )
            await self.session.commit()
            raise
        finally:
            await client.aclose()

    async def full_day_sync(
        self, restaurant_id: uuid.UUID, day: datetime
    ) -> int:
        """Re-sync the full local day for the given timezone of the restaurant."""
        from app.utils.datetime import day_bounds_local

        restaurant = await RestaurantRepository(self.session).get(restaurant_id)
        if not restaurant:
            raise NotFoundError("Restaurant not found")
        tz = restaurant_tz(restaurant.timezone)
        start_utc, end_utc = day_bounds_local(day.date(), tz)
        return await self.sync_orders(restaurant_id, start_utc, end_utc)
