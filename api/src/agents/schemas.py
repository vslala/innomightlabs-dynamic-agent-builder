"""
Agent form schemas - single source of truth for agent-related forms.
"""

from src.form_models import Form, FormInput, FormInputType


CREATE_AGENT_FORM = Form(
    form_name="Create Agent Form",
    submit_path="/agents",
    form_inputs=[
        FormInput(
            label="Agent Name",
            name="agent_name",
            input_type=FormInputType.TEXT,
        ),
        FormInput(
            label="Architecture",
            name="agent_architecture",
            values=["krishna-mini"],  # Future: "krishna-memgpt", etc.
            input_type=FormInputType.SELECT,
        ),
        FormInput(
            label="Persona",
            name="agent_persona",
            input_type=FormInputType.TEXT_AREA,
        ),
        FormInput(
            label="Provider Name",
            name="agent_provider",
            values=["Bedrock"],
            input_type=FormInputType.SELECT,
        ),
        FormInput(
            label="Provider API Key",
            name="agent_provider_api_key",
            input_type=FormInputType.PASSWORD,
        ),
    ],
)


def get_update_agent_form(agent_id: str) -> Form:
    """
    Get the update form schema for a specific agent.
    The submit_path includes the agent_id.
    """
    return Form(
        form_name="Update Agent Form",
        submit_path=f"/agents/{agent_id}",
        form_inputs=[
            FormInput(
                label="Architecture",
                name="agent_architecture",
                values=["krishna-mini"],  # Future: "krishna-memgpt", etc.
                input_type=FormInputType.SELECT,
            ),
            FormInput(
                label="Persona",
                name="agent_persona",
                input_type=FormInputType.TEXT_AREA,
            ),
            FormInput(
                label="Provider Name",
                name="agent_provider",
                values=["Bedrock"],
                input_type=FormInputType.SELECT,
            ),
            FormInput(
                label="Provider API Key",
                name="agent_provider_api_key",
                input_type=FormInputType.PASSWORD,
            ),
        ],
    )


# Static version for validation (without dynamic agent_id in path)
UPDATE_AGENT_FORM = Form(
    form_name="Update Agent Form",
    submit_path="/agents/{agent_id}",
    form_inputs=[
        FormInput(
            label="Architecture",
            name="agent_architecture",
            values=["krishna-mini"],  # Future: "krishna-memgpt", etc.
            input_type=FormInputType.SELECT,
        ),
        FormInput(
            label="Persona",
            name="agent_persona",
            input_type=FormInputType.TEXT_AREA,
        ),
        FormInput(
            label="Provider Name",
            name="agent_provider",
            values=["Bedrock"],
            input_type=FormInputType.SELECT,
        ),
        FormInput(
            label="Provider API Key",
            name="agent_provider_api_key",
            input_type=FormInputType.PASSWORD,
        ),
    ],
)
