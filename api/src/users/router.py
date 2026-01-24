"""User management endpoints."""

import json
import logging
from typing import Optional

import boto3
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .repository import UserRepository
from ..payments.subscriptions.repository import SubscriptionRepository
from ..payments.stripe.service import StripeService
from ..config import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


class DeleteAccountResponse(BaseModel):
    message: str
    status: str


@router.delete("/me", response_model=DeleteAccountResponse)
async def delete_account(request: Request):
    """
    Delete user account.

    Process:
    1. Mark user as INACTIVE (blocks re-login)
    2. Cancel Stripe subscription immediately
    3. Trigger background cascade deletion via Lambda
    """
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(401, "Not authenticated")

    user_repo = UserRepository()
    subscription_repo = SubscriptionRepository()

    # Mark user as INACTIVE
    success = user_repo.mark_inactive(user_email)
    if not success:
        log.error(f"Failed to mark user {user_email} as inactive")
        raise HTTPException(500, "Failed to initiate account deletion")

    log.info(f"Marked user {user_email} as INACTIVE")

    # Cancel Stripe subscription if exists
    subscription = subscription_repo.get_active_for_user(user_email)
    if subscription:
        try:
            stripe_service = StripeService()
            cancelled = await stripe_service.cancel_subscription(
                subscription.subscription_id,
                feedback="customer_service",
                comment="User requested account deletion"
            )
            if cancelled:
                log.info(f"Cancelled subscription {subscription.subscription_id} for {user_email}")
            else:
                log.warning(f"Failed to cancel subscription for {user_email}, continuing with deletion")
        except Exception as e:
            log.warning(f"Stripe cancellation failed for {user_email}: {e}, continuing with deletion")

    # Trigger async Lambda for cascade deletion
    try:
        lambda_client = boto3.client("lambda", region_name=settings.aws_region)
        function_name = f"{settings.environment}-account-deletion-handler"

        lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps({"user_email": user_email}).encode("utf-8")
        )
        log.info(f"Triggered account deletion Lambda for {user_email}")
    except Exception as e:
        log.error(f"Failed to trigger deletion Lambda for {user_email}: {e}")
        # Don't fail the request - user is already marked inactive

    return DeleteAccountResponse(
        message="Account deletion initiated",
        status="processing"
    )
