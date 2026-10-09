from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Mapping, Optional
from uuid import uuid4

from src.blueprints.commands import Command, Reversibility, Undo, Use, undo_action
from src.blueprints.issues import BlueprintIssue
from src.blueprints.reconcile import Outcome
from src.blueprints.kinds.base import (
    Action,
    AppliedResource,
    ApplyContext,
    Change,
    Existing,
    ManagedKind,
    NotFound,
    PlanContext,
    Usage,
)
from src.blueprints.spec import CrawlSpec, KnowledgeBaseSpec
from src.config import settings
from src.knowledge.crawl_launch import launch_crawl
from src.knowledge.models import CrawlConfig, CrawlJob, CrawlSourceType, KnowledgeBase, KnowledgeBaseStatus
from src.knowledge.repository import AgentKnowledgeBaseRepository, CrawlJobRepository, KnowledgeBaseRepository
from src.knowledge.service import get_knowledge_base_service

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


def _applied(name: str, kb: KnowledgeBase) -> AppliedResource:
    return AppliedResource(name=name, kind="KnowledgeBase", id=kb.kb_id, attributes={"id": kb.kb_id, "name": kb.name})


# --- Commands -----------------------------------------------------------------------------------------------


@dataclass(kw_only=True)
class CreateKnowledgeBase(Command):
    kb_name: str
    description: Optional[str]
    #: Chosen when it's prepared, so the undo knows it even if the apply stops before the create returns.
    kb_id: str = ""

    reversibility: ClassVar[Reversibility] = Reversibility.COMPENSATABLE
    establishes: ClassVar[bool] = True
    creates: ClassVar[bool] = True

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        self.kb_id = self.kb_id or str(uuid4())
        return Undo("delete_new_knowledge_base", {"kb_id": self.kb_id})

    def run(self, ctx: ApplyContext) -> None:
        kb = KnowledgeBaseRepository().save(
            KnowledgeBase(kb_id=self.kb_id, name=self.kb_name, description=self.description, created_by=ctx.user_email)
        )
        ctx.applied[self.resource] = _applied(self.resource, kb)


@undo_action("delete_new_knowledge_base")
def _delete_new_knowledge_base(args: dict[str, Any], user_email: str) -> None:
    # Crawls start only after the commit point, so a new knowledge base has no content to clean up.
    if KnowledgeBaseRepository().find_by_id(args["kb_id"], user_email):
        KnowledgeBaseRepository().soft_delete(args["kb_id"], user_email)


@dataclass(kw_only=True)
class SaveKnowledgeBase(Command):
    kb_id: str
    fields: dict[str, Any]

    establishes: ClassVar[bool] = True

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        current = KnowledgeBaseRepository().find_by_id(self.kb_id, ctx.user_email)
        before = {key: getattr(current, key) for key in self.fields} if current else {}
        return Undo("restore_knowledge_base", {"kb_id": self.kb_id, "fields": before})

    def run(self, ctx: ApplyContext) -> None:
        ctx.applied[self.resource] = _applied(self.resource, _save_fields(self.kb_id, self.fields, ctx.user_email))


def _save_fields(kb_id: str, fields: dict[str, Any], user_email: str) -> KnowledgeBase:
    current = KnowledgeBaseRepository().find_by_id(kb_id, user_email)
    if current is None:
        raise RuntimeError("The knowledge base was deleted since the plan. Plan again.")
    return KnowledgeBaseRepository().save(current.model_copy(update=fields))


@undo_action("restore_knowledge_base")
def _restore_knowledge_base(args: dict[str, Any], user_email: str) -> None:
    if args["fields"]:
        _save_fields(args["kb_id"], args["fields"], user_email)


@dataclass(kw_only=True)
class StartCrawl(Command):
    """Reading a site spends the plan's page allowance and can't be taken back, so it runs after the commit point."""

    crawl: CrawlSpec

    reversibility: ClassVar[Reversibility] = Reversibility.IRREVERSIBLE

    def run(self, ctx: ApplyContext) -> None:
        applied = ctx.applied[self.resource]
        job = CrawlJobRepository().save(CrawlJob(
            kb_id=applied.id,
            config=CrawlConfig(
                source_type=CRAWL_SOURCE[self.crawl.mode],
                source_url=self.crawl.url,
                max_pages=self.crawl.max_pages,
                max_depth=self.crawl.max_depth,
            ),
            created_by=ctx.user_email,
        ))
        applied.attributes["crawl_job_id"] = job.job_id
        launch_crawl(job.job_id, applied.id, ctx.user_email, ctx.background_tasks)


