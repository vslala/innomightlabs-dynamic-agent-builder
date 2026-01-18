"""
Base LLM Provider interface.

All LLM providers must implement this interface to ensure consistent
behavior across different AI model backends.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Literal, Optional


@dataclass
class LLMEvent:
    """
    Event emitted during LLM streaming.

    Types:
    - "text": Text content chunk
    - "tool_use": Tool call request from the model
    - "stop": Stream completed
    """

    type: Literal["text", "tool_use", "stop"]
    content: str = ""
    tool_use_id: str = ""
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Providers are responsible for:
    1. Authenticating with the LLM service
    2. Formatting messages for the specific API
    3. Streaming responses back to the caller
    4. Handling tool use if tools are provided
    """

    @abstractmethod
    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        """
        Stream response events from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                     The first message with role='system' is the system prompt.
            credentials: Provider-specific credentials dict (e.g., {"access_key": "...", "secret_key": "..."})
            tools: Optional list of tool definitions for function calling
            model: Optional model name/id to use (provider-specific)

        Yields:
            LLMEvent objects representing text chunks, tool calls, or stop signal

        Raises:
            Exception: If the API call fails
        """
        pass
