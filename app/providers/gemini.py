"""Google Gemini LLM provider."""

from collections.abc import AsyncIterator
from typing import Any

import google.generativeai as genai
from google.generativeai.types import GenerateContentResponse

from app.core.exceptions import LLMAuthenticationError, LLMProviderError, LLMRateLimitError
from app.core.logging import get_logger
from app.models.llm import ChatMessage, LLMResponse, MessageRole, StreamChunk, TokenUsage, ToolCall
from app.models.tools import Tool
from app.providers.base import BaseLLMProvider

logger = get_logger("gemini_provider")


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider."""

    provider_name = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-1.5-pro",
        max_tokens: int = 8192,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key=api_key, model=model, max_tokens=max_tokens, **kwargs)
        genai.configure(api_key=api_key)
        self.client = genai.GenerativeModel(model)

    def _convert_messages(
        self, messages: list[ChatMessage], system_prompt: str | None = None
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert messages to Gemini format."""
        gemini_messages = []
        system = system_prompt

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system = msg.content
                continue
            gemini_messages.append(msg.to_gemini_format())

        return system, gemini_messages

    def _convert_tools(self, tools: list[Tool] | None) -> list[Any] | None:
        """Convert tools to Gemini format."""
        if not tools:
            return None

        function_declarations = []
        for tool in tools:
            function_declarations.append(
                genai.protos.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters=self._convert_schema_to_gemini(tool.parameters),
                )
            )

        return [genai.protos.Tool(function_declarations=function_declarations)]

    def _convert_schema_to_gemini(self, schema: dict[str, Any]) -> genai.protos.Schema:
        """Convert JSON Schema to Gemini Schema proto."""
        type_mapping = {
            "string": genai.protos.Type.STRING,
            "number": genai.protos.Type.NUMBER,
            "integer": genai.protos.Type.INTEGER,
            "boolean": genai.protos.Type.BOOLEAN,
            "array": genai.protos.Type.ARRAY,
            "object": genai.protos.Type.OBJECT,
        }

        schema_type = type_mapping.get(schema.get("type", "string"), genai.protos.Type.STRING)

        proto_schema = genai.protos.Schema(type=schema_type)

        if "description" in schema:
            proto_schema.description = schema["description"]

        if "properties" in schema:
            for prop_name, prop_schema in schema["properties"].items():
                proto_schema.properties[prop_name].CopyFrom(
                    self._convert_schema_to_gemini(prop_schema)
                )

        if "required" in schema:
            proto_schema.required.extend(schema["required"])

        if "items" in schema:
            proto_schema.items.CopyFrom(self._convert_schema_to_gemini(schema["items"]))

        if "enum" in schema:
            proto_schema.enum.extend(schema["enum"])

        return proto_schema

    def _parse_response(self, response: GenerateContentResponse) -> LLMResponse:
        """Parse Gemini response to unified format."""
        content = ""
        tool_calls = []

        if response.candidates:
            candidate = response.candidates[0]
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    content += part.text
                elif hasattr(part, "function_call"):
                    fc = part.function_call
                    tool_calls.append(
                        ToolCall(
                            id=f"call_{fc.name}_{len(tool_calls)}",
                            name=fc.name,
                            arguments=dict(fc.args) if fc.args else {},
                        )
                    )

        # Determine finish reason
        finish_reason = "stop"
        if tool_calls:
            finish_reason = "tool_calls"
        elif response.candidates and response.candidates[0].finish_reason:
            reason = response.candidates[0].finish_reason.name
            if reason == "MAX_TOKENS":
                finish_reason = "length"
            elif reason == "SAFETY":
                finish_reason = "error"

        # Get usage if available
        usage = None
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = TokenUsage(
                prompt_tokens=response.usage_metadata.prompt_token_count or 0,
                completion_tokens=response.usage_metadata.candidates_token_count or 0,
                total_tokens=response.usage_metadata.total_token_count or 0,
            )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=finish_reason,
            usage=usage,
            model=self.model or "gemini-1.5-pro",
            provider=self.provider_name,
        )

    async def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        tools: list[Tool] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion request to Gemini."""
        system, gemini_messages = self._convert_messages(messages, system_prompt)
        gemini_tools = self._convert_tools(tools)

        logger.debug(
            "gemini_request",
            model=self.model,
            message_count=len(gemini_messages),
            has_tools=gemini_tools is not None,
        )

        try:
            # Create a new model instance with system instruction if provided
            model = self.client
            if system:
                model = genai.GenerativeModel(
                    self.model,
                    system_instruction=system,
                )

            generation_config = genai.GenerationConfig(
                max_output_tokens=self.max_tokens,
            )

            # Start chat and send messages
            chat = model.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])

            last_message = gemini_messages[-1] if gemini_messages else {"parts": [{"text": ""}]}
            last_content = last_message.get("parts", [{}])[0].get("text", "")

            response = await chat.send_message_async(
                last_content,
                generation_config=generation_config,
                tools=gemini_tools,
            )

            result = self._parse_response(response)
            logger.debug(
                "gemini_response",
                finish_reason=result.finish_reason,
                tool_calls=len(result.tool_calls) if result.tool_calls else 0,
            )
            return result

        except Exception as e:
            error_str = str(e).lower()
            if "api key" in error_str or "authentication" in error_str:
                logger.error("gemini_auth_error", error=str(e))
                raise LLMAuthenticationError(
                    "Authentication failed", provider=self.provider_name
                ) from e
            elif "rate" in error_str or "quota" in error_str:
                logger.warning("gemini_rate_limit", error=str(e))
                raise LLMRateLimitError(
                    "Rate limit exceeded", provider=self.provider_name
                ) from e
            else:
                logger.error("gemini_api_error", error=str(e))
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
        """Stream a chat completion response from Gemini."""
        system, gemini_messages = self._convert_messages(messages, system_prompt)
        gemini_tools = self._convert_tools(tools)

        logger.debug(
            "gemini_stream_start",
            model=self.model,
            message_count=len(gemini_messages),
        )

        try:
            model = self.client
            if system:
                model = genai.GenerativeModel(
                    self.model,
                    system_instruction=system,
                )

            generation_config = genai.GenerationConfig(
                max_output_tokens=self.max_tokens,
            )

            chat = model.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])

            last_message = gemini_messages[-1] if gemini_messages else {"parts": [{"text": ""}]}
            last_content = last_message.get("parts", [{}])[0].get("text", "")

            response = await chat.send_message_async(
                last_content,
                generation_config=generation_config,
                tools=gemini_tools,
                stream=True,
            )

            async for chunk in response:
                if chunk.candidates:
                    for part in chunk.candidates[0].content.parts:
                        if hasattr(part, "text") and part.text:
                            yield StreamChunk(content=part.text)
                        elif hasattr(part, "function_call"):
                            fc = part.function_call
                            yield StreamChunk(
                                tool_calls=[
                                    ToolCall(
                                        id=f"call_{fc.name}",
                                        name=fc.name,
                                        arguments=dict(fc.args) if fc.args else {},
                                    )
                                ]
                            )

            yield StreamChunk(done=True, finish_reason="stop")

        except Exception as e:
            error_str = str(e).lower()
            if "api key" in error_str or "authentication" in error_str:
                logger.error("gemini_stream_auth_error", error=str(e))
                raise LLMAuthenticationError(
                    "Authentication failed", provider=self.provider_name
                ) from e
            elif "rate" in error_str or "quota" in error_str:
                logger.warning("gemini_stream_rate_limit", error=str(e))
                raise LLMRateLimitError(
                    "Rate limit exceeded", provider=self.provider_name
                ) from e
            else:
                logger.error("gemini_stream_error", error=str(e))
                raise LLMProviderError(
                    f"Streaming error: {str(e)}",
                    provider=self.provider_name,
                ) from e

    async def health_check(self) -> bool:
        """Check if Gemini API is accessible."""
        try:
            response = await self.client.generate_content_async("Hi")
            return response is not None
        except Exception as e:
            logger.warning("gemini_health_check_failed", error=str(e))
            return False
