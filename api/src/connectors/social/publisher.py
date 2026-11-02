"""Publish one post to several connected accounts. Each account is one independent target: one failing doesn't stop the
others, and each is claimed before the network is called so a retry can't post it twice."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.connectors.social.models import SocialAccount
from src.connectors.social.media import SourceImage
from src.connectors.social.networks import network_for
from src.connectors.social.networks.base import PreparedPost, PublishError, PublishErrorKind, SocialNetwork
from src.connectors.social.planning import TargetPlan, plan_targets, select_accounts
from src.connectors.social.posts import PostTarget, SocialPostRepository, TargetStatus
from src.connectors.social.renditions import Renditions
from src.connectors.social.repository import SocialAccountRepository
from src.crypto import encrypt

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishRequest:
    account_id: str
    #: One post is one id: the same id again returns what the first call did instead of posting again
    post_id: str
    text: str
    accounts: Any = "all"
    network: str | None = None
    overrides: dict[str, str] = field(default_factory=dict)
    images: tuple[SourceImage, ...] = ()


class SocialPublisher:
    def __init__(self, accounts: SocialAccountRepository | None = None, posts: SocialPostRepository | None = None) -> None:
        self.accounts = accounts or SocialAccountRepository()
        self.posts = posts or SocialPostRepository()

    def plan(self, account_id: str, text: str, *, selection: Any = "all", network: str | None = None,
             overrides: dict[str, str] | None = None, image_count: int = 0) -> list[TargetPlan]:
        accounts = select_accounts(self.accounts.list(account_id), selection, network)
        return plan_targets(accounts, text, overrides, image_count)

    async def publish(self, request: PublishRequest) -> dict[str, Any]:
        plans = self.plan(request.account_id, request.text, selection=request.accounts, network=request.network,
                          overrides=request.overrides, image_count=len(request.images))
        if not plans:
            raise ValueError("No connected social account matches. Connect one in Connectors, on the Social tab.")
        renditions = Renditions(request.account_id, request.post_id, request.images)
        targets = await asyncio.gather(*(self._publish_target(request, plan, renditions) for plan in plans))
        published = [target for target in targets if target.status == TargetStatus.PUBLISHED]
        status = "failed" if not published else "published" if len(published) == len(targets) else "partial"
        return {"post_id": request.post_id, "status": status, "targets": [target.to_result() for target in targets]}

    async def fresh(self, account: SocialAccount, network: SocialNetwork) -> dict[str, Any]:
        """The account's credentials, its token renewed and saved first when the network says it is time (Threads).
        Raises PublishError(AUTH) when the network refuses to renew it."""
        credentials = account.credentials()
        refreshed = await network.fresh_credentials(credentials)
        if refreshed is None:
            return credentials
        self.accounts.update_credentials(account, encrypt(json.dumps(refreshed.credentials)), refreshed.expires_at)
        return refreshed.credentials

    async def _publish_target(self, request: PublishRequest, plan: TargetPlan, renditions: Renditions) -> PostTarget:
        account = plan.account
        target = PostTarget(account_id=account.account_id, post_id=request.post_id,
                            social_account_id=account.social_account_id, network=account.network,
                            handle=account.handle, status=TargetStatus.PUBLISHING)
        if not plan.ok:
            return target.model_copy(update={"status": TargetStatus.SKIPPED, "reason": plan.reason or "", "detail": plan.detail})
        claimed = self.posts.claim(target)
        if claimed is None:
            return self._already(self.posts.get(target))
        network = network_for(account.network)
        try:
            images = renditions.for_network(network)
            credentials = await self.fresh(account, network)
            published = await network.publish(credentials, PreparedPost(text=plan.text, images=images))
        except PublishError as error:
            return self._failed(claimed, account, error)
        except Exception:  # a network strategy's own bug must not take the other accounts down, nor leave this one locked
            log.exception("Publishing to %s failed unexpectedly", account.network)
            return self.posts.finish(claimed, TargetStatus.UNCERTAIN, reason=PublishErrorKind.UNCERTAIN.value,
                                     detail="Something went wrong while posting, so the post may exist")
        return self.posts.finish(claimed, TargetStatus.PUBLISHED, url=published.url, external_id=published.external_id)

    def _failed(self, target: PostTarget, account: SocialAccount, error: PublishError) -> PostTarget:
        if error.kind == PublishErrorKind.AUTH:
            self.accounts.mark_needs_reconnect(account, str(error))
        status = TargetStatus.UNCERTAIN if error.kind == PublishErrorKind.UNCERTAIN else TargetStatus.FAILED
        return self.posts.finish(target, status, reason=error.kind.value, detail=str(error))

    @staticmethod
    def _already(existing: PostTarget) -> PostTarget:
        """A target in flight when the process died stays unknown: it might be on the network."""
        if existing.status == TargetStatus.PUBLISHING:
            return existing.model_copy(update={"status": TargetStatus.UNCERTAIN, "reason": PublishErrorKind.UNCERTAIN.value,
                                               "detail": "An earlier attempt did not finish, so the post may exist"})
        return existing
