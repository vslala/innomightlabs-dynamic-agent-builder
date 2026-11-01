"""Every environment the app runs in finds a pricing config."""

import pytest

from src.payments.pricing_config import get_pricing_config


@pytest.mark.parametrize("environment", ["local", "dev", "uat", "prod"])
def test_every_environment_has_pricing(monkeypatch, environment: str):
    monkeypatch.setenv("ENVIRONMENT", environment)

    tiers = get_pricing_config().tiers

    assert tiers
    assert next(t for t in tiers if t.key == "enterprise").cta.href == "/contact?type=sales"


@pytest.mark.parametrize("environment", ["dev", "uat", "prod"])
def test_environments_share_one_catalogue(monkeypatch, environment: str):
    """Only Stripe ids differ per environment; tiers, prices and limits are the same everywhere."""
    monkeypatch.setenv("ENVIRONMENT", "prod")
    prod = get_pricing_config()
    monkeypatch.setenv("ENVIRONMENT", environment)
    config = get_pricing_config()

    def catalogue(c):
        return [t.model_dump(exclude={"stripe_price_ids"}) for t in c.tiers], [a.model_dump() for a in c.addons]

    assert [t.key for t in config.tiers] == ["free", "business", "growth", "enterprise"]
    assert catalogue(config) == catalogue(prod)


@pytest.mark.parametrize("environment", ["dev", "uat", "prod"])
def test_every_priced_tier_can_be_bought(monkeypatch, environment: str):
    monkeypatch.setenv("ENVIRONMENT", environment)

    for tier in get_pricing_config().tiers:
        if tier.prices["monthly"] != "Custom":
            assert set(tier.stripe_price_ids) == {"monthly", "annual"}, f"{tier.key} has no Stripe prices"


def test_pricing_route_serves_limits_and_addons(test_client):
    body = test_client.get("/payments/stripe/pricing").json()

    assert [t["name"] for t in body["tiers"]] == ["Free", "Business", "Growth", "Enterprise"]
    assert body["tiers"][1]["limits"]["agents"] == 5
    assert body["addons"][0]["ctaHref"] == "/contact?type=sales"
