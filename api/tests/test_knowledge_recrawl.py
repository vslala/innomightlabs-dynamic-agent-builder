"""Reading a knowledge base's site again on a schedule: the `recrawl` action and the automation that runs it."""

import pytest

from src.automations.models import AutomationTriggerType
from src.automations.repository import AutomationRepository
from src.blueprints import service as blueprints_service
from src.blueprints.kinds.automation import read_chain
from src.blueprints.models import DeploymentStatus  # noqa: F401
from src.knowledge.models import CrawlConfig, CrawlJob, CrawlJobStatus, CrawlSourceType, KnowledgeBase
from src.knowledge.recrawl import recrawl
from src.knowledge.repository import CrawlJobRepository, KnowledgeBaseRepository
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.knowledge_base.actions import recrawl as recrawl_action
from tests.mock_data import TEST_USER_EMAIL, account_for, kb_fields
from tests.mock_data import test_owner as _test_owner

OWNER = _test_owner()

BLUEPRINT = """
apiVersion: innomight/v2
kind: Blueprint
metadata: {name: fresh-docs, title: Fresh docs}
resources:
  docs:
    kind: KnowledgeBase
    name: Docs
    crawl: {url: "https://docs.acme.example", mode: site, max_pages: 10}
  refresh_docs:
    kind: Automation
    title: Refresh the docs
    enabled: true
    trigger:
      schedule: {cron: "0 3 * * 1", timezone: UTC}
    skills:
      - id: knowledge_base
    steps:
      - name: refresh
        skill: knowledge_base
        action: recrawl
        arguments: {knowledge_base_id: docs}
"""


@pytest.fixture(autouse=True)
def launched(dynamodb_table, monkeypatch) -> list[str]:
    """The crawls started: none really run."""
    jobs: list[str] = []
    for place in ("src.knowledge.recrawl.launch_crawl", "src.blueprints.kinds.knowledge_base.launch_crawl"):
        monkeypatch.setattr(place, lambda job_id, *args, **kwargs: jobs.append(job_id))
    return jobs


def a_crawled_kb(status: CrawlJobStatus = CrawlJobStatus.COMPLETED) -> KnowledgeBase:
    kb = KnowledgeBaseRepository().save(KnowledgeBase(name="Docs", **kb_fields(TEST_USER_EMAIL)))
    CrawlJobRepository().save(CrawlJob(
        kb_id=kb.kb_id, status=status, created_by=OWNER.user_id,
        config=CrawlConfig(source_type=CrawlSourceType.URL, source_url="https://docs.acme.example", max_pages=7, max_depth=2),
    ))
    return kb


def test_it_reads_the_site_again_with_the_settings_it_was_read_with(launched):
    kb = a_crawled_kb()

    result = recrawl(kb.kb_id, OWNER)

    assert result.started and launched == [result.job_id]
    job = CrawlJobRepository().find_by_id(result.job_id, kb.kb_id)
    assert job is not None and job.status == CrawlJobStatus.PENDING
    assert (job.config.source_url, job.config.max_pages, job.config.max_depth) == ("https://docs.acme.example", 7, 2)


@pytest.mark.parametrize("status", [CrawlJobStatus.PENDING, CrawlJobStatus.IN_PROGRESS])
def test_it_does_not_start_a_second_crawl_while_one_runs(launched, status):
    kb = a_crawled_kb(status)

    result = recrawl(kb.kb_id, OWNER)

    assert not result.started and "already being crawled" in result.message
    assert launched == [] and len(CrawlJobRepository().find_all_by_kb(kb.kb_id)) == 1


def test_a_knowledge_base_that_was_never_crawled_has_no_site_to_read_again(launched):
    kb = KnowledgeBaseRepository().save(KnowledgeBase(name="Uploads", **kb_fields(TEST_USER_EMAIL)))

    result = recrawl(kb.kb_id, OWNER)

    assert not result.started and "never been crawled" in result.message and launched == []


def test_it_reads_only_the_owners_own_knowledge_bases(launched):
    kb = a_crawled_kb()
    other = _test_owner("someone-else@example.com")

    with pytest.raises(ValueError, match="not found"):
        recrawl(kb.kb_id, other)
    assert launched == []


async def test_the_skill_action_runs_as_the_automations_owner(launched):
    kb = a_crawled_kb()
    context = {"account_id": OWNER.account_id, "owner_id": OWNER.user_id, "owner_email": OWNER.email}

    result = await recrawl_action({"knowledge_base_id": kb.kb_id}, {}, context)

    assert result["started"] is True and launched == [result["job_id"]]


def test_a_blueprint_schedules_the_knowledge_base_it_builds(launched):
    ProviderSettingsRepository().save(
        ProviderSettings(account_id=account_for(TEST_USER_EMAIL), provider_name="Bedrock", encrypted_credentials="{}")
    )

    deployed = blueprints_service.deploy_blueprint(BLUEPRINT, {}, OWNER)

    assert isinstance(deployed, blueprints_service.Deployed), getattr(deployed, "issues", None) or deployed.plan.blockers
    [kb] = KnowledgeBaseRepository().list_in_account(OWNER.account_id)
    [automation] = AutomationRepository().list_in_account(OWNER.account_id)
    chain = read_chain(*AutomationRepository().get_graph(automation.automation_id))
    assert chain is not None and chain.trigger.type == AutomationTriggerType.SCHEDULE
    assert [step.config["arguments"] for step in chain.steps] == [{"knowledge_base_id": kb.kb_id}], "the name became the id"
    again = blueprints_service.deploy_blueprint(BLUEPRINT, {}, OWNER)
    assert {step.action.value for step in again.plan.steps} == {"unchanged"}
