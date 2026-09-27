"""Builders for googleAds:mutate operations, in the REST (camelCase JSON) shape.

Builders are pure: the same arguments always build the same operations, which is
what lets a preview's confirmation token match its apply.
"""

from __future__ import annotations

from typing import Any, Optional

from src.skills.google_ads.models import (
    AdGroupSpec,
    KeywordSpec,
    NegativeKeywordSpec,
    ResponsiveSearchAdSpec,
    id_of,
    to_micros,
)

Operation = dict[str, Any]


class TemporaryIds:
    """Negative ids let one atomic mutate create a budget, campaign, and ad groups that refer to each other."""

    def __init__(self) -> None:
        self._next = -1

    def take(self) -> int:
        value = self._next
        self._next -= 1
        return value


#: A real id from the user (a string of digits) or a temporary id from TemporaryIds (a negative int).
Id = str | int


def campaign_name(customer_id: str, campaign_id: Id) -> str:
    return f"customers/{customer_id}/campaigns/{_id(campaign_id, 'campaign_id')}"


def ad_group_name(customer_id: str, ad_group_id: Id) -> str:
    return f"customers/{customer_id}/adGroups/{_id(ad_group_id, 'ad_group_id')}"


def _id(value: Id, label: str) -> str:
    return str(value) if isinstance(value, int) else id_of(value, label)


def create_budget(customer_id: str, temp_id: int, name: str, daily_budget: float) -> Operation:
    return {
        "campaignBudgetOperation": {
            "create": {
                "resourceName": f"customers/{customer_id}/campaignBudgets/{temp_id}",
                "name": f"{name} budget",
                "amountMicros": str(to_micros(daily_budget)),
                "deliveryMethod": "STANDARD",
                "explicitlyShared": False,
            }
        }
    }


def update_budget(budget_resource_name: str, daily_budget: float) -> Operation:
    return {
        "campaignBudgetOperation": {
            "update": {"resourceName": budget_resource_name, "amountMicros": str(to_micros(daily_budget))},
            "updateMask": "amount_micros",
        }
    }


BIDDING = {
    "manual_cpc": lambda max_cpc: {"manualCpc": {}},
    "maximize_clicks": lambda max_cpc: {
        "targetSpend": {"cpcBidCeilingMicros": str(to_micros(max_cpc))} if max_cpc else {}
    },
    "maximize_conversions": lambda max_cpc: {"maximizeConversions": {}},
}


def create_search_campaign(
    customer_id: str,
    temp_id: int,
    budget_temp_id: int,
    *,
    name: str,
    bidding_strategy: str,
    max_cpc: Optional[float],
    include_search_partners: bool,
    enabled: bool,
    contains_eu_political_advertising: bool,
) -> Operation:
    return {
        "campaignOperation": {
            "create": {
                "resourceName": campaign_name(customer_id, temp_id),
                "name": name,
                "status": "ENABLED" if enabled else "PAUSED",
                "advertisingChannelType": "SEARCH",
                "campaignBudget": f"customers/{customer_id}/campaignBudgets/{budget_temp_id}",
                "networkSettings": {
                    "targetGoogleSearch": True,
                    "targetSearchNetwork": include_search_partners,
                    "targetContentNetwork": False,
                    "targetPartnerSearchNetwork": False,
                },
                # Required on every new campaign since the EU political advertising rules.
                "containsEuPoliticalAdvertising": (
                    "CONTAINS_EU_POLITICAL_ADVERTISING"
                    if contains_eu_political_advertising
                    else "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING"
                ),
                **BIDDING[bidding_strategy](max_cpc),
            }
        }
    }


def campaign_location(customer_id: str, campaign_id: Id, location_id: int) -> Operation:
    return {
        "campaignCriterionOperation": {
            "create": {
                "campaign": campaign_name(customer_id, campaign_id),
                "location": {"geoTargetConstant": f"geoTargetConstants/{location_id}"},
            }
        }
    }


def campaign_language(customer_id: str, campaign_id: Id, language_id: int) -> Operation:
    return {
        "campaignCriterionOperation": {
            "create": {
                "campaign": campaign_name(customer_id, campaign_id),
                "language": {"languageConstant": f"languageConstants/{language_id}"},
            }
        }
    }


def update_campaign(customer_id: str, campaign_id: str, fields: dict[str, Any], mask: list[str]) -> Operation:
    return {
        "campaignOperation": {
            "update": {"resourceName": campaign_name(customer_id, campaign_id), **fields},
            "updateMask": ",".join(mask),
        }
    }


def remove_campaign(customer_id: str, campaign_id: str) -> Operation:
    return {"campaignOperation": {"remove": campaign_name(customer_id, campaign_id)}}


