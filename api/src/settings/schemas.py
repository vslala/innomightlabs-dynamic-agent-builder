"""Form schemas for the account's settings. Each LLM provider's credentials form is its own
(`Provider.settings_form`, in `src/llm/providers/`)."""

from src.form_models import Form, FormInput, FormInputType


def get_agent2agent_settings_schema() -> Form:
    return Form(
        form_name="Agent2Agent Trust Settings",
        submit_path="/settings/agent2agent",
        form_inputs=[
            FormInput(
                input_type=FormInputType.KEY_VALUE,
                name="allowed_origins",
                label="Allowed Agent2Agent Origins",
                attr={
                    "key_placeholder": "https://api.example.com or http://localhost:1455",
                    "value_placeholder": "Optional label",
                    "add_label": "Add origin",
                    "empty_text": "No Agent2Agent origins are allowlisted.",
                },
            )
        ],
    )
