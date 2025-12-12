"""OpenAI GPT LLM provider."""

import json
from collections.abc import AsyncIterator
from typing import Any

import openai
from openai import AsyncOpenAI

from app.core.exceptions import LLMAuthenticationError, LLMProviderError, LLMRateLimitError
from app.core.logging import get_logger
from app.models.llm import ChatMessage, LLMResponse, StreamChunk, TokenUsage, ToolCall
from app.models.tools import Tool
from app.providers.base import BaseLLMProvider

logger = get_logger("openai_provider")


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider."""

    provider_name = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key=api_key, model=model, max_tokens=max_tokens, **kwargs)
        self.client = AsyncOpenAI(api_key=api_key)

    def _convert_messages(
        self, messages: list[ChatMessage], system_prompt: str | None = None
    ) -> list[dict[str, Any]]:
        """Convert messages to OpenAI format."""
        openai_messages = []

        # Add system prompt first if provided
        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            openai_messages.append(msg.to_openai_format())

        return openai_messages

    def _convert_tools(self, tools: list[Tool] | None) -> list[dict[str, Any]] | None:
        """Convert tools to OpenAI format."""
        if not tools:
            return None
        return [tool.to_openai_format() for tool in tools]

    def _parse_response(self, response: openai.types.chat.ChatCompletion) -> LLMResponse:
        """Parse OpenAI response to unified format."""
        choice = response.choices[0]
        message = choice.message

        content = message.content or ""
        tool_calls = []

        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args,
                    )
                )

        # Map finish reason
        finish_reason_map = {
            "stop": "stop",
            "tool_calls": "tool_calls",
            "length": "length",
            "content_filter": "error",
        }
        finish_reason = finish_reason_map.get(choice.finish_reason or "stop", "stop")

        return LLMResponse(
            content=content,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=finish_reason,
            usage=TokenUsage.from_openai(response.usage) if response.usage else None,
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
        """Send a chat completion request to OpenAI."""
        openai_messages = self._convert_messages(messages, system_prompt)
        openai_tools = self._convert_tools(tools)

        logger.debug(
            "openai_request",
            model=self.model,
            message_count=len(openai_messages),
            has_tools=openai_tools is not None,
        )

        try:
            request_kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": openai_messages,
            }

            if openai_tools:
                request_kwargs["tools"] = openai_tools

            response = await self.client.chat.completions.create(**request_kwargs)

            result = self._parse_response(response)
            logger.debug(
                "openai_response",
                finish_reason=result.finish_reason,
                tool_calls=len(result.tool_calls) if result.tool_calls else 0,
            )
            return result

        except openai.AuthenticationError as e:
            logger.error("openai_auth_error", error=str(e))
            raise LLMAuthenticationError(
                "Authentication failed", provider=self.provider_name
            ) from e
        except openai.RateLimitError as e:
            logger.warning("openai_rate_limit", error=str(e))
            raise LLMRateLimitError(
                "Rate limit exceeded", provider=self.provider_name
            ) from e
        except openai.APIError as e:
            logger.error("openai_api_error", error=str(e))
            raise LLMProviderError(
                f"API error: {str(e)}",
                provider=self.provider_name,
            ) from e

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        tools: list[Tool] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion response from OpenAI."""
        openai_messages = self._convert_messages(messages, system_prompt)
        openai_tools = self._convert_tools(tools)

        logger.debug(
            "openai_stream_start",
            model=self.model,
            message_count=len(openai_messages),
        )

        try:
            request_kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": openai_messages,
                "stream": True,
            }

            if openai_tools:
                request_kwargs["tools"] = openai_tools

            stream = await self.client.chat.completions.create(**request_kwargs)

            current_tool_calls: dict[int, dict[str, Any]] = {}

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Handle text content
                if delta.content:
                    yield StreamChunk(content=delta.content)

                # Handle tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name if tc.function else "",
                                "arguments": "",
                            }
                        if tc.function and tc.function.arguments:
                            current_tool_calls[idx]["arguments"] += tc.function.arguments

                # Check for finish
                finish_reason = chunk.choices[0].finish_reason
                if finish_reason:
                    # Emit any accumulated tool calls
                    if current_tool_calls:
                        tool_calls = []
                        for tc_data in current_tool_calls.values():
                            try:
                                args = json.loads(tc_data["arguments"])
                            except json.JSONDecodeError:
                                args = {}
                            tool_calls.append(
                                ToolCall(
                                    id=tc_data["id"],
                                    name=tc_data["name"],
                                    arguments=args,
                                )
                            )
                        yield StreamChunk(tool_calls=tool_calls)

                    yield StreamChunk(
                        done=True,
                        finish_reason="tool_calls" if finish_reason == "tool_calls" else "stop",
                    )

        except openai.AuthenticationError as e:
            logger.error("openai_stream_auth_error", error=str(e))
            raise LLMAuthenticationError(
                "Authentication failed", provider=self.provider_name
            ) from e
        except openai.RateLimitError as e:
            logger.warning("openai_stream_rate_limit", error=str(e))
            raise LLMRateLimitError(
                "Rate limit exceeded", provider=self.provider_name
            ) from e
        except openai.APIError as e:
            logger.error("openai_stream_error", error=str(e))
            raise LLMProviderError(
                f"Streaming error: {str(e)}",
                provider=self.provider_name,
            ) from e

    async def health_check(self) -> bool:
        """Check if OpenAI API is accessible."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model or "gpt-4o",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
            )
            return response is not None
        except Exception as e:
            logger.warning("openai_health_check_failed", error=str(e))
            return False
