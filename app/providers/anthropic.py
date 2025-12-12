"""Anthropic Claude LLM provider."""

import json
from collections.abc import AsyncIterator
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from app.core.exceptions import LLMAuthenticationError, LLMProviderError, LLMRateLimitError
from app.core.logging import get_logger
from app.models.llm import ChatMessage, LLMResponse, MessageRole, StreamChunk, TokenUsage, ToolCall
from app.models.tools import Tool
from app.providers.base import BaseLLMProvider

logger = get_logger("anthropic_provider")


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API provider."""

    provider_name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 8192,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key=api_key, model=model, max_tokens=max_tokens, **kwargs)
        self.client = AsyncAnthropic(api_key=api_key)

    def _convert_messages(
        self, messages: list[ChatMessage], system_prompt: str | None = None
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert messages to Anthropic format, extracting system prompt."""
        anthropic_messages = []
        system = system_prompt

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # Anthropic handles system prompts separately
                system = msg.content
                continue
            anthropic_messages.append(msg.to_anthropic_format())

        return system, anthropic_messages

    def _convert_tools(self, tools: list[Tool] | None) -> list[dict[str, Any]] | None:
        """Convert tools to Anthropic format."""
        if not tools:
            return None
        return [tool.to_anthropic_format() for tool in tools]

    def _parse_response(self, response: anthropic.types.Message) -> LLMResponse:
        """Parse Anthropic response to unified format."""
        content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        # Determine finish reason
        finish_reason = "stop"
        if response.stop_reason == "tool_use":
            finish_reason = "tool_calls"
        elif response.stop_reason == "max_tokens":
            finish_reason = "length"

        return LLMResponse(
            content=content,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=finish_reason,
            usage=TokenUsage.from_anthropic(response.usage),
            model=response.model,
            provider=self.provider_name,
        )

    async def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        tools: list[Tool] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion request to Anthropic."""
        system, anthropic_messages = self._convert_messages(messages, system_prompt)
        anthropic_tools = self._convert_tools(tools)

        logger.debug(
            "anthropic_request",
            model=self.model,
            message_count=len(anthropic_messages),
            has_tools=anthropic_tools is not None,
        )

        try:
            request_kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": anthropic_messages,
            }

            if system:
                request_kwargs["system"] = system
            if anthropic_tools:
                request_kwargs["tools"] = anthropic_tools

            response = await self.client.messages.create(**request_kwargs)

            result = self._parse_response(response)
            logger.debug(
                "anthropic_response",
                finish_reason=result.finish_reason,
                tool_calls=len(result.tool_calls) if result.tool_calls else 0,
            )
            return result

        except anthropic.AuthenticationError as e:
            logger.error("anthropic_auth_error", error=str(e))
            raise LLMAuthenticationError(
                "Authentication failed", provider=self.provider_name
            ) from e
        except anthropic.RateLimitError as e:
            logger.warning("anthropic_rate_limit", error=str(e))
            raise LLMRateLimitError(
                "Rate limit exceeded", provider=self.provider_name
            ) from e
        except anthropic.APIError as e:
            logger.error("anthropic_api_error", error=str(e), status_code=e.status_code)
            raise LLMProviderError(
                f"API error: {e.message}",
                provider=self.provider_name,
                status_code=e.status_code,
            ) from e

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        tools: list[Tool] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion response from Anthropic."""
        system, anthropic_messages = self._convert_messages(messages, system_prompt)
        anthropic_tools = self._convert_tools(tools)

        logger.debug(
            "anthropic_stream_start",
            model=self.model,
            message_count=len(anthropic_messages),
        )

        try:
            request_kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": anthropic_messages,
            }

            if system:
                request_kwargs["system"] = system
            if anthropic_tools:
                request_kwargs["tools"] = anthropic_tools

            async with self.client.messages.stream(**request_kwargs) as stream:
                current_tool_call: dict[str, Any] | None = None

                async for event in stream:
                    if event.type == "content_block_start":
                        if hasattr(event.content_block, "type"):
                            if event.content_block.type == "tool_use":
                                current_tool_call = {
                                    "id": event.content_block.id,
                                    "name": event.content_block.name,
                                    "arguments": "",
                                }

                    elif event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            yield StreamChunk(content=event.delta.text)
                        elif hasattr(event.delta, "partial_json"):
                            if current_tool_call:
                                current_tool_call["arguments"] += event.delta.partial_json

                    elif event.type == "content_block_stop":
                        if current_tool_call:
                            try:
                                args = json.loads(current_tool_call["arguments"])
                            except json.JSONDecodeError:
                                args = {}
                            yield StreamChunk(
                                tool_calls=[
                                    ToolCall(
                                        id=current_tool_call["id"],
                                        name=current_tool_call["name"],
                                        arguments=args,
                                    )
                                ]
                            )
                            current_tool_call = None

                    elif event.type == "message_stop":
                        yield StreamChunk(done=True, finish_reason="stop")

        except anthropic.AuthenticationError as e:
            logger.error("anthropic_stream_auth_error", error=str(e))
            raise LLMAuthenticationError(
                "Authentication failed", provider=self.provider_name
            ) from e
        except anthropic.RateLimitError as e:
            logger.warning("anthropic_stream_rate_limit", error=str(e))
            raise LLMRateLimitError(
                "Rate limit exceeded", provider=self.provider_name
            ) from e
        except anthropic.APIError as e:
            logger.error("anthropic_stream_error", error=str(e))
            raise LLMProviderError(
                f"Streaming error: {e.message}",
                provider=self.provider_name,
            ) from e

    async def health_check(self) -> bool:
        """Check if Anthropic API is accessible."""
        try:
            # Make a minimal request to verify API key
            response = await self.client.messages.create(
                model=self.model or "claude-sonnet-4-20250514",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
            )
            return response is not None
        except Exception as e:
            logger.warning("anthropic_health_check_failed", error=str(e))
            return False
