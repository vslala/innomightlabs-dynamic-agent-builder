"""
Agent Architecture factory.

Returns the appropriate architecture based on the agent's configuration.
"""

from collections.abc import Callable

from .base import AgentArchitecture
from .krishna_mini import KrishnaMiniArchitecture
from .krishna_memgpt import KrishnaMemGPTArchitecture
from src.messages.repositories import MessageRepository

ArchitectureFactory = Callable[..., AgentArchitecture]


def get_agent_architecture(
    architecture_name: str,
    *,
    message_repository: MessageRepository | None = None,
) -> AgentArchitecture:
    """
    Get an agent architecture instance by name.

    Args:
        architecture_name: The name of the architecture (e.g., "krishna-mini")
        message_repository: Optional message repository override for this runtime

    Returns:
        An instance of the appropriate architecture

    Raises:
        ValueError: If the architecture name is not supported
    """
    factories: dict[str, ArchitectureFactory] = {
        "krishna-mini": KrishnaMiniArchitecture,
        "krishna-memgpt": KrishnaMemGPTArchitecture,
    }

    factory = factories.get(architecture_name)
    if not factory:
        supported = ", ".join(factories.keys())
        raise ValueError(
            f"Unknown architecture: '{architecture_name}'. Supported: {supported}"
        )

    return factory(message_repository=message_repository)
