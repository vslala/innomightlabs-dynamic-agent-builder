from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.messages.models import Message
from src.messages.repository import MessageRepository
from src.widget.models import WidgetConversation
from src.widget.repository import WidgetConversationRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2


def create_agent(agent_id: str, owner_email: str = TEST_USER_EMAIL) -> Agent:
    agent = Agent(
        agent_id=agent_id,
        agent_name=f"Agent {agent_id}",
        agent_architecture="krishna-mini",
        agent_provider="Bedrock",
        agent_persona="Test persona",
        created_by=owner_email,
    )
    return AgentRepository().save(agent)


def save_dashboard_conversation(
    *,
    conversation_id: str,
    agent_id: str,
    created_at: datetime,
    title: str = "Dashboard conversation",
    created_by: str = TEST_USER_EMAIL,
) -> Conversation:
    conversation = Conversation(
        conversation_id=conversation_id,
        title=title,
        agent_id=agent_id,
        created_by=created_by,
        created_at=created_at,
    )
    return ConversationRepository().save(conversation)


def save_widget_conversation(
    *,
    conversation_id: str,
    agent_id: str,
    created_at: datetime,
    visitor_email: str,
    title: str = "Widget conversation",
) -> WidgetConversation:
    conversation = WidgetConversation(
        conversation_id=conversation_id,
        agent_id=agent_id,
        visitor_id=f"visitor-{conversation_id}",
        visitor_email=visitor_email,
        visitor_name="Visitor",
        title=title,
        created_at=created_at,
    )
    return WidgetConversationRepository().save(conversation)


def save_message(
    *,
    conversation_id: str,
    created_at: datetime,
    role: str,
    created_by: str,
    content: str,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        created_by=created_by,
        content=content,
        created_at=created_at,
    )
    return MessageRepository().save(message)


