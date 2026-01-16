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
