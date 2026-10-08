from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds.base import AppliedResource, ApplyContext, PlanContext, ResourceKind, Usage
from src.blueprints.spec import KnowledgeBaseSpec
from src.config import settings
from src.knowledge.crawl_launch import launch_crawl
from src.knowledge.models import CrawlConfig, CrawlJob, CrawlSourceType, KnowledgeBase
from src.knowledge.repository import CrawlJobRepository, KnowledgeBaseRepository

CRAWL_SOURCE = {"site": CrawlSourceType.URL, "sitemap": CrawlSourceType.SITEMAP}


class KnowledgeBaseKind(ResourceKind[KnowledgeBaseSpec]):
    kind = "KnowledgeBase"
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

    def check(self, name: str, spec: KnowledgeBaseSpec, ctx: PlanContext) -> list[BlueprintIssue]:
        if not spec.crawl:
            return []
        try:
            settings.require_pinecone()
        except Exception:
            return [BlueprintIssue(
                path=f"resources.{name}.crawl",
                message="Reading websites into knowledge bases isn't available right now.",
            )]
        return []

    def usage(self, spec: KnowledgeBaseSpec) -> Usage:
        return Usage(kb_pages=spec.crawl.max_pages if spec.crawl else 0)

    def describe(self, name: str, spec: KnowledgeBaseSpec) -> str:
        if spec.crawl:
            return f"Create knowledge base '{spec.name}' and read up to {spec.crawl.max_pages} pages from {spec.crawl.url}"
        return f"Create empty knowledge base '{spec.name}'"

    def apply(self, name: str, spec: KnowledgeBaseSpec, ctx: ApplyContext) -> AppliedResource:
        kb = KnowledgeBaseRepository().save(
            KnowledgeBase(name=spec.name, description=spec.description, created_by=ctx.user_email)
        )
        return AppliedResource(name=name, kind=self.kind, id=kb.kb_id, attributes={"id": kb.kb_id, "name": kb.name})

    def start(self, applied: AppliedResource, spec: KnowledgeBaseSpec, ctx: ApplyContext) -> None:
        if not spec.crawl:
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
