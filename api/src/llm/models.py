"""What a provider's catalog says about one model."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ModelCapability(StrEnum):
    """What a model can be used for. The catalog that lists it decides, from the vendor's own fields where it has them
    and otherwise from a dated rule beside its parsing. The values are on the wire (`/llm/models`,
    `AgentResponse.capabilities`), so they don't change."""

    #: Can hold an agent's conversation
    CHAT = "chat"
    IMAGE_UNDERSTANDING = "image_understanding"
    IMAGE_GENERATION = "image_generation"
    IMAGE_EDITING = "image_editing"


class ModelInfo(BaseModel):
    """Information about an available model."""

    model_id: str  # The provider's own id (e.g., "us.anthropic.claude-sonnet-4-20250514-v1:0")
    model_name: str  # The name an agent stores and pickers offer (e.g., "claude-sonnet-4")
    display_name: str  # Human-readable name (e.g., "Claude Sonnet 4")
    provider: str  # The provider's catalog key (e.g., "bedrock")
    capabilities: list[ModelCapability] = Field(default_factory=list)

    def can(self, *needed: ModelCapability) -> bool:
        return all(capability in self.capabilities for capability in needed)


def chat_capabilities(*, reads_images: bool, draws: bool = False) -> list[ModelCapability]:
    """A chat model's capabilities: whether it reads images, and whether it draws (through its provider's tool)."""
    return [
        ModelCapability.CHAT,
        *([ModelCapability.IMAGE_UNDERSTANDING] if reads_images else []),
        *([ModelCapability.IMAGE_GENERATION] if draws else []),
    ]
