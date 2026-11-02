from __future__ import annotations

from typing import Any
from uuid import uuid4, uuid5, NAMESPACE_URL

from src.connectors.social.models import SocialAccount
from src.connectors.social.networks import network_for
from src.connectors.social.networks.base import PublishError, PublishErrorKind
from src.connectors.social.publisher import PublishRequest, SocialPublisher
from src.connectors.social.repository import SocialAccountRepository
from src.consent.preview import FieldsBlock, ImagesBlock, PreviewField, PreviewImage, PreviewTarget, TargetsBlock, TextBlock
from src.skills.runtime_context import account_of

from .images import load_images, resolve_images

RECENT_POSTS_DEFAULT = 10
RECENT_POSTS_MAX = 25
#: Per post, so ten long posts can't flood the agent's context
RECENT_POST_TEXT_MAX = 2000


async def accounts(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del arguments, config
    connected = SocialAccountRepository().list(account_of(context))
    return {"accounts": [_describe(account) for account in connected]}


async def check(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del config
    plans = SocialPublisher().plan(
        account_of(context), str(arguments.get("text") or ""), selection=arguments.get("accounts", "all"),
        network=_network(arguments), overrides=_overrides(arguments), image_count=len(resolve_images(arguments, context)),
    )
    return {"targets": [
        {"social_account_id": plan.account.social_account_id, "network": plan.account.network, "handle": plan.account.handle,
         "can_post": plan.ok, **({"reason": plan.reason, "detail": plan.detail} if plan.reason else {})}
        for plan in plans
    ]}


async def publish(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del config
    request = PublishRequest(
        account_id=account_of(context), post_id=_post_id(context), text=str(arguments.get("text") or "").strip(),
        accounts=arguments.get("accounts", "all"), network=_network(arguments), overrides=_overrides(arguments),
        images=load_images(resolve_images(arguments, context)),
    )
    result = await SocialPublisher().publish(request)
    if result["status"] == "failed" and context.get("orchestrator_type") == "automation":
        # An automation step fails when nothing was posted, so its error path can react (for example, email the owner)
        reasons = "; ".join(f"{target['network']}: {target.get('detail') or target['status']}" for target in result["targets"])
        raise RuntimeError(f"Nothing was posted. {reasons}")
    return result


async def recent_posts(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """The account's own newest posts, so the agent doesn't repeat itself. Read-only, so it asks no consent."""
    del config
    account = SocialAccountRepository().get(account_of(context), str(arguments.get("social_account_id") or ""))
    if account is None:
        raise ValueError("No connected social account with that social_account_id. Call accounts for the ids.")
    network = network_for(account.network)
    if not network.reads_posts:
        return {"supported": False, "posts": [], "reason": f"{network.display_name} doesn't let apps read posts"}
    limit = max(1, min(int(arguments.get("limit") or RECENT_POSTS_DEFAULT), RECENT_POSTS_MAX))
    try:
        posts = await network.recent_posts(account.credentials(), limit)
    except PublishError as error:
        if error.kind == PublishErrorKind.AUTH:
            SocialAccountRepository().mark_needs_reconnect(account, str(error))
        raise ValueError(str(error)) from error
    return {"supported": True, "posts": [
        {"posted_at": post.posted_at.isoformat(), "text": post.text[:RECENT_POST_TEXT_MAX], "url": post.url,
         "media": post.media}
        for post in posts
    ]}


async def publish_preview(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """What the person approves before `publish`: the post, its images, and which accounts it goes to, or why not."""
    del config
    text = str(arguments.get("text") or "").strip()
    images = resolve_images(arguments, context)
    overrides = _overrides(arguments)
    plans = SocialPublisher().plan(
        account_of(context), text, selection=arguments.get("accounts", "all"), network=_network(arguments),
        overrides=overrides, image_count=len(images),
    )
    blocks: list[Any] = [TextBlock(label="Post", value=text, argument="text")]
    if images:
        blocks.append(ImagesBlock(items=[PreviewImage(s3_key=image.s3_key, alt_text=image.alt_text or None) for image in images]))
    blocks.append(TargetsBlock(items=[
        PreviewTarget(
            label=f"{network_for(plan.account.network).display_name} · {plan.account.handle}",
            will_run=plan.ok,
            reason=None if plan.ok else (plan.detail or plan.reason),
        )
        for plan in plans
    ]))
    if overrides:
        blocks.append(FieldsBlock(label="Different text for", items=[PreviewField(label=key, value=value) for key, value in overrides.items()]))
    return {"blocks": [block.model_dump() for block in blocks]}


def _post_id(context: dict[str, Any]) -> str:
    """One post per automation step, so a retried step finds what the first try did. A chat call is its own post."""
    run_id, node_id = context.get("automation_run_id"), context.get("automation_node_id")
    return str(uuid5(NAMESPACE_URL, f"social-post:{run_id}:{node_id}")) if run_id and node_id else str(uuid4())


def _network(arguments: dict[str, Any]) -> str | None:
    network = str(arguments.get("network") or "").strip().lower()
    if network:
        network_for(network)  # an unknown network is a clear error, not an empty selection
    return network or None


def _overrides(arguments: dict[str, Any]) -> dict[str, str]:
    overrides = arguments.get("overrides") or {}
    if not isinstance(overrides, dict):
        raise ValueError("overrides must be an object of text by network or social_account_id")
    return {str(key): str(value) for key, value in overrides.items()}


def _describe(account: SocialAccount) -> dict[str, Any]:
    network = network_for(account.network)
    return {
        "social_account_id": account.social_account_id,
        "network": account.network,
        "handle": account.handle,
        "status": account.effective_status().value,
        "max_characters": network.limits.max_text,
        "max_images": network.limits.max_images,
        "requires_image": network.limits.requires_image,
        "reads_posts": network.reads_posts,
        **({"token_expires_at": account.token_expires_at.isoformat()} if account.token_expires_at else {}),
    }
