"""In-process crawls resume their own checkpoints, since no Lambda continues them."""

from types import SimpleNamespace
from unittest.mock import patch

from src.knowledge.models import CrawlCheckpoint, CrawlJobStatus
from src.knowledge.crawl_launch import run_crawl_in_background
from src.crawler.worker import CrawlerWorker


class ScriptedCrawler:
    """Returns the scripted job states one run at a time."""

    def __init__(self, *jobs: SimpleNamespace):
        self.jobs = list(jobs)
        self.runs = 0

    async def run(self, **_: object) -> SimpleNamespace:
        self.runs += 1
        return self.jobs.pop(0)


def _job(status: CrawlJobStatus, checkpoint_index: int | None = None) -> SimpleNamespace:
    checkpoint = None if checkpoint_index is None else CrawlCheckpoint(current_url_index=checkpoint_index)
    return SimpleNamespace(status=status, checkpoint=checkpoint)


async def test_resumes_checkpointed_job_until_complete() -> None:
    crawler = ScriptedCrawler(
        _job(CrawlJobStatus.IN_PROGRESS, checkpoint_index=3),
        _job(CrawlJobStatus.IN_PROGRESS, checkpoint_index=9),
        _job(CrawlJobStatus.COMPLETED),
    )

    await run_crawl_in_background("job-1", "kb-1", "user@example.com", crawler)

    assert crawler.runs == 3


async def test_stops_when_job_is_no_longer_in_progress() -> None:
    crawler = ScriptedCrawler(_job(CrawlJobStatus.CANCELLED, checkpoint_index=3))

    await run_crawl_in_background("job-1", "kb-1", "user@example.com", crawler)

    assert crawler.runs == 1


def test_continuation_does_not_invoke_lambda_for_in_process_crawls(monkeypatch) -> None:
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.setattr("src.crawler.worker.settings.async_job_backend", "local")
    monkeypatch.setattr("src.crawler.worker.settings.async_job_lambda_name", "crawl-worker")

    with patch("src.crawler.worker.boto3.client") as lambda_client:
        CrawlerWorker()._invoke_continuation("job-1", "kb-1", "user@example.com")

    lambda_client.assert_not_called()
