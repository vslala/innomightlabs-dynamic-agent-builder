"""
Simplified rate limiting service.

Design: Get user tier → Get tier limits → Check usage → Enforce limits
"""

from datetime import datetime, timezone
from fastapi import HTTPException

from ..payments.subscriptions import SubscriptionRepository
from ..payments.pricing_config import get_pricing_config, PricingTierLimits
from ..agents.repository import AgentRepository
from .repository import UsageRepository


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
            'free', 'starter', 'pro', or 'enterprise'
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

    def check_agent_limit(self, user_email: str) -> None:
        """
        Check if user can create a new agent.

        Raises:
            HTTPException: 429 if limit exceeded
        """
        tier = self.get_user_tier(user_email)
        limits = self.get_tier_limits(tier)

        if limits.agents == 0:
            return

        current_agents = self.agent_repo.find_all_by_created_by(user_email)

        if len(current_agents) >= limits.agents:
            raise HTTPException(
                status_code=429,
                detail={
                    "message": f"Agent limit reached ({limits.agents}). Upgrade to create more.",
                    "limit": limits.agents,
                    "current": len(current_agents),
                    "tier": tier,
                },
            )

    def check_message_limit(self, user_email: str) -> None:
        """
        Check if user can send a message this month.

        Raises:
            HTTPException: 429 if limit exceeded
        """
        tier = self.get_user_tier(user_email)
        limits = self.get_tier_limits(tier)

        if limits.messages_per_month == 0:
            return

        period_key = datetime.now(timezone.utc).strftime("%Y-%m")
        usage = self.usage_repo.get_usage(user_email, period_key)
        current = usage.messages_used if usage else 0

        if current >= limits.messages_per_month:
            raise HTTPException(
                status_code=429,
                detail={
                    "message": f"Monthly message limit reached ({limits.messages_per_month}). Upgrade for more.",
                    "limit": limits.messages_per_month,
                    "current": current,
                    "tier": tier,
                },
            )

    def check_kb_pages_limit(self, user_email: str, requested_pages: int) -> None:
        """
        Check if user can crawl requested pages.

        Raises:
            HTTPException: 429 if limit exceeded
        """
        tier = self.get_user_tier(user_email)
        limits = self.get_tier_limits(tier)

        if limits.kb_pages == 0:
            return

        period_key = datetime.now(timezone.utc).strftime("%Y-%m")
        usage = self.usage_repo.get_usage(user_email, period_key)
        current = usage.kb_pages_used if usage else 0

        remaining = limits.kb_pages - current

        if requested_pages > remaining:
            raise HTTPException(
                status_code=429,
                detail={
                    "message": f"Knowledge base page limit exceeded. {remaining} pages remaining.",
                    "limit": limits.kb_pages,
                    "current": current,
                    "remaining": remaining,
                    "tier": tier,
                },
            )

    def record_message_usage(self, user_email: str) -> None:
        """Record a message sent."""
        period_key = datetime.now(timezone.utc).strftime("%Y-%m")
        self.usage_repo.increment_messages(user_email, period_key, 1)

    def record_kb_pages(self, user_email: str, count: int) -> None:
        """Record pages crawled."""
        if count <= 0:
            return
        period_key = datetime.now(timezone.utc).strftime("%Y-%m")
        self.usage_repo.increment_kb_pages(user_email, period_key, count)

    def get_usage_summary(self, user_email: str) -> dict:
        """Get usage summary for current month."""
        tier = self.get_user_tier(user_email)
        limits = self.get_tier_limits(tier)

        period_key = datetime.now(timezone.utc).strftime("%Y-%m")
        usage = self.usage_repo.get_usage(user_email, period_key)
        agents = self.agent_repo.find_all_by_created_by(user_email)

        return {
            "tier": tier,
            "period": period_key,
            "limits": {
                "agents": limits.agents if limits.agents > 0 else "unlimited",
                "messages_per_month": limits.messages_per_month if limits.messages_per_month > 0 else "unlimited",
                "kb_pages": limits.kb_pages if limits.kb_pages > 0 else "unlimited",
                "memory_blocks": limits.memory_blocks if limits.memory_blocks > 0 else "unlimited",
            },
            "usage": {
                "agents": len(agents),
                "messages": usage.messages_used if usage else 0,
                "kb_pages": usage.kb_pages_used if usage else 0,
            },
        }
