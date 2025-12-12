"""Utilities for converting tools between provider formats."""

from typing import Any

from app.models.tools import Tool


def convert_tools_for_provider(
    tools: list[Tool],
    provider: str,
) -> list[dict[str, Any]]:
    """
    Convert a list of tools to a specific provider's format.

    Args:
        tools: List of Tool objects
        provider: Provider name (anthropic, openai, gemini, ollama)

    Returns:
        List of tools in provider-specific format

    Raises:
        ValueError: If provider is unknown
    """
    converters = {
        "anthropic": lambda t: t.to_anthropic_format(),
        "openai": lambda t: t.to_openai_format(),
        "gemini": lambda t: t.to_gemini_format(),
        "ollama": lambda t: t.to_ollama_format(),
    }

    converter = converters.get(provider)
    if not converter:
        raise ValueError(f"Unknown provider: {provider}")

    return [converter(tool) for tool in tools]


def convert_from_mcp_tool(mcp_tool: dict[str, Any]) -> Tool:
    """
    Convert an MCP tool definition to our Tool model.

    Args:
        mcp_tool: Tool definition from MCP server

    Returns:
        Tool object
    """
    return Tool(
        name=mcp_tool["name"],
        description=mcp_tool.get("description", ""),
        parameters=mcp_tool.get("inputSchema", {}),
    )


def convert_from_openai_function(func: dict[str, Any]) -> Tool:
    """
    Convert an OpenAI function definition to our Tool model.

    Args:
        func: OpenAI function definition

    Returns:
        Tool object
    """
    function = func.get("function", func)
    return Tool(
        name=function["name"],
        description=function.get("description", ""),
        parameters=function.get("parameters", {}),
    )


def merge_tool_schemas(*schemas: dict[str, Any]) -> dict[str, Any]:
    """
    Merge multiple JSON schemas into one.

    Useful for combining tool parameters.

    Args:
        *schemas: JSON schemas to merge

    Returns:
        Merged schema
    """
    merged: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    for schema in schemas:
        if "properties" in schema:
            merged["properties"].update(schema["properties"])
        if "required" in schema:
            merged["required"].extend(schema["required"])

    # Dedupe required
    merged["required"] = list(set(merged["required"]))

    return merged


def validate_tool_arguments(
    tool: Tool,
    arguments: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Validate arguments against a tool's parameter schema.

    This is a basic validation - for production use consider
    using a proper JSON Schema validator.

    Args:
        tool: Tool to validate against
        arguments: Arguments to validate

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors: list[str] = []
    schema = tool.parameters

    # Check required parameters
    required = schema.get("required", [])
    for param in required:
        if param not in arguments:
            errors.append(f"Missing required parameter: {param}")

    # Check for unknown parameters
    properties = schema.get("properties", {})
    for arg_name in arguments:
        if arg_name not in properties:
            errors.append(f"Unknown parameter: {arg_name}")

    # Basic type checking
    for arg_name, arg_value in arguments.items():
        if arg_name in properties:
            expected_type = properties[arg_name].get("type")
            if not _check_type(arg_value, expected_type):
                errors.append(
                    f"Invalid type for {arg_name}: expected {expected_type}"
                )

    return len(errors) == 0, errors


def _check_type(value: Any, expected_type: str | None) -> bool:
    """Check if a value matches the expected JSON Schema type."""
    if expected_type is None:
        return True

    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }

    expected = type_map.get(expected_type)
    if expected is None:
        return True  # Unknown type, allow

    return isinstance(value, expected)
