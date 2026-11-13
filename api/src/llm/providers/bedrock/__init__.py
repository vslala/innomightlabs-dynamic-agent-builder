"""Claude on Amazon Bedrock, with the account's own AWS keys."""

from src.form_models import Form, FormInput, FormInputType
from src.llm.providers.provider import Provider

from .catalog import BedrockCatalog
from .chat import BedrockProvider

# No refusal rule: `BedrockProvider.get_model_id` already maps a missing model onto the live catalog.
BEDROCK = Provider(
    name="Bedrock",
    title="Bedrock",
    settings_form=Form(
        form_name="AWS Bedrock Configuration",
        submit_path="/settings/providers/Bedrock",
        form_inputs=[
            FormInput(input_type=FormInputType.PASSWORD, name="access_key", label="AWS Access Key"),
            FormInput(input_type=FormInputType.PASSWORD, name="secret_key", label="AWS Secret Key"),
        ],
    ),
    chat=BedrockProvider(),
    catalog=BedrockCatalog(),
)
