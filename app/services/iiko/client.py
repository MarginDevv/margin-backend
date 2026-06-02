"""Thin async client for iikoCloud Transport API.

Docs: https://api-ru.iiko.services/api/0/, swagger at https://api-ru.iiko.services/docs

Endpoints we use (POST, JSON):
    /access_token                 — issue token (TTL ~1h)
    /organizations                — list orgs available for apiLogin
    /terminal_groups              — list terminal groups for orgs
    /nomenclature                 — full menu / products / groups
    /deliveries/by_delivery_date_and_status — fetch orders by date range
    /documents/sales/by_organizations       — alternative: closed cheques
"""
from __future__ import annotations

from datetime import datetime, timedelta
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

    async def __aenter__(self) -> "IikoClient":
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
        from datetime import UTC
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
        if self._token and self._token_expires_at and self._token_expires_at - timedelta(seconds=60) > now:
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

    async def terminal_groups(self, organization_ids: list[str]) -> list[dict[str, Any]]:
        data = await self._request(
            "/terminal_groups", {"organizationIds": organization_ids}
        )
        return data.get("terminalGroups", [])

    async def nomenclature(self, organization_id: str) -> dict[str, Any]:
        return await self._request("/nomenclature", {"organizationId": organization_id})

    async def orders_by_period(
        self,
        organization_ids: list[str],
        date_from: datetime,
        date_to: datetime,
        statuses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch closed-cheque sales (documents/sales/by_organizations).
        date_from / date_to are UTC datetimes; iiko expects 'YYYY-MM-DD HH:MM:SS.fff'.
        """
        from app.utils.datetime import iiko_dt

        payload: dict[str, Any] = {
            "organizationIds": organization_ids,
            "dateFrom": iiko_dt(date_from),
            "dateTo": iiko_dt(date_to),
        }
        if statuses:
            payload["statuses"] = statuses
        data = await self._request("/documents/sales/by_organizations", payload)
        return data.get("documents", [])

    async def writeoffs_by_period(
        self,
        organization_ids: list[str],
        date_from: datetime,
        date_to: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch writeoff documents for inventory-leak detection.

        Endpoint: /documents/writeoffs/by_organizations
        Response shape mirrors `sales`: { documents: [...] }, each document has
        items[] with productId, amount, sum, etc.
        """
        from app.utils.datetime import iiko_dt

        payload = {
            "organizationIds": organization_ids,
            "dateFrom": iiko_dt(date_from),
            "dateTo": iiko_dt(date_to),
        }
        data = await self._request("/documents/writeoffs/by_organizations", payload)
        return data.get("documents", [])

    async def stop_list(self, organization_ids: list[str]) -> list[dict[str, Any]]:
        """Current stop-list (out-of-stock products) for the given orgs."""
        data = await self._request(
            "/stop_lists", {"organizationIds": organization_ids}
        )
        return data.get("terminalGroupStopLists", [])


class IikoTransientError(Exception):
    """Marker exception that should be retried."""
