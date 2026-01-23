import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class PricingTierLimits(BaseModel):
    agents: int
    messages_per_month: int
    kb_pages: int
    memory_blocks: int


class PricingTierCTA(BaseModel):
    label: str
    href: str


class PricingTierConfig(BaseModel):
    key: str
    name: str
    badge: str
    description: str
    prices: dict[str, str]
    cta: PricingTierCTA
    highlighted: bool = False
    features: list[str]
    limits: PricingTierLimits
    stripe_price_ids: dict[str, str]


class PricingConfig(BaseModel):
    tiers: list[PricingTierConfig]
    addons: list[dict]
    updated_at: Optional[str] = None


def _config_path() -> Path:
    return Path(__file__).with_name(f"{os.getenv("ENVIRONMENT", "dev")}_pricing_config.json")


def get_pricing_config() -> PricingConfig:
    path = _config_path()
    data = json.loads(path.read_text())
    return PricingConfig(**data)
