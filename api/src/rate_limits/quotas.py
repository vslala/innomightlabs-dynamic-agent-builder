"""The plan quotas: what a subscription tier allows, and how each is measured.

A quota is data, not code: which limit in the tier it reads, where its usage comes from, and how a refusal
reads. `RateLimitService.check` enforces any of them the same way.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from ..payments.pricing_config import PricingTierLimits
from .models import UsageRecord


@dataclass(frozen=True)
class Quota:
    name: str
    #: The tier's allowance; 0 means unlimited
    allowance: Callable[[PricingTierLimits], int]
    #: This month's usage from the counter the usage stream keeps, or None when usage is what exists now
    #: (agents are counted, not metered)
    monthly: Optional[Callable[[UsageRecord], int]]
    #: What the person reads when refused, from the allowance and what is left of it
    refusal: Callable[[int, int], str]


AGENTS = Quota(
    name="agents",
    allowance=lambda limits: limits.agents,
    monthly=None,
    refusal=lambda limit, _left: f"Agent limit reached ({limit}). Upgrade to create more.",
)

MESSAGES = Quota(
    name="messages",
    allowance=lambda limits: limits.messages_per_month,
    monthly=lambda usage: usage.messages_used,
    refusal=lambda limit, _left: f"Monthly message limit reached ({limit}). Upgrade for more.",
)

KB_PAGES = Quota(
    name="kb_pages",
    allowance=lambda limits: limits.kb_pages,
    monthly=lambda usage: usage.kb_pages_used,
    refusal=lambda _limit, left: f"Knowledge base page limit exceeded. {left} pages remaining.",
)
