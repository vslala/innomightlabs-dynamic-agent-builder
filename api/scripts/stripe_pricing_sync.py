#!/usr/bin/env python3
import json
import os
import re
import sys
import argparse
from pathlib import Path
from typing import Any

import stripe
from pydantic import BaseModel, Field


class PricingPrices(BaseModel):
    monthly: str
    annual: str


class PricingTier(BaseModel):
    key: str
    name: str
    prices: PricingPrices
    stripe_price_ids: dict[str, str] = Field(default_factory=dict)
    stripe_product_id: str | None = None

    model_config = {"extra": "allow"}


class PricingConfig(BaseModel):
    tiers: list[PricingTier]
    addons: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: str | None = None

    model_config = {"extra": "allow"}


def _get_env_var(var_name: str, fallback_var: str = None) -> str | None:
    """
    Get environment variable with support for environment-specific prefixes.
    
    Tries in order:
    1. {ENV_PREFIX}_{var_name} (e.g., PROD_STRIPE_SECRET_KEY)
    2. {var_name} (e.g., STRIPE_SECRET_KEY)
    3. {fallback_var} if provided
    """
    environment = os.getenv("ENVIRONMENT", "").upper()
    
    # Try environment-specific variable first
    if environment:
        env_specific = os.getenv(f"{environment}_{var_name}")
        if env_specific:
            return env_specific
    
    # Try non-prefixed variable
    value = os.getenv(var_name)
    if value:
        return value
    
    # Try fallback
    if fallback_var:
        return os.getenv(fallback_var)
    
    return None


def _list_products() -> list[dict]:
    return list(stripe.Product.list(limit=100).auto_paging_iter())


def _list_prices(product_id: str) -> list[dict]:
    return list(stripe.Price.list(product=product_id, limit=100).auto_paging_iter())


def _filter_by_metadata(items: list[dict], metadata: dict[str, str]) -> list[dict]:
    results = []
    for item in items:
        item_meta = item.get("metadata", {}) or {}
        if all(item_meta.get(key) == value for key, value in metadata.items()):
            results.append(item)
    return results


def _parse_amount(value: str) -> int | None:
    digits = re.findall(r"\d+", value)
    if not digits:
        return None
    return int("".join(digits))


def _get_product(
    plan_key: str,
    name: str,
    lookup_key: str,
    existing_id: str | None,
    import_existing: bool,
) -> dict | None:
    if existing_id:
        try:
            product = stripe.Product.retrieve(existing_id)
            return product
        except Exception:
            pass

    metadata_keys = {"plan_key": plan_key, "lookup_key": lookup_key}
    products = _list_products()
    results = _filter_by_metadata(products, metadata_keys)
    if results:
        return results[0]

    results = _filter_by_metadata(products, {"plan_key": plan_key})
    if results:
        return results[0]

    for product in products:
        if product.get("name") == name:
            return product

    if import_existing:
        return None

    return stripe.Product.create(name=name, metadata=metadata_keys)


def _get_price(
    product_id: str,
    plan_key: str,
    billing_cycle: str,
    amount: int,
    currency: str,
    import_existing: bool,
) -> dict:
    prices = _list_prices(product_id)
    results = _filter_by_metadata(
        prices,
        {"plan_key": plan_key, "billing_cycle": billing_cycle},
    )
    for price in results:
        recurring = price.get("recurring") or {}
        if (
            price.get("product") == product_id
            and price.get("currency") == currency
            and price.get("unit_amount") == amount
            and recurring.get("interval") == ("month" if billing_cycle == "monthly" else "year")
        ):
            return price

    lookup_key = f"{plan_key}-{billing_cycle}-{currency}"
    for price in prices:
        if price.get("lookup_key") == lookup_key:
            return price

    if import_existing:
        return None

    return stripe.Price.create(
        product=product_id,
        unit_amount=amount,
        currency=currency,
        recurring={"interval": "month" if billing_cycle == "monthly" else "year"},
        lookup_key=lookup_key,
        metadata={"plan_key": plan_key, "billing_cycle": billing_cycle},
    )


def _config_path(environment: str) -> Path:
    config_path = os.getenv("PRICING_CONFIG_PATH")
    if config_path:
        if "{env}" in config_path:
            return Path(config_path.format(env=environment))
        path = Path(config_path)
        if path.is_dir():
            return path / f"{environment}_pricing_config.json"
        if path.name == f"{environment}_pricing_config.json":
            return path
    return Path(__file__).resolve().parents[1] / f"src/payments/{environment}_pricing_config.json"


