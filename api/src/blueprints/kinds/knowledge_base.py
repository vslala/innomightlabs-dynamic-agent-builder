from typing import Literal, Optional

from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds.base import (
    Action,
    AppliedResource,
    ApplyContext,
    Change,
    Existing,
    NotFound,
    PlanContext,
    ResourceKind,
    Usage,
)
from src.blueprints.spec import CrawlSpec, KnowledgeBaseSpec
from src.config import settings
from src.knowledge.crawl_launch import launch_crawl
from src.knowledge.models import CrawlConfig, CrawlJob, CrawlSourceType, KnowledgeBase, KnowledgeBaseStatus
from src.knowledge.repository import CrawlJobRepository, KnowledgeBaseRepository

CRAWL_SOURCE = {"site": CrawlSourceType.URL, "sitemap": CrawlSourceType.SITEMAP}
CRAWL_MODE: dict[CrawlSourceType, Literal["site", "sitemap"]] = {CrawlSourceType.URL: "site", CrawlSourceType.SITEMAP: "sitemap"}


def last_crawl(kb_id: str) -> Optional[CrawlSpec]:
    """The settings the knowledge base was last read with, as a blueprint would write them."""
    # Job keys are ids, not times, so fetch a batch; the repository sorts it newest first.
    jobs = CrawlJobRepository().find_all_by_kb(kb_id, limit=50)
    if not jobs:
        return None
    config = jobs[0].config
    return CrawlSpec(
        url=config.source_url,
        mode=CRAWL_MODE.get(config.source_type, "site"),
        max_pages=config.max_pages,
        max_depth=config.max_depth,
    )


class KnowledgeBaseKind(ResourceKind[KnowledgeBaseSpec]):
    kind = "KnowledgeBase"
    label = "Knowledge base"
    spec_model = KnowledgeBaseSpec
    exposes = ("id", "name", "crawl_job_id")

    def validate(self, name: str, spec: KnowledgeBaseSpec) -> list[BlueprintIssue]:
        if spec.crawl and "{{" not in spec.crawl.url and not spec.crawl.url.startswith(("http://", "https://")):
            return [BlueprintIssue(
                path=f"resources.{name}.crawl.url",
                message=f"'{spec.crawl.url}' isn't a web address.",
                hint="Start it with https://.",
            )]
        return []

    def find_existing(self, name: str, spec: KnowledgeBaseSpec, ctx: PlanContext) -> Optional[Existing]:
        repo = KnowledgeBaseRepository()
        if spec.id:
            kb = repo.find_by_id(spec.id, ctx.user_email)
            if not kb or kb.status == KnowledgeBaseStatus.DELETED:
                raise NotFound(f"There's no knowledge base with id '{spec.id}' in your account.")
            return Existing(id=kb.kb_id, record=kb, matched_by="id", related={"crawl": last_crawl(kb.kb_id)})
        same_name = [kb for kb in repo.find_all_by_user(ctx.user_email) if kb.name == spec.name]
        if len(same_name) != 1:
            # None to match, or several and no way to tell which: create a new one.
            return None
        kb = same_name[0]
        return Existing(id=kb.kb_id, record=kb, matched_by="name", related={"crawl": last_crawl(kb.kb_id)})

    def differences(self, name: str, spec: KnowledgeBaseSpec, existing: Existing, ctx: PlanContext) -> list[str]:
        kb: KnowledgeBase = existing.record
        changes = []
        if spec.name != kb.name:
            changes.append(f"rename to '{spec.name}'")
        if spec.description is not None and spec.description != kb.description:
            changes.append("update its description")
        if spec.crawl and spec.crawl != existing.related.get("crawl"):
            changes.append(f"read {spec.crawl.url} again, up to {spec.crawl.max_pages} pages")
        return changes

    def check(self, name: str, spec: KnowledgeBaseSpec, change: Change, ctx: PlanContext) -> list[BlueprintIssue]:
        if not self._crawls(spec, change):
            return []
        try:
            settings.require_pinecone()
        except Exception:
            return [BlueprintIssue(
                path=f"resources.{name}.crawl",
                message="Reading websites into knowledge bases isn't available right now.",
            )]
        return []

    def usage(self, spec: KnowledgeBaseSpec, change: Change) -> Usage:
        return Usage(kb_pages=spec.crawl.max_pages if spec.crawl and self._crawls(spec, change) else 0)

    @staticmethod
    def _crawls(spec: KnowledgeBaseSpec, change: Change) -> bool:
        if not spec.crawl or change.action == Action.UNCHANGED:
            return False
        return change.action == Action.CREATE or spec.crawl != change.existing.related.get("crawl")  # type: ignore[union-attr]

    def describe(self, name: str, spec: KnowledgeBaseSpec) -> str:
        if spec.crawl:
            return f"Create knowledge base '{spec.name}' and read up to {spec.crawl.max_pages} pages from {spec.crawl.url}"
        return f"Create empty knowledge base '{spec.name}'"

    def apply(self, name: str, spec: KnowledgeBaseSpec, ctx: ApplyContext) -> AppliedResource:
        kb = KnowledgeBaseRepository().save(
            KnowledgeBase(name=spec.name, description=spec.description, created_by=ctx.user_email)
        )
        return self._applied(name, kb, needs_start=bool(spec.crawl))

    def update(self, name: str, spec: KnowledgeBaseSpec, change: Change, ctx: ApplyContext) -> AppliedResource:
        previous: KnowledgeBase = change.existing.record  # type: ignore[union-attr]
        updated = previous.model_copy(update={
            "name": spec.name,
            "description": spec.description if spec.description is not None else previous.description,
        })
        kb = KnowledgeBaseRepository().save(updated)
        applied = self._applied(name, kb, needs_start=self._crawls(spec, change))
        applied.previous = previous
        return applied

    def kept(self, name: str, change: Change) -> AppliedResource:
        return self._applied(name, change.existing.record, needs_start=False)  # type: ignore[union-attr]

    def _applied(self, name: str, kb: KnowledgeBase, *, needs_start: bool) -> AppliedResource:
        return AppliedResource(
            name=name, kind=self.kind, id=kb.kb_id, attributes={"id": kb.kb_id, "name": kb.name}, needs_start=needs_start
        )

    def start(self, applied: AppliedResource, spec: KnowledgeBaseSpec, ctx: ApplyContext) -> None:
        if not spec.crawl or not applied.needs_start:
            return
        job = CrawlJobRepository().save(CrawlJob(
            kb_id=applied.id,
            config=CrawlConfig(
                source_type=CRAWL_SOURCE[spec.crawl.mode],
                source_url=spec.crawl.url,
                max_pages=spec.crawl.max_pages,
                max_depth=spec.crawl.max_depth,
            ),
            created_by=ctx.user_email,
        ))
        applied.attributes["crawl_job_id"] = job.job_id
        launch_crawl(job.job_id, applied.id, ctx.user_email, ctx.background_tasks)

    def rollback(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        # Crawls start only after every resource exists, so there are no vectors to clean up here.
        KnowledgeBaseRepository().soft_delete(applied.id, ctx.user_email)

    def restore(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        KnowledgeBaseRepository().save(applied.previous)
