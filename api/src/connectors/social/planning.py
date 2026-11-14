"""Which accounts a post can go to, and why not to the others. `check` and `publish` share it, so what the agent was told
before posting is exactly what happens when it posts. It makes no network calls."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.connectors.social.documents import DocumentFacts, extension, megabytes
from src.connectors.social.models import SocialAccount, SocialAccountStatus
from src.connectors.social.networks import enabled_networks, network_for

TEXT_TOO_LONG = "text_too_long"
IMAGE_REQUIRED = "image_required"
IMAGES_NOT_SUPPORTED = "images_not_supported"
TOO_MANY_IMAGES = "too_many_images"
NEEDS_RECONNECT = "needs_reconnect"
NETWORK_DISABLED = "network_disabled"
EMPTY_TEXT = "empty_text"
TOO_MANY_HASHTAGS = "too_many_hashtags"
TOO_MANY_MENTIONS = "too_many_mentions"
DOCUMENTS_NOT_SUPPORTED = "documents_not_supported"
DOCUMENT_TYPE_NOT_SUPPORTED = "document_type_not_supported"
DOCUMENT_TOO_LARGE = "document_too_large"
DOCUMENT_WITH_IMAGES = "document_with_images"

#: A #tag or an @handle starts a word: an email address or "C#" isn't one
HASHTAG = re.compile(r"(?<![\w&])#\w+")
MENTION = re.compile(r"(?<![\w@])@[\w.]+")


@dataclass(frozen=True)
class TargetPlan:
    account: SocialAccount
    text: str
    #: Why this account is skipped; None when the post can go
    reason: str | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.reason is None


def select_accounts(accounts: list[SocialAccount], selection: Any = "all", network: str | None = None) -> list[SocialAccount]:
    """`selection` is "all" or a list of social_account_ids; `network` narrows it to one network's accounts."""
    chosen = accounts
    if isinstance(selection, list):
        wanted = {str(item) for item in selection}
        unknown = wanted - {account.social_account_id for account in accounts}
        if unknown:
            raise ValueError(f"No connected social account: {', '.join(sorted(unknown))}")
        chosen = [account for account in accounts if account.social_account_id in wanted]
    elif selection not in (None, "", "all"):
        raise ValueError('accounts must be "all" or a list of social_account_ids')
    if network:
        chosen = [account for account in chosen if account.network == network]
    return chosen


def plan_targets(
    accounts: list[SocialAccount], text: str, overrides: dict[str, str] | None = None, image_count: int = 0,
    document: DocumentFacts | None = None,
) -> list[TargetPlan]:
    """One plan per account. An override is keyed by social_account_id, or by network for all of its accounts."""
    overrides = overrides or {}
    enabled = {network.key for network in enabled_networks()}
    return [_plan(account, _text_for(account, text, overrides), image_count, document, enabled) for account in accounts]


def _text_for(account: SocialAccount, text: str, overrides: dict[str, str]) -> str:
    return str(overrides.get(account.social_account_id) or overrides.get(account.network) or text).strip()


def _plan(account: SocialAccount, text: str, image_count: int, document: DocumentFacts | None,
          enabled: set[str]) -> TargetPlan:
    def skip(reason: str, detail: str = "") -> TargetPlan:
        return TargetPlan(account, text, reason, detail)

    if account.network not in enabled:
        return skip(NETWORK_DISABLED, "This network is not set up on this server")
    if account.effective_status() == SocialAccountStatus.NEEDS_RECONNECT:
        return skip(NEEDS_RECONNECT, f"Reconnect {network_for(account.network).display_name} in Connectors")
    limits = network_for(account.network).limits
    if not text:
        return skip(EMPTY_TEXT, "There is no text to post")
    length = limits.text_length(text)
    if length > limits.max_text:
        return skip(TEXT_TOO_LONG, f"{length}/{limits.max_text} characters")
    name = network_for(account.network).display_name
    hashtags, mentions = len(HASHTAG.findall(text)), len(MENTION.findall(text))
    if limits.max_hashtags is not None and hashtags > limits.max_hashtags:
        return skip(TOO_MANY_HASHTAGS, f"{hashtags}/{limits.max_hashtags} hashtags")
    if limits.max_mentions is not None and mentions > limits.max_mentions:
        return skip(TOO_MANY_MENTIONS, f"{mentions}/{limits.max_mentions} @mentions")
    if document is not None:
        return _plan_document(account, text, document, image_count)
    if image_count and not limits.max_images:
        return skip(IMAGES_NOT_SUPPORTED, f"{name} posts text only")
    if image_count > limits.max_images:
        return skip(TOO_MANY_IMAGES, f"{image_count}/{limits.max_images} images")
    if limits.requires_image and not image_count:
        return skip(IMAGE_REQUIRED, f"{name} needs an image")
    return TargetPlan(account, text)


def _plan_document(account: SocialAccount, text: str, document: DocumentFacts, image_count: int) -> TargetPlan:
    """A document post: the network must take documents, this kind of file, at this size, and nothing else with it."""
    network = network_for(account.network)
    accepted = network.limits.documents

    def skip(reason: str, detail: str) -> TargetPlan:
        return TargetPlan(account, text, reason, detail)

    if accepted is None:
        return skip(DOCUMENTS_NOT_SUPPORTED, f"{network.display_name} can't post documents")
    if image_count:
        return skip(DOCUMENT_WITH_IMAGES, "A post carries a document or images, not both")
    if extension(document.filename) not in accepted.formats:
        formats = ", ".join(suffix[1:].upper() for suffix in accepted.formats)
        return skip(DOCUMENT_TYPE_NOT_SUPPORTED, f"{network.display_name} takes {formats} documents")
    if document.size_bytes > accepted.max_bytes:
        return skip(DOCUMENT_TOO_LARGE, f"{megabytes(document.size_bytes)}/{megabytes(accepted.max_bytes)}")
    return TargetPlan(account, text)
