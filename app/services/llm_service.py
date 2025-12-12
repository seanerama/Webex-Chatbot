"""Unified LLM orchestration service."""

from collections.abc import AsyncIterator
from typing import Any

from app.config import LLMProvider, get_settings
from app.core.exceptions import LLMError, LLMProviderError
from app.core.logging import get_logger, LogEvents
from app.models.llm import ChatMessage, LLMResponse, MessageRole, StreamChunk, ToolCall, ToolResult
from app.models.tools import Tool
from app.providers.base import BaseLLMProvider
from app.providers.registry import ProviderRegistry, get_provider
from app.services.mcp_service import MCPService

logger = get_logger("llm_service")


class LLMService:
    """Unified service for LLM interactions with tool execution loop."""

    def __init__(
        self,
        mcp_service: MCPService | None = None,
        max_tool_iterations: int = 10,
    ) -> None:
        self._mcp = mcp_service
        self._max_tool_iterations = max_tool_iterations
        self._settings = get_settings()

    def _get_provider(
        self,
        provider_name: str | None = None,
        model: str | None = None,
    ) -> BaseLLMProvider:
        """Get a provider instance with optional overrides."""
        if provider_name:
            provider = ProviderRegistry.get_or_create_provider(
                provider_name,
                model=model,
            )
        else:
            provider = get_provider()

        # Override model if specified
        if model and provider.model != model:
            provider = ProviderRegistry.create_provider(
                provider.provider_name,
                model=model,
            )

        return provider

    def _build_messages(
        self,
        user_message: str,
        history: list[dict[str, Any]] | None = None,
        tool_results: list[ToolResult] | None = None,
    ) -> list[ChatMessage]:
        """Build message list from history and current message."""
        messages: list[ChatMessage] = []

        # Add history
        if history:
            for msg in history:
                messages.append(
                    ChatMessage(
                        role=MessageRole(msg["role"]),
                        content=msg["content"],
                    )
                )

        # Add current user message
        messages.append(
            ChatMessage(
                role=MessageRole.USER,
                content=user_message,
            )
        )

        # Add tool results if any
        if tool_results:
            for result in tool_results:
                messages.append(
                    ChatMessage(
                        role=MessageRole.TOOL,
                        content=result.content,
                        tool_call_id=result.tool_call_id,
                    )
                )

        return messages

    async def chat(
        self,
        message: str,
        system_prompt: str | None = None,
        history: list[dict[str, Any]] | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        use_tools: bool = True,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Send a chat request with automatic tool execution loop.

        This method handles the full tool use loop:
        1. Send message to LLM
        2. If LLM requests tools, execute them
        3. Send tool results back to LLM
        4. Repeat until LLM returns final response

        Args:
            message: User message
            system_prompt: Optional system prompt
            history: Conversation history
            provider_name: Provider to use (defaults to configured default)
            model: Model to use (defaults to provider default)
            use_tools: Whether to enable tool use
            **kwargs: Additional provider-specific options

        Returns:
            Final LLM response
        """
        provider = self._get_provider(provider_name, model)

        # Get tools if enabled and MCP is available
        tools: list[Tool] | None = None
        if use_tools and self._mcp and self._mcp.is_enabled:
            tools = self._mcp.get_tools()

        logger.info(
            LogEvents.LLM_REQUEST_STARTED,
            provider=provider.provider_name,
            model=provider.model,
            has_tools=tools is not None,
            tool_count=len(tools) if tools else 0,
        )

        messages = self._build_messages(message, history)
        iterations = 0

        while iterations < self._max_tool_iterations:
            iterations += 1

            response = await provider.chat(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools,
                **kwargs,
            )

            # If no tool calls, we're done
            if not response.tool_calls or response.finish_reason != "tool_calls":
                logger.info(
                    LogEvents.LLM_REQUEST_COMPLETED,
                    provider=provider.provider_name,
                    model=response.model,
                    iterations=iterations,
                    finish_reason=response.finish_reason,
                )
                return response

            # Execute tools
            logger.debug(
                LogEvents.LLM_TOOL_CALL,
                tool_count=len(response.tool_calls),
                tools=[tc.name for tc in response.tool_calls],
            )

            # Add assistant message with tool calls
            messages.append(
                ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            # Execute tools and get results
            if self._mcp:
                tool_results = await self._mcp.execute_tools(response.tool_calls)
            else:
                # No MCP service - return error results
                tool_results = [
                    ToolResult(
                        tool_call_id=tc.id,
                        content="Tool execution not available",
                        is_error=True,
                    )
                    for tc in response.tool_calls
                ]

            # Add tool results as messages
            for result in tool_results:
                messages.append(
                    ChatMessage(
                        role=MessageRole.TOOL,
                        content=result.content,
                        tool_call_id=result.tool_call_id,
                    )
                )

        # Max iterations reached
        logger.warning(
            "max_tool_iterations_reached",
            max_iterations=self._max_tool_iterations,
        )
        raise LLMError(f"Max tool iterations ({self._max_tool_iterations}) reached")

    async def stream(
        self,
        message: str,
        system_prompt: str | None = None,
        history: list[dict[str, Any]] | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        use_tools: bool = True,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream a chat response.

        Note: When tool calls are involved, this yields chunks and then
        handles tool execution internally, yielding the final response.

        Args:
            message: User message
            system_prompt: Optional system prompt
            history: Conversation history
            provider_name: Provider to use
            model: Model to use
            use_tools: Whether to enable tool use
            **kwargs: Additional provider-specific options

        Yields:
            StreamChunk with partial responses
        """
        provider = self._get_provider(provider_name, model)

        # Get tools if enabled
        tools: list[Tool] | None = None
        if use_tools and self._mcp and self._mcp.is_enabled:
            tools = self._mcp.get_tools()

        logger.info(
            LogEvents.LLM_STREAMING_STARTED,
            provider=provider.provider_name,
            model=provider.model,
        )

        messages = self._build_messages(message, history)
        iterations = 0
        accumulated_tool_calls: list[ToolCall] = []
        accumulated_content = ""

        while iterations < self._max_tool_iterations:
            iterations += 1
            accumulated_tool_calls = []
            accumulated_content = ""

            async for chunk in provider.stream(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools,
                **kwargs,
            ):
                # Yield text content
                if chunk.content:
                    accumulated_content += chunk.content
                    yield chunk

                # Collect tool calls
                if chunk.tool_calls:
                    accumulated_tool_calls.extend(chunk.tool_calls)

                # Check for completion
                if chunk.done:
                    if not accumulated_tool_calls or chunk.finish_reason != "tool_calls":
                        # No tool calls - we're done
                        yield chunk
                        return

            # Handle tool calls
            if accumulated_tool_calls:
                logger.debug(
                    LogEvents.LLM_TOOL_CALL,
                    tool_count=len(accumulated_tool_calls),
                )

                # Add assistant message with tool calls
                messages.append(
                    ChatMessage(
                        role=MessageRole.ASSISTANT,
                        content=accumulated_content,
                        tool_calls=accumulated_tool_calls,
                    )
                )

                # Execute tools
                if self._mcp:
                    tool_results = await self._mcp.execute_tools(accumulated_tool_calls)
                else:
                    tool_results = [
                        ToolResult(
                            tool_call_id=tc.id,
                            content="Tool execution not available",
                            is_error=True,
                        )
                        for tc in accumulated_tool_calls
                    ]

                # Add tool results
                for result in tool_results:
                    messages.append(
                        ChatMessage(
                            role=MessageRole.TOOL,
                            content=result.content,
                            tool_call_id=result.tool_call_id,
                        )
                    )

                # Yield a marker that we're processing tools
                yield StreamChunk(content="\n\n[Processing tool results...]\n\n")
            else:
                # No tool calls and stream ended
                break

        logger.warning("max_tool_iterations_reached_streaming")

    async def get_healthy_provider(
        self,
        preferred: str | None = None,
    ) -> BaseLLMProvider:
        """Get a healthy provider with fallback support."""
        preferred_provider = LLMProvider(preferred) if preferred else None
        return await ProviderRegistry.get_healthy_provider(preferred=preferred_provider)

    async def health_check(self, provider_name: str | None = None) -> dict[str, Any]:
        """Check health of LLM providers."""
        results: dict[str, Any] = {}

        if provider_name:
            # Check specific provider
            try:
                provider = self._get_provider(provider_name)
                results[provider_name] = await provider.health_check()
            except Exception as e:
                results[provider_name] = False
                results[f"{provider_name}_error"] = str(e)
        else:
            # Check all available providers
            for p in self._settings.get_available_providers():
                try:
                    provider = ProviderRegistry.get_or_create_provider(p)
                    results[p.value] = await provider.health_check()
                except Exception as e:
                    results[p.value] = False
                    results[f"{p.value}_error"] = str(e)

        return results
