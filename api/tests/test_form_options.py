from __future__ import annotations

from src.agents.models import Agent
from src.form_models import Form, FormInput, FormInputType, FormOptionsSource
from src.form_options import FormOptionsContext, hydrate_form_options, validate_form_options
from tests.mock_data import agent_fields, owner_for

OWNER = owner_for("owner@example.com")


class FakeAgentRepository:
    def list_owned(self, account_id: str, owner_id: str) -> list[Agent]:
        user_email = "user@example.com"
        return [
            Agent(
                agent_id="mini-1",
                agent_name="Mini Reporter",
                agent_architecture="krishna-mini",
                agent_provider="Bedrock",
                agent_persona="Reports.",
                **agent_fields(user_email),
            ),
            Agent(
                agent_id="memgpt-1",
                agent_name="Memory Agent",
                agent_architecture="krishna-memgpt",
                agent_provider="Bedrock",
                agent_persona="Memory.",
                **agent_fields(user_email),
            ),
        ]


def _agent_form() -> Form:
    return Form(
        form_name="Report Skill",
        submit_path="",
        form_inputs=[
            FormInput(
                input_type=FormInputType.SELECT,
                name="agent_id",
                label="Agent",
                options_source=FormOptionsSource(type="krishna_mini_agents"),
            )
        ],
    )


def test_krishna_mini_agent_options_only_include_mini_agents():
    form = hydrate_form_options(
        _agent_form(),
        FormOptionsContext(owner=OWNER, agent_repository=FakeAgentRepository()),
    )

    options = form.form_inputs[0].options or []
    assert [(option.value, option.label) for option in options] == [("mini-1", "Mini Reporter")]


def test_krishna_mini_agent_options_validation_rejects_other_architectures():
    context = FormOptionsContext(owner=OWNER, agent_repository=FakeAgentRepository())

    validate_form_options(_agent_form().form_inputs, {"agent_id": "mini-1"}, context)

    try:
        validate_form_options(_agent_form().form_inputs, {"agent_id": "memgpt-1"}, context)
    except ValueError as exc:
        assert str(exc) == "Invalid value for agent_id"
    else:
        raise AssertionError("Expected memgpt agent to be rejected")
