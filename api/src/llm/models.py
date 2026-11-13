"""What a provider's catalog says about one model."""

from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    """Information about an available model."""

    model_id: str  # The provider's own id (e.g., "us.anthropic.claude-sonnet-4-20250514-v1:0")
    model_name: str  # The name an agent stores and pickers offer (e.g., "claude-sonnet-4")
    display_name: str  # Human-readable name (e.g., "Claude Sonnet 4")
    provider: str  # The provider's catalog key (e.g., "bedrock")
    capabilities: list[str] = Field(default_factory=list)
