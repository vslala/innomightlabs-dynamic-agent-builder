"""
Agent Architecture factory.

Returns the appropriate architecture based on the agent's configuration.
"""

from .base import AgentArchitecture
from .krishna_mini import KrishnaMiniArchitecture


def get_agent_architecture(architecture_name: str) -> AgentArchitecture:
    """
    Get an agent architecture instance by name.

    Args:
        architecture_name: The name of the architecture (e.g., "krishna-mini")

    Returns:
        An instance of the appropriate architecture

    Raises:
        ValueError: If the architecture name is not supported
    """
    architectures: dict[str, AgentArchitecture] = {
        "krishna-mini": KrishnaMiniArchitecture(),
        # Future architectures:
        # "krishna-memgpt": KrishnaMemGPTArchitecture(),
    }

    architecture = architectures.get(architecture_name)
    if not architecture:
        supported = ", ".join(architectures.keys())
        raise ValueError(
            f"Unknown architecture: '{architecture_name}'. Supported: {supported}"
        )

    return architecture