@dataclass(kw_only=True)
class DeleteKnowledgeBase(Command):
    kb_id: str

    reversibility: ClassVar[Reversibility] = Reversibility.IRREVERSIBLE
    deletes: ClassVar[bool] = True

    def run(self, ctx: ApplyContext) -> None:
        # The same delete as the dashboard's: vectors and chunks go, and it's disconnected from every agent.
        result = get_knowledge_base_service().soft_delete(self.kb_id, ctx.user_email)
        if not result.success:
            raise RuntimeError(result.error or "The knowledge base couldn't be deleted.")


# --- The kind -----------------------------------------------------------------------------------------------


class KnowledgeBaseKind(ManagedKind[KnowledgeBaseSpec]):
    kind = "KnowledgeBase"
    label = "Knowledge base"
    use_when = "The agent should answer from a website or other content: learn my site, answer from our docs or FAQ."
    deletes = "its content is deleted, and every agent using it loses it"
    spec_model = KnowledgeBaseSpec
    exposes = ("id", "name", "crawl_job_id")
    feeds = "knowledge for"
    dashboard_path = "/dashboard/knowledge-bases/{id}"
    export_name = "knowledge"

    def observe(self, record: KnowledgeBase, names: Mapping[str, str]) -> dict[str, Any]:
        resource: dict[str, Any] = {"kind": self.kind, "id": record.kb_id, "name": record.name}
        if record.description:
            resource["description"] = record.description
        crawl = last_crawl(record.kb_id)
        if crawl:
            resource["crawl"] = crawl.model_dump()
        return resource

    def applied(self, name: str, record: KnowledgeBase) -> AppliedResource:
        return _applied(name, record)

    def card_details(self, spec: KnowledgeBaseSpec) -> list[str]:
        if not spec.crawl:
            return ["Empty, ready for content"]
        return [f"Reads {spec.crawl.url}", f"Up to {spec.crawl.max_pages} pages"]

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
            return Existing(id=kb.kb_id, record=kb, matched_by="id")
        same_name = [kb for kb in repo.find_all_by_user(ctx.user_email) if kb.name == spec.name]
        if len(same_name) != 1:
            # None to match, or several and no way to tell which: create a new one.
            return None
        kb = same_name[0]
        return Existing(id=kb.kb_id, record=kb, matched_by="name")

    def commands(
        self, name: str, spec: KnowledgeBaseSpec, existing: Optional[Existing], outcome: Outcome, ctx: PlanContext
    ) -> list[Command]:
        if existing is None:
            crawl = [StartCrawl(resource=name, crawl=spec.crawl)] if spec.crawl else []
            return [CreateKnowledgeBase(resource=name, kb_name=spec.name, description=spec.description), *crawl]
        kb: KnowledgeBase = existing.record
        fields = outcome.values(KnowledgeBaseSpec)
        says = tuple(change.says for change in outcome.sets if change.says and change.field != "crawl")
        commands: list[Command] = (
            [SaveKnowledgeBase(resource=name, kb_id=kb.kb_id, fields=fields, says=says)]
            if fields else [Use(resource=name, applied=_applied(name, kb))]
        )
        if spec.crawl and outcome.sets_field("crawl"):
            said = next(change.says for change in outcome.sets if change.field == "crawl")
            commands.append(StartCrawl(resource=name, crawl=spec.crawl, says=(said,) if said else ()))
        return commands

    def delete_blockers(self, name: str, existing: Existing, kit_ids: set[str]) -> list[BlueprintIssue]:
        outside = [link.agent_id for link in AgentKnowledgeBaseRepository().find_agents_for_kb(existing.id)
                   if link.agent_id not in kit_ids]
        if not outside:
            return []
        return [BlueprintIssue(
            path=f"resources.{name}",
            message=f"'{existing.record.name}' is also used by {len(outside)} agent(s) outside this kit, so it can't "
            "be deleted with it.",
            hint="Keep it in the blueprint, or disconnect it from those agents first.",
        )]

    def delete_commands(
        self, name: str, spec: KnowledgeBaseSpec, existing: Existing, removal: str
    ) -> list[Command]:
        return [DeleteKnowledgeBase(resource=name, kb_id=existing.id, removal=removal)]

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
        if change.action == Action.CREATE or change.existing is None:
            return True
        return spec.crawl.model_dump() != change.existing.observed.get("crawl")

    def describe(self, name: str, spec: KnowledgeBaseSpec) -> str:
        if spec.crawl:
            return f"Create knowledge base '{spec.name}' and read up to {spec.crawl.max_pages} pages from {spec.crawl.url}"
        return f"Create empty knowledge base '{spec.name}'"