def _sync_keys(
    environment: str,
    stripe_secret_key: str | None,
    stripe_publisher_key: str | None,
    import_existing: bool,
    dry_run: bool,
) -> int:
    path = _config_path(environment)
    if not path.exists():
        print(f"❌ Pricing config not found: {path}", file=sys.stderr)
        return 1

    # Get Stripe API key (supports both STRIPE_SECRET_KEY and legacy STRIPE_API_KEY)
    stripe_key = stripe_secret_key
    if not stripe_key:
        print("❌ STRIPE_SECRET_KEY is required", file=sys.stderr)
        print(f"   Tried: {environment.upper()}_STRIPE_SECRET_KEY, STRIPE_SECRET_KEY, STRIPE_API_KEY", file=sys.stderr)
        return 1
    
    stripe.api_key = stripe_key
    
    # Determine Stripe mode
    stripe_mode = "LIVE ⚠️" if stripe_key.startswith("sk_live_") else "TEST"
    
    # Get currency
    currency = _get_env_var("STRIPE_CURRENCY") or "gbp"
    
    # Display sync information
    print("=" * 60)
    print(f"🔄 Syncing Stripe Pricing")
    print("=" * 60)
    print(f"Environment:     {environment}")
    print(f"Stripe Mode:     {stripe_mode}")
    print(f"Currency:        {currency.upper()}")
    print(f"Config File:     {path}")
    print(f"Import Existing: {import_existing}")
    print(f"Dry Run:         {dry_run}")
    print("=" * 60)
    print()
    
    # Warn for production
    if stripe_mode == "LIVE ⚠️":
        print("⚠️  WARNING: Using LIVE Stripe keys - changes will affect production!")
        print()
        # response = input("Continue? (yes/no): ")
        # if response.lower() != "yes":
        #     print("Cancelled.")
        #     return 1
        print()

    # Load pricing config
    config = PricingConfig.model_validate_json(path.read_text())

    changed = False
    for tier in config.tiers:
        plan_key = tier.key
        prices = tier.prices
        price_ids = tier.stripe_price_ids or {}
        product_id = tier.stripe_product_id
        if not plan_key or not prices:
            continue
        if tier.stripe_price_ids is None:
            tier.stripe_price_ids = price_ids

        # Skip custom pricing tiers
        if not price_ids and prices.monthly == "Custom":
            continue

        lookup_key = f"{plan_key}"
        product = _get_product(plan_key, tier.name, lookup_key, product_id, import_existing)
        if not product:
            print(f"⚠️  No product found for {tier.name} (plan_key: {plan_key})")
            print()
            continue
        if not import_existing:
            if product.get("name") != tier.name:
                stripe.Product.modify(product["id"], name=tier.name)
            if product.get("metadata", {}).get("plan_key") != plan_key or product.get("metadata", {}).get("lookup_key") != lookup_key:
                stripe.Product.modify(
                    product["id"],
                    metadata={"plan_key": plan_key, "lookup_key": lookup_key},
                )
        if tier.stripe_product_id != product.get("id"):
            tier.stripe_product_id = product.get("id")
            changed = True
        print(f"📦 Product: {tier.name} (plan_key: {plan_key}) -> {product.get('id')}")

        for billing_cycle in ("monthly", "annual"):
            price_label = getattr(prices, billing_cycle)
            amount_major = _parse_amount(str(price_label))
            if amount_major is None:
                continue
            amount = amount_major * 100
            price = _get_price(
                product["id"],
                plan_key,
                billing_cycle,
                amount,
                currency,
                import_existing,
            )
            if not price:
                print(f"   ⚠️  {billing_cycle.capitalize()}: No price found")
                continue
            
            if price_ids.get(billing_cycle) != price.get("id"):
                price_ids[billing_cycle] = price.get("id")
                print(f"   ✓ {billing_cycle.capitalize()}: {price.get('id')} ({currency.upper()}{amount_major})")
                changed = True
            else:
                print(f"   • {billing_cycle.capitalize()}: {price.get('id')} (unchanged)")

        tier.stripe_price_ids = price_ids
        print()

    if changed and dry_run:
        print(f"🧪 Dry run: changes detected, not writing {path}")
    elif changed:
        path.write_text(config.model_dump_json(indent=2, exclude_none=True))
        print(f"✅ Updated pricing config: {path}")
    else:
        print("✅ Pricing config already in sync.")

    return 0



def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Stripe pricing config files.")
    parser.add_argument(
        "--import-existing",
        action="store_true",
        help="Only import existing Stripe products/prices into pricing config files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without writing to pricing config files.",
    )
    args = parser.parse_args()

    for env in ["dev", "uat", "prod"]:
        print(f"Retrieving keys for: {env}")

        stripe_secret_key = os.getenv(f"{env.upper()}_STRIPE_SECRET_KEY")
        stripe_publisher_key = os.getenv(f"{env.upper()}_STRIPE_PUBLISHER_KEY")

        _sync_keys(
            env,
            stripe_secret_key,
            stripe_publisher_key,
            args.import_existing,
            args.dry_run,
        )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
