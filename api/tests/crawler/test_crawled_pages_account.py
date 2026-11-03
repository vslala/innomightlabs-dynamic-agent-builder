"""A crawled page says which account it was charged to, so the usage stream can bill the account's owner."""

from src.knowledge.repository import CrawledPageRepository
from tests.crawler.fakes import SITE, a_crawl, paragraphs


async def test_crawled_pages_record_the_account_they_belong_to(dynamodb_table, monkeypatch):
    crawl = a_crawl(monkeypatch)
    crawl.site.publish(f"{SITE}/pricing", paragraphs(4))

    job = await crawl.crawl()

    pages, _ = CrawledPageRepository().find_all_by_job(job.job_id)
    assert pages, "the crawl saved a page record"
    assert {page.account_id for page in pages} == {crawl.kb.account_id}
