from fastapi import status

from tests.mock_data import TEST_USER_EMAIL


def _create_kb(kb_repo, name: str = "Test KB"):
    from src.knowledge.models import KnowledgeBase

    kb = KnowledgeBase(
        name=name,
        description="Test knowledge base",
        created_by=TEST_USER_EMAIL,
    )
    return kb_repo.save(kb)


def test_crawl_job_rejects_when_over_limit(test_client, auth_headers, dynamodb_table):
    from src.knowledge.repository import KnowledgeBaseRepository

    kb_repo = KnowledgeBaseRepository()
    kb = _create_kb(kb_repo)

    payload = {
        "source_type": "sitemap",
        "source_url": "https://example.com/sitemap.xml",
        "max_pages": 20,
    }

    response = test_client.post(
        f"/knowledge-bases/{kb.kb_id}/crawl-jobs?auto_start=true",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    data = response.json()
    assert "upgrade_url" in data["detail"]


def test_crawl_job_defaults_to_max_pages_limit(test_client, auth_headers, dynamodb_table):
    from src.knowledge.repository import KnowledgeBaseRepository

    kb_repo = KnowledgeBaseRepository()
    kb = _create_kb(kb_repo, name="Default Limit KB")

    payload = {
        "source_type": "sitemap",
        "source_url": "https://example.com/sitemap.xml",
    }

    response = test_client.post(
        f"/knowledge-bases/{kb.kb_id}/crawl-jobs?auto_start=true",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_crawl_job_creation_allows_when_not_auto_started(test_client, auth_headers, dynamodb_table):
    from src.knowledge.repository import KnowledgeBaseRepository

    kb_repo = KnowledgeBaseRepository()
    kb = _create_kb(kb_repo, name="Manual KB")

    payload = {
        "source_type": "sitemap",
        "source_url": "https://example.com/sitemap.xml",
        "max_pages": 999,
    }

    response = test_client.post(
        f"/knowledge-bases/{kb.kb_id}/crawl-jobs?auto_start=false",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_201_CREATED


def test_agent_limit_respects_latest_paid_plan(test_client, auth_headers, dynamodb_table):
    from src.payments.subscriptions import Subscription, SubscriptionRepository

    repo = SubscriptionRepository()
    repo.upsert(
        Subscription(
            subscription_id="sub-free",
            user_email=TEST_USER_EMAIL,
            status="active",
            plan_name="free",
        )
    )
    repo.upsert(
        Subscription(
            subscription_id="sub-starter",
            user_email=TEST_USER_EMAIL,
            status="active",
            plan_name="starter",
        )
    )

    response1 = test_client.post("/agents", json={"agent_name": "Agent One", **_agent_payload()}, headers=auth_headers)
    response2 = test_client.post("/agents", json={"agent_name": "Agent Two", **_agent_payload()}, headers=auth_headers)

    assert response1.status_code == status.HTTP_201_CREATED
    assert response2.status_code == status.HTTP_201_CREATED


def _agent_payload():
    return {
        "agent_architecture": "krishna-memgpt",
        "agent_provider": "Bedrock",
        "agent_model": "anthropic.claude-3-sonnet-20240229-v1:0",
        "agent_persona": "Test persona",
    }
