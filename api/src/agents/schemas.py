"""
Agent form schemas - single source of truth for agent-related forms.
"""

from src.form_models import (
    Form,
    FormInput,
    FormInputType,
    FormOptionsSource,
    SelectOption,
    SmartSuggestionConfig,
)
from src.form_options import FormOptionSourceType
from src.smart_suggestions.models import SmartSuggestionType


# Fallback model options if dynamic fetch fails
# These must be models available in eu-west-2
DEFAULT_MODEL_OPTIONS = [
    SelectOption(value="claude-3-7-sonnet", label="Claude 3.7 Sonnet"),
    SelectOption(value="claude-3-sonnet", label="Claude 3 Sonnet"),
    SelectOption(value="claude-3-haiku", label="Claude 3 Haiku (Fast)"),
]

# Session timeout options
SESSION_TIMEOUT_OPTIONS = [
    SelectOption(value="30", label="30 minutes"),
    SelectOption(value="60", label="1 hour (Default)"),
    SelectOption(value="120", label="2 hours"),
    SelectOption(value="240", label="4 hours"),
    SelectOption(value="0", label="No timeout (load all)"),
]

# Thinking-mode choices for Ollama reasoning models (qwen3, deepseek-r1, ...).
# Ignored for every other provider.
OLLAMA_THINKING_OPTIONS = [
    SelectOption(value="default", label="Provider default"),
    SelectOption(value="enabled", label="Enabled"),
    SelectOption(value="disabled", label="Disabled"),
]


def _ollama_thinking_field() -> FormInput:
    return FormInput(
        label="Ollama Thinking Mode",
        name="agent_ollama_thinking",
        input_type=FormInputType.CHOICE,
        options=OLLAMA_THINKING_OPTIONS,
        value="default",
        attr={
            "optional": "true",
            "help_text": (
                "Only applies to Ollama agents using a reasoning model (e.g. qwen3, "
                "deepseek-r1). Ignored for every other provider."
            ),
        },
    )


def _agent_instructions_field() -> FormInput:
    return FormInput(
        label="Instructions",
        name="agent_persona",
        input_type=FormInputType.TEXT_AREA,
        smart_suggestion=SmartSuggestionConfig(
            suggestion_type=SmartSuggestionType.AGENT_INSTRUCTIONS,
            button_label="Suggest instructions",
            prompt_placeholder="Describe what this agent should do",
        ),
        attr={"rows": "8"},
    )


def get_create_agent_form() -> Form:
    """
    Get the form schema for creating an agent.

    Returns:
        Form schema with dynamic model option sources
    """
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
            _agent_instructions_field(),
            FormInput(
                label="Description (optional)",
                name="agent_description",
                input_type=FormInputType.TEXT_AREA,
                attr={"optional": "true"},
            ),
            FormInput(
                label="Provider Name",
                name="agent_provider",
                input_type=FormInputType.SELECT,
                options_source=FormOptionsSource(type=FormOptionSourceType.AGENT_MODEL_PROVIDERS),
            ),
            FormInput(
                label="Model",
                name="agent_model",
                options=DEFAULT_MODEL_OPTIONS,
                input_type=FormInputType.SEARCH,
                options_source=FormOptionsSource(type=FormOptionSourceType.AGENT_MODELS),
            ),
            FormInput(
                label="Session Timeout",
                name="session_timeout_minutes",
                options=SESSION_TIMEOUT_OPTIONS,
                value="60",  # Default value
                input_type=FormInputType.SELECT,
            ),
            _ollama_thinking_field(),
        ],
    )


def get_update_agent_form(
    agent_id: str,
) -> Form:
    """
    Get the update form schema for a specific agent.

    Returns:
        Form schema with dynamic model option sources
    """
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
            _agent_instructions_field(),
            FormInput(
                label="Description (optional)",
                name="agent_description",
                input_type=FormInputType.TEXT_AREA,
                attr={"optional": "true"},
            ),
            FormInput(
                label="Provider Name",
                name="agent_provider",
                input_type=FormInputType.SELECT,
                options_source=FormOptionsSource(type=FormOptionSourceType.AGENT_MODEL_PROVIDERS),
            ),
            FormInput(
                label="Model",
                name="agent_model",
                options=DEFAULT_MODEL_OPTIONS,
                input_type=FormInputType.SEARCH,
                options_source=FormOptionsSource(type=FormOptionSourceType.AGENT_MODELS),
            ),
            FormInput(
                label="Session Timeout",
                name="session_timeout_minutes",
                options=SESSION_TIMEOUT_OPTIONS,
                input_type=FormInputType.SELECT,
            ),
            _ollama_thinking_field(),
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
        _agent_instructions_field(),
        FormInput(
            label="Description (optional)",
            name="agent_description",
            input_type=FormInputType.TEXT_AREA,
            attr={"optional": "true"},
        ),
        FormInput(
            label="Provider Name",
            name="agent_provider",
            values=["Bedrock", "Anthropic", "OpenAI", "Gemini", "Ollama"],
            input_type=FormInputType.SELECT,
        ),
        FormInput(
            label="Model",
            name="agent_model",
            options=DEFAULT_MODEL_OPTIONS,
            input_type=FormInputType.SEARCH,
        ),
        FormInput(
            label="Session Timeout",
            name="session_timeout_minutes",
            options=SESSION_TIMEOUT_OPTIONS,
            input_type=FormInputType.SELECT,
        ),
        _ollama_thinking_field(),
    ],
)