def test_overview_supports_dashboard_and_widget_sources(
    test_client: TestClient,
    auth_headers: dict,
):
    create_agent("agent-analytics")
    save_dashboard_conversation(
        conversation_id="conv-dashboard",
        agent_id="agent-analytics",
        created_at=datetime(2026, 3, 10, 9, 0, tzinfo=UTC),
    )
    save_widget_conversation(
        conversation_id="conv-widget",
        agent_id="agent-analytics",
        created_at=datetime(2026, 3, 11, 10, 0, tzinfo=UTC),
        visitor_email="visitor@example.com",
    )

    save_message(
        conversation_id="conv-dashboard",
        created_at=datetime(2026, 3, 10, 9, 5, tzinfo=UTC),
        role="user",
        created_by="dashboard-user@example.com",
        content="hello",
    )
    save_message(
        conversation_id="conv-dashboard",
        created_at=datetime(2026, 3, 10, 9, 6, tzinfo=UTC),
        role="assistant",
        created_by="dashboard-user@example.com",
        content="hi",
    )
    save_message(
        conversation_id="conv-widget",
        created_at=datetime(2026, 3, 11, 10, 5, tzinfo=UTC),
        role="user",
        created_by="widget-runtime@example.com",
        content="need help",
    )

    response = test_client.get(
        "/analytics/agents/agent-analytics/overview?from=2026-03-01T00:00:00Z&to=2026-03-20T00:00:00Z&tz=UTC",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["totals"]["conversations"] == 2
    assert data["totals"]["messages"] == 3
    assert data["totals"]["user_messages"] == 2
    assert data["totals"]["assistant_messages"] == 1
    assert data["totals"]["unique_users"] == 2
    assert data["ratios"]["dropoff_rate"] == 0.5
    assert data["breakdown_by_source"]["dashboard"]["messages"] == 2
    assert data["breakdown_by_source"]["widget"]["messages"] == 1
    assert data["top"]["most_active_users"][0]["user"] == "dashboard-user@example.com"


def test_overview_filters_to_widget_source_only(
    test_client: TestClient,
    auth_headers: dict,
):
    create_agent("agent-widget-only")
    save_dashboard_conversation(
        conversation_id="conv-dashboard-only",
        agent_id="agent-widget-only",
        created_at=datetime(2026, 3, 10, 9, 0, tzinfo=UTC),
    )
    save_widget_conversation(
        conversation_id="conv-widget-only",
        agent_id="agent-widget-only",
        created_at=datetime(2026, 3, 10, 9, 0, tzinfo=UTC),
        visitor_email="widget@example.com",
    )
    save_message(
        conversation_id="conv-dashboard-only",
        created_at=datetime(2026, 3, 10, 9, 5, tzinfo=UTC),
        role="user",
        created_by="dashboard@example.com",
        content="dashboard message",
    )
    save_message(
        conversation_id="conv-widget-only",
        created_at=datetime(2026, 3, 10, 9, 6, tzinfo=UTC),
        role="user",
        created_by="runtime@example.com",
        content="widget message",
    )

    response = test_client.get(
        "/analytics/agents/agent-widget-only/overview?from=2026-03-01T00:00:00Z&to=2026-03-20T00:00:00Z&tz=UTC&sources=widget",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["window"]["sources"] == ["widget"]
    assert data["totals"]["messages"] == 1
    assert data["breakdown_by_source"]["widget"]["messages"] == 1


def test_timeseries_supports_messages_conversations_and_unique_users(
    test_client: TestClient,
    auth_headers: dict,
):
    create_agent("agent-timeseries")
    save_dashboard_conversation(
        conversation_id="conv-ts-1",
        agent_id="agent-timeseries",
        created_at=datetime(2026, 3, 10, 23, 30, tzinfo=UTC),
    )
    save_message(
        conversation_id="conv-ts-1",
        created_at=datetime(2026, 3, 10, 23, 45, tzinfo=UTC),
        role="user",
        created_by="u1@example.com",
        content="one",
    )
    save_message(
        conversation_id="conv-ts-1",
        created_at=datetime(2026, 3, 11, 0, 10, tzinfo=UTC),
        role="assistant",
        created_by="u1@example.com",
        content="two",
    )

    response = test_client.get(
        "/analytics/agents/agent-timeseries/timeseries?metric=messages&bucket=day&from=2026-03-10T00:00:00Z&to=2026-03-12T00:00:00Z&tz=Europe/Berlin&sources=dashboard",
        headers=auth_headers,
    )
    assert response.status_code == 200
    series = response.json()["series"]
    assert [point["value"] for point in series] == [0, 2, 0]

    response = test_client.get(
        "/analytics/agents/agent-timeseries/timeseries?metric=conversations&bucket=day&from=2026-03-10T00:00:00Z&to=2026-03-12T00:00:00Z&tz=UTC&sources=dashboard",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert [point["value"] for point in response.json()["series"]] == [1, 0, 0]

    response = test_client.get(
        "/analytics/agents/agent-timeseries/timeseries?metric=unique_users&bucket=day&from=2026-03-10T00:00:00Z&to=2026-03-12T00:00:00Z&tz=UTC&sources=dashboard",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert [point["value"] for point in response.json()["series"]] == [1, 1, 0]


def test_overview_ignores_messages_outside_window(
    test_client: TestClient,
    auth_headers: dict,
):
    create_agent("agent-window")
    save_dashboard_conversation(
        conversation_id="conv-window",
        agent_id="agent-window",
        created_at=datetime(2026, 3, 10, 0, 0, tzinfo=UTC),
    )
    save_message(
        conversation_id="conv-window",
        created_at=datetime(2026, 3, 9, 23, 59, tzinfo=UTC),
        role="user",
        created_by="u@example.com",
        content="before",
    )
    save_message(
        conversation_id="conv-window",
        created_at=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
        role="assistant",
        created_by="u@example.com",
        content="inside",
    )

    response = test_client.get(
        "/analytics/agents/agent-window/overview?from=2026-03-10T00:00:00Z&to=2026-03-11T00:00:00Z&tz=UTC&sources=dashboard",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["totals"]["messages"] == 1


def test_overview_returns_not_found_for_unowned_agent(
    test_client: TestClient,
    auth_headers: dict,
):
    create_agent("agent-other-owner", owner_email=TEST_USER_EMAIL_2)

    response = test_client.get(
        "/analytics/agents/agent-other-owner/overview",
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_overview_validates_inputs(
    test_client: TestClient,
    auth_headers: dict,
):
    create_agent("agent-invalid-input")

    response = test_client.get(
        "/analytics/agents/agent-invalid-input/overview?from=2026-03-20T00:00:00Z&to=2026-03-10T00:00:00Z",
        headers=auth_headers,
    )
    assert response.status_code == 400

    response = test_client.get(
        "/analytics/agents/agent-invalid-input/overview?tz=Bad/Timezone",
        headers=auth_headers,
    )
    assert response.status_code == 400

    response = test_client.get(
        "/analytics/agents/agent-invalid-input/overview?sources=dashboard,bad",
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_overview_sets_truncation_metadata(
    test_client: TestClient,
    auth_headers: dict,
    monkeypatch,
):
    import src.analytics.service as analytics_service

    monkeypatch.setattr(analytics_service, "MAX_MESSAGES_SCANNED", 1)

    create_agent("agent-truncated")
    save_dashboard_conversation(
        conversation_id="conv-truncated",
        agent_id="agent-truncated",
        created_at=datetime(2026, 3, 10, 0, 0, tzinfo=UTC),
    )
    save_message(
        conversation_id="conv-truncated",
        created_at=datetime(2026, 3, 10, 10, 0, tzinfo=UTC),
        role="user",
        created_by="u@example.com",
        content="one",
    )
    save_message(
        conversation_id="conv-truncated",
        created_at=datetime(2026, 3, 10, 10, 5, tzinfo=UTC),
        role="assistant",
        created_by="u@example.com",
        content="two",
    )

    response = test_client.get(
        "/analytics/agents/agent-truncated/overview?from=2026-03-01T00:00:00Z&to=2026-03-20T00:00:00Z&sources=dashboard",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["truncated"] is True
    assert data["meta"]["truncation_reason"] == "message scan limit reached"
