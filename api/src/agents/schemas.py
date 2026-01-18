"""
Agent form schemas - single source of truth for agent-related forms.
"""

from src.form_models import Form, FormInput, FormInputType, SelectOption


# Fallback model options if dynamic fetch fails
DEFAULT_MODEL_OPTIONS = [
    SelectOption(value="claude-sonnet-4", label="Claude Sonnet 4 (Latest)"),
    SelectOption(value="claude-opus-4", label="Claude Opus 4"),
    SelectOption(value="claude-3-5-haiku", label="Claude 3.5 Haiku (Fast)"),
    SelectOption(value="claude-3-5-sonnet", label="Claude 3.5 Sonnet v2"),
]

# Session timeout options
SESSION_TIMEOUT_OPTIONS = [
    SelectOption(value="30", label="30 minutes"),
    SelectOption(value="60", label="1 hour (Default)"),
    SelectOption(value="120", label="2 hours"),
    SelectOption(value="240", label="4 hours"),
    SelectOption(value="0", label="No timeout (load all)"),
]


def get_create_agent_form(model_options: list[dict] | None = None) -> Form:
    """
    Get the form schema for creating an agent.

    Args:
        model_options: List of model options with value/label pairs

    Returns:
        Form schema with dynamic model options
    """
    options = (
        [SelectOption(**opt) for opt in model_options]
        if model_options
        else DEFAULT_MODEL_OPTIONS
    )

    return Form(
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
                values=["krishna-mini", "krishna-memgpt"],
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
                label="Model",
                name="agent_model",
                options=options,
                input_type=FormInputType.SELECT,
            ),
            FormInput(
                label="Session Timeout",
                name="session_timeout_minutes",
                options=SESSION_TIMEOUT_OPTIONS,
                value="60",  # Default value
                input_type=FormInputType.SELECT,
            ),
        ],
    )


# Static version for backward compatibility
CREATE_AGENT_FORM = get_create_agent_form()


def get_update_agent_form(agent_id: str, model_options: list[dict] | None = None) -> Form:
    """
    Get the update form schema for a specific agent.

    Args:
        agent_id: The agent ID for the submit path
        model_options: List of model options with value/label pairs

    Returns:
        Form schema with dynamic model options
    """
    options = (
        [SelectOption(**opt) for opt in model_options]
        if model_options
        else DEFAULT_MODEL_OPTIONS
    )

    return Form(
        form_name="Update Agent Form",
        submit_path=f"/agents/{agent_id}",
        form_inputs=[
            FormInput(
                label="Architecture",
                name="agent_architecture",
                values=["krishna-mini", "krishna-memgpt"],
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
                label="Model",
                name="agent_model",
                options=options,
                input_type=FormInputType.SELECT,
            ),
            FormInput(
                label="Session Timeout",
                name="session_timeout_minutes",
                options=SESSION_TIMEOUT_OPTIONS,
                input_type=FormInputType.SELECT,
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
            values=["krishna-mini", "krishna-memgpt"],
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
            label="Model",
            name="agent_model",
            options=DEFAULT_MODEL_OPTIONS,
            input_type=FormInputType.SELECT,
        ),
        FormInput(
            label="Session Timeout",
            name="session_timeout_minutes",
            options=SESSION_TIMEOUT_OPTIONS,
            input_type=FormInputType.SELECT,
        ),
    ],
)
