from __future__ import annotations

from src.connectors.mcp.providers.base import MCPProvider, ProviderInstall
from src.connectors.mcp.resolved import HttpTarget
from src.form_models import FormInput, FormInputType

HUGGING_FACE_MCP_URL = "https://huggingface.co/mcp"


def _target(install: ProviderInstall) -> HttpTarget:
    token = install.inputs.get("token")
    return HttpTarget(HUGGING_FACE_MCP_URL, {"Authorization": f"Bearer {token}"} if token else {})


PROVIDER = MCPProvider(
    key="hugging_face",
    display_name="Hugging Face",
    description="Explore Hugging Face models, datasets, Spaces, papers, and documentation.",
    icon="hugging_face",
    category="development",
    tags=("ai", "models", "datasets", "spaces", "papers", "documentation"),
    docs_url="https://huggingface.co/docs/hub/en/hf-mcp-server",
    inputs=(
        FormInput(
            input_type=FormInputType.PASSWORD,
            name="token",
            label="Hugging Face token",
            attr={"optional": "true", "help_text": "Optional. Without a token, anonymous tools and rate limits apply. Add a token for authenticated tools and higher limits."},
        ),
    ),
    target=_target,
)
