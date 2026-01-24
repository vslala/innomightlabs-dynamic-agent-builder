"""Stripe service for subscription management operations."""

import logging
from typing import Optional

import httpx
from fastapi import HTTPException

from ...config import settings

log = logging.getLogger(__name__)


class StripeService:
    BASE_URL = "https://api.stripe.com/v1"

    def __init__(self):
        if not settings.stripe_secret_key:
            raise HTTPException(500, "Stripe not configured")
        self.headers = {"Authorization": f"Bearer {settings.stripe_secret_key}"}

    async def _request(self, method: str, path: str, data: dict = None) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            kwargs = {"headers": self.headers}
            if data:
                kwargs["data"] = data

            response = await getattr(client, method)(f"{self.BASE_URL}{path}", **kwargs)

            if response.status_code >= 400:
                log.error(f"Stripe API error {response.status_code}: {response.text}")
                raise HTTPException(502, "Stripe API request failed")

            return response.json()

    async def get(self, path: str) -> dict:
        return await self._request("get", path)

    async def post(self, path: str, data: dict) -> dict:
        return await self._request("post", path, data)

    async def delete(self, path: str, data: dict = None) -> dict:
        return await self._request("delete", path, data)

    async def cancel_subscription(
        self,
        subscription_id: str,
        feedback: Optional[str] = "customer_service",
        comment: Optional[str] = None
    ) -> bool:
        try:
            data = {}
            if feedback:
                data["cancellation_details[feedback]"] = feedback
            if comment:
                data["cancellation_details[comment]"] = comment

            await self.delete(f"/subscriptions/{subscription_id}", data)
            log.info(f"Successfully cancelled subscription {subscription_id}")
            return True
        except Exception as e:
            log.error(f"Failed to cancel subscription {subscription_id}: {e}")
            return False