def create_ad_group(
    customer_id: str, temp_id: int, campaign_id: Id, spec: AdGroupSpec, status: str = "ENABLED"
) -> Operation:
    ad_group: dict[str, Any] = {
        "resourceName": ad_group_name(customer_id, temp_id),
        "campaign": campaign_name(customer_id, campaign_id),
        "name": spec.name,
        "status": status,
        "type": "SEARCH_STANDARD",
    }
    if spec.max_cpc:
        ad_group["cpcBidMicros"] = str(to_micros(spec.max_cpc))
    return {"adGroupOperation": {"create": ad_group}}


def ad_group_with_contents(
    customer_id: str, ids: TemporaryIds, campaign_id: Id, spec: AdGroupSpec, status: str = "ENABLED"
) -> list[Operation]:
    """An ad group plus its keywords and ads, all in one batch."""
    temp_id = ids.take()
    return [
        create_ad_group(customer_id, temp_id, campaign_id, spec, status),
        *(create_keyword(customer_id, temp_id, keyword) for keyword in spec.keywords),
        *(create_responsive_search_ad(customer_id, temp_id, ad) for ad in spec.ads),
    ]


def update_ad_group(customer_id: str, ad_group_id: str, fields: dict[str, Any], mask: list[str]) -> Operation:
    return {
        "adGroupOperation": {
            "update": {"resourceName": ad_group_name(customer_id, ad_group_id), **fields},
            "updateMask": ",".join(mask),
        }
    }


def create_keyword(customer_id: str, ad_group_id: Id, keyword: KeywordSpec) -> Operation:
    criterion: dict[str, Any] = {
        "adGroup": ad_group_name(customer_id, ad_group_id),
        "status": "ENABLED",
        "keyword": {"text": keyword.text, "matchType": keyword.match_type},
    }
    if keyword.max_cpc:
        criterion["cpcBidMicros"] = str(to_micros(keyword.max_cpc))
    return {"adGroupCriterionOperation": {"create": criterion}}


def keyword_name(customer_id: str, ad_group_id: str, criterion_id: str) -> str:
    return (
        f"customers/{customer_id}/adGroupCriteria/"
        f"{id_of(ad_group_id, 'ad_group_id')}~{id_of(criterion_id, 'criterion_id')}"
    )


def update_keyword(customer_id: str, ad_group_id: str, criterion_id: str, fields: dict[str, Any], mask: list[str]) -> Operation:
    return {
        "adGroupCriterionOperation": {
            "update": {"resourceName": keyword_name(customer_id, ad_group_id, criterion_id), **fields},
            "updateMask": ",".join(mask),
        }
    }


def remove_keyword(customer_id: str, ad_group_id: str, criterion_id: str) -> Operation:
    return {"adGroupCriterionOperation": {"remove": keyword_name(customer_id, ad_group_id, criterion_id)}}


def negative_keyword_for_ad_group(customer_id: str, ad_group_id: str, keyword: NegativeKeywordSpec) -> Operation:
    return {
        "adGroupCriterionOperation": {
            "create": {
                "adGroup": ad_group_name(customer_id, ad_group_id),
                "negative": True,
                "keyword": {"text": keyword.text, "matchType": keyword.match_type},
            }
        }
    }


def negative_keyword_for_campaign(customer_id: str, campaign_id: str, keyword: NegativeKeywordSpec) -> Operation:
    return {
        "campaignCriterionOperation": {
            "create": {
                "campaign": campaign_name(customer_id, campaign_id),
                "negative": True,
                "keyword": {"text": keyword.text, "matchType": keyword.match_type},
            }
        }
    }


def create_responsive_search_ad(customer_id: str, ad_group_id: Id, ad: ResponsiveSearchAdSpec) -> Operation:
    responsive: dict[str, Any] = {
        "headlines": [{"text": text} for text in ad.headlines],
        "descriptions": [{"text": text} for text in ad.descriptions],
    }
    if ad.path1:
        responsive["path1"] = ad.path1
    if ad.path2:
        responsive["path2"] = ad.path2
    return {
        "adGroupAdOperation": {
            "create": {
                "adGroup": ad_group_name(customer_id, ad_group_id),
                "status": ad.status,
                "ad": {"finalUrls": [ad.final_url], "responsiveSearchAd": responsive},
            }
        }
    }


def ad_status(customer_id: str, ad_group_id: str, ad_id: str, status: str) -> Operation:
    name = f"customers/{customer_id}/adGroupAds/{id_of(ad_group_id, 'ad_group_id')}~{id_of(ad_id, 'ad_id')}"
    return {"adGroupAdOperation": {"update": {"resourceName": name, "status": status}, "updateMask": "status"}}


def budget_amounts(operations: list[Operation]) -> list[int]:
    """Every daily budget (micros) a batch creates or sets, for the budget cap."""
    amounts = []
    for operation in operations:
        budget = operation.get("campaignBudgetOperation") or {}
        for verb in ("create", "update"):
            amount = (budget.get(verb) or {}).get("amountMicros")
            if amount is not None:
                amounts.append(int(amount))
    return amounts
