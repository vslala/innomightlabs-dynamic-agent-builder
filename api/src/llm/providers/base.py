"""
Base LLM Provider interface.

All LLM providers must implement this interface to ensure consistent
behavior across different AI model backends.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Providers are responsible for:
    1. Authenticating with the LLM service
    2. Formatting messages for the specific API
    3. Streaming responses back to the caller
    """

    @abstractmethod
    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
    ) -> AsyncIterator[str]:
        """
        Stream response chunks from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                     The first message with role='system' is the system prompt.
            credentials: Provider-specific credentials dict (e.g., {"access_key": "...", "secret_key": "..."})

        Yields:
            String chunks of the response as they arrive

        Raises:
            Exception: If the API call fails
        """
        pass
