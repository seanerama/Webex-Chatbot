"""LLM request and response models."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Role of a message in the conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """Tool call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    """Result from a tool execution."""

    tool_call_id: str
    content: str
    is_error: bool = False


class ChatMessage(BaseModel):
    """A single message in the conversation (provider-agnostic)."""

    role: MessageRole
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None  # For tool results

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic message format."""
        if self.role == MessageRole.SYSTEM:
            # Anthropic handles system messages separately
            return {"role": "user", "content": f"[System]: {self.content}"}

        if self.role == MessageRole.TOOL:
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": self.tool_call_id,
                        "content": self.content,
                    }
                ],
            }

        if self.role == MessageRole.ASSISTANT and self.tool_calls:
            content: list[dict[str, Any]] = []
            if self.content:
                content.append({"type": "text", "text": self.content})
            for tc in self.tool_calls:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    }
                )
            return {"role": "assistant", "content": content}

        return {"role": self.role.value, "content": self.content}

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI message format."""
        if self.role == MessageRole.SYSTEM:
            return {"role": "system", "content": self.content}

        if self.role == MessageRole.TOOL:
            return {
                "role": "tool",
                "tool_call_id": self.tool_call_id,
                "content": self.content,
            }

        if self.role == MessageRole.ASSISTANT and self.tool_calls:
            return {
                "role": "assistant",
                "content": self.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": str(tc.arguments),
                        },
                    }
                    for tc in self.tool_calls
                ],
            }

        return {"role": self.role.value, "content": self.content}

    def to_gemini_format(self) -> dict[str, Any]:
        """Convert to Gemini message format."""
        if self.role == MessageRole.SYSTEM:
            return {"role": "user", "parts": [{"text": f"[System]: {self.content}"}]}

        if self.role == MessageRole.TOOL:
            return {
                "role": "function",
                "parts": [
                    {
                        "function_response": {
                            "name": self.name or "unknown",
                            "response": {"result": self.content},
                        }
                    }
                ],
            }

        if self.role == MessageRole.ASSISTANT and self.tool_calls:
            parts: list[dict[str, Any]] = []
            if self.content:
                parts.append({"text": self.content})
            for tc in self.tool_calls:
                parts.append(
                    {"function_call": {"name": tc.name, "args": tc.arguments}}
                )
            return {"role": "model", "parts": parts}

        role = "model" if self.role == MessageRole.ASSISTANT else "user"
        return {"role": role, "parts": [{"text": self.content}]}

    def to_ollama_format(self) -> dict[str, Any]:
        """Convert to Ollama message format (OpenAI-compatible)."""
        return self.to_openai_format()


class TokenUsage(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_anthropic(cls, usage: Any) -> "TokenUsage":
        """Create from Anthropic usage object."""
        return cls(
            prompt_tokens=getattr(usage, "input_tokens", 0),
            completion_tokens=getattr(usage, "output_tokens", 0),
            total_tokens=getattr(usage, "input_tokens", 0)
            + getattr(usage, "output_tokens", 0),
        )

    @classmethod
    def from_openai(cls, usage: Any) -> "TokenUsage":
        """Create from OpenAI usage object."""
        return cls(
            prompt_tokens=getattr(usage, "prompt_tokens", 0),
            completion_tokens=getattr(usage, "completion_tokens", 0),
            total_tokens=getattr(usage, "total_tokens", 0),
        )


class LLMResponse(BaseModel):
    """Unified response from any LLM provider."""

    content: str
    tool_calls: list[ToolCall] | None = None
    finish_reason: str  # "stop", "tool_calls", "length", "error"
    usage: TokenUsage | None = None
    model: str
    provider: str


class StreamChunk(BaseModel):
    """Streaming chunk from LLM (provider-agnostic)."""

    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    done: bool = False
    finish_reason: str | None = None
