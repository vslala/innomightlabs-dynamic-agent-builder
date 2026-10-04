"""Every environment the app runs in finds a pricing config."""

import pytest

from src.payments.pricing_config import get_pricing_config


@pytest.mark.parametrize("environment", ["local", "dev", "uat", "prod"])
def test_every_environment_has_pricing(monkeypatch, environment: str):
    monkeypatch.setenv("ENVIRONMENT", environment)

    tiers = get_pricing_config().tiers

    assert tiers
    assert next(t for t in tiers if t.key == "enterprise").cta.href == "/contact?type=sales"
