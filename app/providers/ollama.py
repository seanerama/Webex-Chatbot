"""Ollama local LLM provider."""

import json
from collections.abc import AsyncIterator
from typing import Any

import ollama
from ollama import AsyncClient

from app.core.exceptions import LLMProviderError
from app.core.logging import get_logger
from app.models.llm import ChatMessage, LLMResponse, StreamChunk, TokenUsage, ToolCall
from app.models.tools import Tool
from app.providers.base import BaseLLMProvider

logger = get_logger("ollama_provider")


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider."""

    provider_name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
        timeout: int = 120,
        **kwargs: Any,
    ) -> None:
        super().__init__(base_url=base_url, model=model, timeout=timeout, **kwargs)
        self.client = AsyncClient(host=base_url)

    def _convert_messages(
        self, messages: list[ChatMessage], system_prompt: str | None = None
    ) -> list[dict[str, Any]]:
        """Convert messages to Ollama format (OpenAI-compatible)."""
        ollama_messages = []

        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            ollama_messages.append(msg.to_ollama_format())

        return ollama_messages

    def _convert_tools(self, tools: list[Tool] | None) -> list[dict[str, Any]] | None:
        """Convert tools to Ollama format."""
        if not tools:
            return None
        return [tool.to_ollama_format() for tool in tools]

    def _parse_response(self, response: dict[str, Any]) -> LLMResponse:
        """Parse Ollama response to unified format."""
        message = response.get("message", {})
        content = message.get("content", "")
        tool_calls = []

        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                func = tc.get("function", {})
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                tool_calls.append(
                    ToolCall(
                        id=tc.get("id", f"call_{func.get('name', 'unknown')}"),
                        name=func.get("name", ""),
                        arguments=args,
                    )
                )

        # Determine finish reason
        finish_reason = "stop"
        if tool_calls:
            finish_reason = "tool_calls"
        elif response.get("done_reason") == "length":
            finish_reason = "length"

        # Get usage
        usage = None
        if "prompt_eval_count" in response or "eval_count" in response:
            usage = TokenUsage(
                prompt_tokens=response.get("prompt_eval_count", 0),
                completion_tokens=response.get("eval_count", 0),
                total_tokens=response.get("prompt_eval_count", 0)
                + response.get("eval_count", 0),
            )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=finish_reason,
            usage=usage,
            model=response.get("model", self.model or "unknown"),
            provider=self.provider_name,
        )

    async def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        tools: list[Tool] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion request to Ollama."""
        ollama_messages = self._convert_messages(messages, system_prompt)
        ollama_tools = self._convert_tools(tools)

        logger.debug(
            "ollama_request",
            model=self.model,
            message_count=len(ollama_messages),
            has_tools=ollama_tools is not None,
        )

        try:
            request_kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": ollama_messages,
            }

            if ollama_tools:
                request_kwargs["tools"] = ollama_tools

            response = await self.client.chat(**request_kwargs)

            result = self._parse_response(response)
            logger.debug(
                "ollama_response",
                finish_reason=result.finish_reason,
                tool_calls=len(result.tool_calls) if result.tool_calls else 0,
            )
            return result

        except ollama.ResponseError as e:
            logger.error("ollama_response_error", error=str(e), status_code=e.status_code)
            raise LLMProviderError(
                f"Ollama error: {e.error}",
                provider=self.provider_name,
                status_code=e.status_code,
            ) from e
        except Exception as e:
            logger.error("ollama_error", error=str(e))
            raise LLMProviderError(
                f"Ollama error: {str(e)}",
                provider=self.provider_name,
            ) from e

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        tools: list[Tool] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion response from Ollama."""
        ollama_messages = self._convert_messages(messages, system_prompt)
        ollama_tools = self._convert_tools(tools)

        logger.debug(
            "ollama_stream_start",
            model=self.model,
            message_count=len(ollama_messages),
        )

        try:
            request_kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": ollama_messages,
                "stream": True,
            }

            if ollama_tools:
                request_kwargs["tools"] = ollama_tools

            stream = await self.client.chat(**request_kwargs)

            accumulated_tool_calls: list[dict[str, Any]] = []

            async for chunk in stream:
                message = chunk.get("message", {})

                # Handle text content
                if message.get("content"):
                    yield StreamChunk(content=message["content"])

                # Handle tool calls
                if message.get("tool_calls"):
                    for tc in message["tool_calls"]:
                        accumulated_tool_calls.append(tc)

                # Check for completion
                if chunk.get("done"):
                    # Emit accumulated tool calls
                    if accumulated_tool_calls:
                        tool_calls = []
                        for tc in accumulated_tool_calls:
                            func = tc.get("function", {})
                            args = func.get("arguments", {})
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except json.JSONDecodeError:
                                    args = {}
                            tool_calls.append(
                                ToolCall(
                                    id=tc.get("id", f"call_{func.get('name', 'unknown')}"),
                                    name=func.get("name", ""),
                                    arguments=args,
                                )
                            )
                        yield StreamChunk(tool_calls=tool_calls)

                    finish_reason = "stop"
                    if accumulated_tool_calls:
                        finish_reason = "tool_calls"
                    elif chunk.get("done_reason") == "length":
                        finish_reason = "length"

                    yield StreamChunk(done=True, finish_reason=finish_reason)

        except ollama.ResponseError as e:
            logger.error("ollama_stream_error", error=str(e), status_code=e.status_code)
            raise LLMProviderError(
                f"Ollama streaming error: {e.error}",
                provider=self.provider_name,
                status_code=e.status_code,
            ) from e
        except Exception as e:
            logger.error("ollama_stream_error", error=str(e))
            raise LLMProviderError(
                f"Ollama streaming error: {str(e)}",
                provider=self.provider_name,
            ) from e

    async def health_check(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            # Check if Ollama is running
            models = await self.client.list()

            # Check if our model is available
            model_names = [m.get("name", "") for m in models.get("models", [])]
            model_available = any(self.model in name for name in model_names)

            if not model_available:
                logger.warning(
                    "ollama_model_not_found",
                    model=self.model,
                    available_models=model_names,
                )
                return False

            return True
        except Exception as e:
            logger.warning("ollama_health_check_failed", error=str(e))
            return False

    def supports_tools(self) -> bool:
        """Check if this provider supports tool calling.

        Note: Tool support depends on the specific model being used.
        """
        # Most modern Ollama models support tools
        return True
