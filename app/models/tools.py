"""Tool/function calling models."""

from typing import Any

from pydantic import BaseModel


class Tool(BaseModel):
    """Unified tool definition (provider-agnostic)."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema format

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI tool format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_gemini_format(self) -> dict[str, Any]:
        """Convert to Gemini tool format."""
        # Convert JSON Schema to Gemini's format
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self._convert_schema_for_gemini(self.parameters),
        }

    def to_ollama_format(self) -> dict[str, Any]:
        """Convert to Ollama tool format (OpenAI-compatible)."""
        return self.to_openai_format()

    def _convert_schema_for_gemini(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Convert JSON Schema to Gemini's expected format."""
        # Gemini uses a subset of JSON Schema
        converted: dict[str, Any] = {}

        if "type" in schema:
            converted["type"] = schema["type"].upper()

        if "properties" in schema:
            converted["properties"] = {
                k: self._convert_schema_for_gemini(v)
                for k, v in schema["properties"].items()
            }

        if "required" in schema:
            converted["required"] = schema["required"]

        if "description" in schema:
            converted["description"] = schema["description"]

        if "items" in schema:
            converted["items"] = self._convert_schema_for_gemini(schema["items"])

        if "enum" in schema:
            converted["enum"] = schema["enum"]

        return converted


class ToolRegistry(BaseModel):
    """Registry of available tools."""

    tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self.tools.get(name)

    def list_tools(self) -> list[Tool]:
        """List all registered tools."""
        return list(self.tools.values())

    def to_provider_format(self, provider: str) -> list[dict[str, Any]]:
        """Convert all tools to a specific provider's format."""
        converter = {
            "anthropic": lambda t: t.to_anthropic_format(),
            "openai": lambda t: t.to_openai_format(),
            "gemini": lambda t: t.to_gemini_format(),
            "ollama": lambda t: t.to_ollama_format(),
        }.get(provider)

        if not converter:
            raise ValueError(f"Unknown provider: {provider}")

        return [converter(tool) for tool in self.tools.values()]
