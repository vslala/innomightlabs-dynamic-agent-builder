#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

import stripe


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


def _get_product(plan_key: str, name: str) -> dict:
    results = _filter_by_metadata(_list_products(), {"plan_key": plan_key})
    if results:
        return results[0]
    return stripe.Product.create(name=name, metadata={"plan_key": plan_key})


def _get_price(product_id: str, plan_key: str, billing_cycle: str, amount: int, currency: str) -> dict:
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

    return stripe.Price.create(
        product=product_id,
        unit_amount=amount,
        currency=currency,
        recurring={"interval": "month" if billing_cycle == "monthly" else "year"},
        metadata={"plan_key": plan_key, "billing_cycle": billing_cycle},
    )


def main() -> int:
    config_path = os.getenv("PRICING_CONFIG_PATH")
    if not config_path:
        config_path = str(Path(__file__).resolve().parents[1] / "api/src/payments/pricing_config.json")
    path = Path(config_path)
    if not path.exists():
        print(f"pricing config not found: {path}", file=sys.stderr)
        return 1

    if not os.getenv("STRIPE_API_KEY"):
        print("STRIPE_API_KEY is required", file=sys.stderr)
        return 1
    stripe.api_key = os.environ["STRIPE_API_KEY"]

    config = json.loads(path.read_text())
    currency = os.getenv("STRIPE_CURRENCY", "gbp")

    changed = False
    for tier in config.get("tiers", []):
        plan_key = tier.get("key")
        prices = tier.get("prices", {})
        price_ids = tier.get("stripe_price_ids") or {}
        if not plan_key or not prices:
            continue
        if tier.get("stripe_price_ids") is None:
            tier["stripe_price_ids"] = price_ids

        if not price_ids and prices.get("monthly") == "Custom":
            continue

        product = _get_product(plan_key, tier.get("name", plan_key))

        for billing_cycle in ("monthly", "annual"):
            price_label = prices.get(billing_cycle)
            amount_major = _parse_amount(str(price_label))
            if amount_major is None:
                continue
            amount = amount_major * 100
            price = _get_price(product["id"], plan_key, billing_cycle, amount, currency)
            if price_ids.get(billing_cycle) != price.get("id"):
                price_ids[billing_cycle] = price.get("id")
                changed = True

        tier["stripe_price_ids"] = price_ids

    if changed:
        path.write_text(json.dumps(config, indent=2))
        print(f"Updated pricing config: {path}")
    else:
        print("Pricing config already in sync.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
