"""Plan limits: the billed person's tier → its allowance for a quota → what is used → allow or refuse (429).

The billed person is the account owner (`billing.account_billing_email`), whoever does the work, so a member's
agents, messages and crawled pages count against the owner's plan. The quotas themselves are in `quotas.py`.
"""

import logging
from datetime import datetime, timezone
from fastapi import HTTPException

from ..payments.subscriptions import SubscriptionRepository
from ..payments.pricing_config import get_pricing_config, PricingTierLimits
from ..accounts.repository import AccountRepository
from ..agents.models import Agent
from ..agents.repository import AgentRepository
from ..identity import IdentityRepository
from ..config import settings
from .billing import account_billing_email
from .quotas import Quota
from .repository import UsageRepository

log = logging.getLogger(__name__)


UNLIMITED = PricingTierLimits(agents=0, messages_per_month=0, kb_pages=0, memory_blocks=0)


class RateLimitService:
    """Simple rate limiting based on subscription tiers."""

    def __init__(self) -> None:
        self.usage_repo = UsageRepository()
        self.subscription_repo = SubscriptionRepository()
        self.agent_repo = AgentRepository()

    def get_user_tier(self, user_email: str) -> str:
        """
        Get user's subscription tier.

        Returns:
            A tier key from the pricing config, such as 'free' or 'business'
        """
        subscription = self.subscription_repo.get_active_for_user(user_email)

        if not subscription or not subscription.plan_name:
            return "free"

        return subscription.plan_name

    def get_tier_limits(self, tier: str) -> PricingTierLimits:
        """Get limits for a tier."""
        config = get_pricing_config()

        for pricing_tier in config.tiers:
            if pricing_tier.key == tier:
                return pricing_tier.limits

        return config.tiers[0].limits

    def get_account_limits(self, account_id: str) -> PricingTierLimits:
        """Limits on what an account owns, such as its leads: its owner's tier, until billing moves to accounts
        (KAN-86)."""
        owner_email = account_billing_email(account_id) or ""
        if settings.is_superuser_email(owner_email):
            return UNLIMITED
        return self.get_tier_limits(self.get_user_tier(owner_email))

    def check(self, billed_email: str, quota: Quota, requested: int = 1) -> None:
        """Refuse (HTTP 429) when the billed person's plan has less than `requested` left of `quota`.

        The email is the account owner's (`billing.account_billing_email`), whoever does the work. Superusers and
        an allowance of 0 are unlimited.
        """
        if settings.is_superuser_email(billed_email):
            log.info("Rate-limit bypass applied", extra={"user": billed_email, "limit_type": quota.name})
            return

        tier = self.get_user_tier(billed_email)
        limit = quota.allowance(self.get_tier_limits(tier))
        if limit == 0:
            return

        current = self._used(billed_email, quota)
        remaining = limit - current
        if requested <= remaining:
            return

        detail = {"limit": limit, "current": current, "remaining": remaining, "tier": tier}
        log.info("Plan limit reached", extra={"user": billed_email, "limit_type": quota.name,
                                               "requested": requested, **detail})
        raise HTTPException(status_code=429, detail={
            "message": quota.refusal(limit, remaining), **detail,
            "upgrade_url": f"{settings.frontend_url}/pricing",
        })

    def _used(self, billed_email: str, quota: Quota) -> int:
        if quota.monthly is None:
            return len(self._agents_charged_to(billed_email))
        usage = self.usage_repo.get_usage(billed_email, datetime.now(timezone.utc).strftime("%Y-%m"))
        return quota.monthly(usage) if usage else 0

    def _agents_charged_to(self, billed_email: str) -> list[Agent]:
        """Every agent in the accounts this person owns, whoever created it: the agents their plan pays for.
        Agents they have in someone else's account are charged to that account's owner."""
        identity = IdentityRepository().find_by_email(billed_email)
        if identity is None:
            return []
        accounts = AccountRepository()
        member_of = [member.account_id for member in accounts.list_memberships(identity.user_id)]
        return [
            agent
            for account in accounts.get_many(member_of).values() if account.owner_id == identity.user_id
            for agent in self.agent_repo.list_in_account(account.account_id)
        ]
