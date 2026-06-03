"""Thin async client for iikoCloud Transport API.

Docs: https://api-ru.iiko.services/docs (the OpenAPI spec is also vendored
under ``docs/iiko_openapi.json`` so we can sanity-check field names
without going to the internet).

Endpoints we use (POST, JSON; base_url already includes ``/api/1``):

    /access_token                              — issue token (TTL ~1h, deprecated;
                                                 /api/v2/access_token is the
                                                 modern replacement, migration TODO)
    /organizations                             — list orgs available for apiLogin
    /nomenclature                              — menu (revision-based delta sync)
    /deliveries/by_delivery_date_and_status    — orders by date range; despite
                                                 the URL it returns dine-in
                                                 (Common), pickup and courier
                                                 deliveries alike
    /deliveries/by_revision                    — orders incremental sync via
                                                 startRevision; cheaper than
                                                 date range, but max 3-hour
                                                 offset from current maxRevision
"""
from __future__ import annotations

from datetime import datetime, timedelta, tzinfo
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.exceptions import IikoIntegrationError
from app.core.logging import get_logger

logger = get_logger("iiko.client")


class IikoClient:
    """Async iikoCloud client with token caching and retry."""

    def __init__(
        self,
        api_login: str,
        *,
        cached_token: str | None = None,
        cached_token_expires_at: datetime | None = None,
    ) -> None:
        self._api_login = api_login
        self._token: str | None = cached_token
        self._token_expires_at: datetime | None = cached_token_expires_at
        self._client = httpx.AsyncClient(
            base_url=settings.iiko_api_base_url,
            timeout=settings.iiko_http_timeout,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )

    async def __aenter__(self) -> IikoClient:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def token_expires_at(self) -> datetime | None:
        return self._token_expires_at

    # ----- HTTP plumbing -----

    async def _request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path != "/access_token":
            await self._ensure_token()

        headers: dict[str, str] = {}
        if self._token and path != "/access_token":
            headers["Authorization"] = f"Bearer {self._token}"

        retryer = AsyncRetrying(
            stop=stop_after_attempt(settings.iiko_retry_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.TransportError, IikoTransientError)),
            reraise=True,
        )

        async for attempt in retryer:
            with attempt:
                response = await self._client.post(path, json=payload, headers=headers)
                if response.status_code == 401 and path != "/access_token":
                    # Token may have been revoked — re-issue once and retry.
                    self._token = None
                    self._token_expires_at = None
                    await self._ensure_token()
                    headers["Authorization"] = f"Bearer {self._token}"
                    response = await self._client.post(path, json=payload, headers=headers)
                if 500 <= response.status_code < 600:
                    raise IikoTransientError(
                        f"iiko {path} returned {response.status_code}: {response.text[:200]}"
                    )
                if response.status_code >= 400:
                    raise IikoIntegrationError(
                        f"iiko {path} failed [{response.status_code}]: {response.text[:300]}"
                    )
                data = response.json()
                if isinstance(data, dict) and data.get("errorDescription"):
                    raise IikoIntegrationError(
                        f"iiko {path} business error: {data['errorDescription']}"
                    )
                return data  # type: ignore[no-any-return]
        raise IikoIntegrationError(f"iiko {path} exhausted retries")

    async def _ensure_token(self) -> None:
        from datetime import UTC
        now = datetime.now(UTC)
        if (
            self._token
            and self._token_expires_at
            and self._token_expires_at - timedelta(seconds=60) > now
        ):
            return
        data = await self._request("/access_token", {"apiLogin": self._api_login})
        token = data.get("token")
        if not token:
            raise IikoIntegrationError("iiko access_token response missing 'token'")
        self._token = token
        self._token_expires_at = now + timedelta(seconds=settings.iiko_token_ttl_seconds)
        logger.info("iiko.token.issued", expires_at=self._token_expires_at.isoformat())

    # ----- Domain methods -----

    async def organizations(self) -> list[dict[str, Any]]:
        data = await self._request("/organizations", {})
        return data.get("organizations", [])

    async def nomenclature(
        self, organization_id: str, *, start_revision: int = 0
    ) -> dict[str, Any]:
        """Fetch nomenclature, optionally as a diff from ``start_revision``.

        Per /api/1/nomenclature spec: when ``startRevision`` equals the
        ``revision`` of the last full response, iiko returns the same
        ``revision`` value with empty ``groups`` / ``productCategories`` /
        ``products`` / ``sizes`` lists. Callers should compare the returned
        ``revision`` to the one they passed to decide whether anything
        changed.
        """
        return await self._request(
            "/nomenclature",
            {"organizationId": organization_id, "startRevision": start_revision},
        )

    async def orders_by_date_range(
        self,
        organization_ids: list[str],
        date_from: datetime,
        date_to: datetime,
        *,
        local_tz: tzinfo | None = None,
        statuses: list[str] | None = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        """Backfill via POST /api/1/deliveries/by_delivery_date_and_status.

        Despite the URL, this endpoint returns **all** orders for the period —
        dine-in (``orderServiceType=Common``), pickup (``DeliveryByClient``)
        and courier deliveries (``DeliveryByCourier``). It is the only
        date-range entry point in the Transport API.

        ``date_from`` / ``date_to`` are UTC datetimes; the API expects them
        in **restaurant-local** time (swagger: "Local for delivery
        terminal"), so pass ``local_tz`` to convert before formatting.

        Returns ``(max_revision, order_infos)`` where ``max_revision`` is
        the response's ``maxRevision`` (use it to seed
        ``last_orders_revision`` on the first run) and ``order_infos`` is
        the flattened list of ``OrderInfo`` objects across all organisations.
        """
        from app.utils.datetime import iiko_dt

        payload: dict[str, Any] = {
            "organizationIds": organization_ids,
            "deliveryDateFrom": iiko_dt(date_from, tz=local_tz),
            "deliveryDateTo": iiko_dt(date_to, tz=local_tz),
        }
        if statuses:
            payload["statuses"] = statuses
        data = await self._request(
            "/deliveries/by_delivery_date_and_status", payload
        )
        return _extract_orders(data)

    async def orders_by_revision(
        self,
        organization_ids: list[str],
        start_revision: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        """Incremental sync via POST /api/1/deliveries/by_revision.

        Returns ``(max_revision, order_infos)``. Per spec the maximum
        revision offset is 3 hours — for longer gaps callers should fall
        back to :meth:`orders_by_date_range`.
        """
        data = await self._request(
            "/deliveries/by_revision",
            {"organizationIds": organization_ids, "startRevision": start_revision},
        )
        return _extract_orders(data)


def _extract_orders(data: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """Flatten the ``ordersByOrganizations`` envelope shared by deliveries
    endpoints into ``(max_revision, [OrderInfo, ...])``.
    """
    max_revision = int(data.get("maxRevision") or 0)
    orders: list[dict[str, Any]] = []
    for org_block in data.get("ordersByOrganizations") or []:
        orders.extend(org_block.get("orders") or [])
    return max_revision, orders


class IikoTransientError(Exception):
    """Marker exception that should be retried."""
