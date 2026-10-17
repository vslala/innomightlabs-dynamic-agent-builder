"""Reading a knowledge base's site again, with the settings it was last read with.

What an automation's `recrawl` step does. The crawler re-embeds only the chunks that changed (`crawler/page_chunks.py`),
so a schedule that reads an unchanged site costs the fetches and nothing else.
"""

from dataclasses import dataclass
from typing import Optional

from src.accounts.owner import Owner
from src.knowledge.access import owned_kb
from src.knowledge.crawl_launch import launch_crawl
from src.knowledge.models import CrawlJob, CrawlJobStatus
from src.knowledge.repository import CrawlJobRepository

#: How many of the newest jobs to look through for one still running.
RECENT_JOBS = 5


@dataclass(frozen=True)
class Recrawl:
    started: bool
    #: Why it didn't start, or what it started; written for the person reading a run.
    message: str
    job_id: Optional[str] = None


def recrawl(kb_id: str, owner: Owner) -> Recrawl:
    """Start a crawl of the knowledge base, unless one is already running or it was never read from a site."""
    kb = owned_kb(kb_id, owner)
    if kb is None:
        raise ValueError("Knowledge base not found")
    jobs = CrawlJobRepository().find_all_by_kb(kb.kb_id, limit=50)
    if not jobs:
        return Recrawl(False, f"{kb.name} has never been crawled, so there is no site to read again.")
    running = next((job for job in jobs[:RECENT_JOBS] if job.status in (CrawlJobStatus.PENDING, CrawlJobStatus.IN_PROGRESS)), None)
    if running:
        return Recrawl(False, f"{kb.name} is already being crawled; skipped this time.", running.job_id)
    job = CrawlJobRepository().save(CrawlJob(kb_id=kb.kb_id, config=jobs[0].config, created_by=owner.user_id))
    launch_crawl(job.job_id, kb.kb_id, kb.account_id)
    return Recrawl(True, f"Started reading {jobs[0].config.source_url} again for {kb.name}.", job.job_id)
