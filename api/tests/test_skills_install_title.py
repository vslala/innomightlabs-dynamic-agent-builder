"""Every skill install carries a title and a description: what the person calls it, and what the agent reads."""

from __future__ import annotations

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.skills.service import SkillRuntimeService
from tests.mock_data import TEST_USER_EMAIL, agent_fields

SITE = {"site_url": "https://example.com", "username": "admin", "app_password": "secret-pass"}


def _agent() -> Agent:
    return AgentRepository().save(
        Agent(
            agent_name="Title Test Agent",
            agent_architecture="krishna-memgpt",
            agent_provider="Bedrock",
            agent_model="claude-3-7-sonnet",
            agent_persona="Helpful",
            **agent_fields(TEST_USER_EMAIL),
        )
    )


def _install(test_client, auth_headers, agent_id: str, **body):
    return test_client.post(
        f"/agents/{agent_id}/skills?skill_id=wordpress_search", headers=auth_headers, json={"config": SITE, **body}
    )


def test_install_schema_asks_for_a_title_and_an_optional_description(test_client, auth_headers):
    schema = test_client.get("/skills/wordpress_search/install-schema", headers=auth_headers).json()
    title, description, *rest = schema["form_inputs"]

    assert (title["name"], description["name"]) == ("install_title", "install_description")
    assert title["value"] == "WordPress Search"
    assert "optional" not in (title.get("attr") or {})
    assert description["attr"]["optional"] == "true"
    assert "Your agent sees this title and description" in description["attr"]["help_text"]
    assert [field["name"] for field in rest][:1] == ["site_url"]


def test_an_install_without_a_title_takes_the_skills_name_and_description(test_client, auth_headers, dynamodb_table):
    agent = _agent()
    installed = _install(test_client, auth_headers, agent.agent_id).json()

    schema = test_client.get("/skills/wordpress_search/install-schema", headers=auth_headers).json()
    assert installed["name"] == "WordPress Search"
    assert installed["description"] == schema["form_inputs"][1]["value"]


def test_the_title_and_description_given_are_what_the_install_keeps(test_client, auth_headers, dynamodb_table):
    agent = _agent()
    response = _install(
        test_client, auth_headers, agent.agent_id, title="  Company blog  ", description="Search our blog posts."
    )

    assert response.status_code == 201
    assert (response.json()["name"], response.json()["description"]) == ("Company blog", "Search our blog posts.")
    raw = dynamodb_table.get_item(Key={"pk": f"Agent#{agent.agent_id}", "sk": "Skill#wordpress_search"})["Item"]
    assert (raw["skill_name"], raw["skill_description"]) == ("Company blog", "Search our blog posts.")


def test_updating_the_settings_or_toggling_keeps_the_title(test_client, auth_headers, dynamodb_table):
    agent = _agent()
    _install(test_client, auth_headers, agent.agent_id, title="Company blog", description="Search our blog.")
    url = f"/agents/{agent.agent_id}/skills/wordpress_search"

    toggled = test_client.patch(url, headers=auth_headers, json={"enabled": False}).json()
    reconfigured = test_client.patch(
        url, headers=auth_headers, json={"config": {"site_url": "https://example.org"}}
    ).json()
    reinstalled = _install(test_client, auth_headers, agent.agent_id).json()

    for item in (toggled, reconfigured, reinstalled):
        assert (item["name"], item["description"]) == ("Company blog", "Search our blog.")


def test_the_title_and_description_can_be_changed_alone(test_client, auth_headers, dynamodb_table):
    agent = _agent()
    _install(test_client, auth_headers, agent.agent_id, title="Company blog", description="Search our blog.")
    url = f"/agents/{agent.agent_id}/skills/wordpress_search"

    renamed = test_client.patch(url, headers=auth_headers, json={"title": "Docs site"})
    cleared = test_client.patch(url, headers=auth_headers, json={"description": ""})

    assert (renamed.json()["name"], renamed.json()["description"]) == ("Docs site", "Search our blog.")
    assert (cleared.json()["name"], cleared.json()["description"]) == ("Docs site", "")


def test_the_title_is_required_and_both_have_a_length_limit(test_client, auth_headers, dynamodb_table):
    agent = _agent()
    url = f"/agents/{agent.agent_id}/skills/wordpress_search"
    _install(test_client, auth_headers, agent.agent_id)

    assert _install(test_client, auth_headers, agent.agent_id, title="   ").status_code == 422
    assert _install(test_client, auth_headers, agent.agent_id, title="x" * 81).status_code == 422
    assert _install(test_client, auth_headers, agent.agent_id, description="x" * 301).status_code == 422
    assert test_client.patch(url, headers=auth_headers, json={"title": ""}).status_code == 422


def test_the_agent_reads_each_installs_title_and_description(test_client, auth_headers, dynamodb_table):
    agent = _agent()
    _install(test_client, auth_headers, agent.agent_id, title="Company blog", description="Search our blog posts.")
    runtime = SkillRuntimeService()

    prompt = runtime.build_system_prompt_addendum(runtime.list_enabled(agent.agent_id))
    assert "- wordpress_search: Company blog - Search our blog posts. (skill_id: wordpress_search)" in prompt

    test_client.patch(f"/agents/{agent.agent_id}/skills/wordpress_search", headers=auth_headers, json={"description": ""})
    prompt = runtime.build_system_prompt_addendum(runtime.list_enabled(agent.agent_id))
    assert "- wordpress_search: Company blog (skill_id: wordpress_search)" in prompt
