"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from app.models.llm import ChatMessage, LLMResponse, StreamChunk
from app.models.tools import Tool


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    provider_name: str = "base"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        base_url: str | None = None,
        timeout: int = 120,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.base_url = base_url
        self.timeout = timeout

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        tools: list[Tool] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Send a chat completion request.

        Args:
            messages: List of conversation messages
            system_prompt: Optional system prompt
            tools: Optional list of tools for function calling
            **kwargs: Provider-specific options

        Returns:
            LLMResponse with the model's response
        """
        pass

    @abstractmethod
    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        tools: list[Tool] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream a chat completion response.

        Args:
            messages: List of conversation messages
            system_prompt: Optional system prompt
            tools: Optional list of tools for function calling
            **kwargs: Provider-specific options

        Yields:
            StreamChunk with partial responses
        """
        pass
        # Make this an async generator
        if False:
            yield StreamChunk()

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the provider is available and configured correctly.

        Returns:
            True if healthy, False otherwise
        """
        pass

    def supports_tools(self) -> bool:
        """Check if this provider supports tool/function calling."""
        return True

    def supports_streaming(self) -> bool:
        """Check if this provider supports streaming responses."""
        return True

    def get_model_name(self) -> str:
        """Get the current model name."""
        return self.model or "unknown"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model})"
