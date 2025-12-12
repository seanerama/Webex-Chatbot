"""MCP (Model Context Protocol) tool execution service."""

import asyncio
from typing import Any

import httpx

from app.config import get_settings
from app.core.exceptions import MCPError
from app.core.logging import get_logger, LogEvents
from app.models.llm import ToolCall, ToolResult
from app.models.tools import Tool, ToolRegistry

logger = get_logger("mcp_service")


class MCPService:
    """Service for interacting with FastMCP server and executing tools."""

    def __init__(self, server_url: str | None = None) -> None:
        settings = get_settings()
        self._server_url = server_url or settings.mcp_server_url
        self._enabled = settings.mcp_enabled
        self._tool_registry = ToolRegistry()
        self._client = httpx.AsyncClient(timeout=30.0)
        self._tools_loaded = False

    @property
    def is_enabled(self) -> bool:
        """Check if MCP is enabled."""
        return self._enabled

    async def initialize(self) -> None:
        """Initialize the MCP service and load tools."""
        if not self._enabled:
            logger.info("mcp_disabled")
            return

        try:
            await self.load_tools()
        except Exception as e:
            logger.warning("mcp_init_failed", error=str(e))

    async def load_tools(self) -> list[Tool]:
        """Load available tools from the MCP server."""
        if not self._enabled:
            return []

        try:
            response = await self._client.get(f"{self._server_url}/tools")
            response.raise_for_status()

            tools_data = response.json()
            tools = []

            for tool_data in tools_data.get("tools", []):
                tool = Tool(
                    name=tool_data["name"],
                    description=tool_data.get("description", ""),
                    parameters=tool_data.get("inputSchema", {}),
                )
                self._tool_registry.register(tool)
                tools.append(tool)

            self._tools_loaded = True
            logger.info("mcp_tools_loaded", tool_count=len(tools))
            return tools

        except httpx.HTTPError as e:
            logger.error("mcp_tools_load_failed", error=str(e))
            raise MCPError(f"Failed to load MCP tools: {e}") from e

    def get_tools(self) -> list[Tool]:
        """Get all registered tools."""
        return self._tool_registry.list_tools()

    def get_tools_for_provider(self, provider: str) -> list[dict[str, Any]]:
        """Get tools formatted for a specific provider."""
        return self._tool_registry.to_provider_format(provider)

    async def execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool and return the result."""
        if not self._enabled:
            return ToolResult(
                tool_call_id=tool_call.id,
                content="MCP tools are disabled",
                is_error=True,
            )

        logger.info(
            LogEvents.MCP_TOOL_INVOKED,
            tool_name=tool_call.name,
            tool_id=tool_call.id,
        )

        try:
            response = await self._client.post(
                f"{self._server_url}/tools/{tool_call.name}",
                json={"arguments": tool_call.arguments},
            )

            if response.status_code == 404:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    content=f"Tool '{tool_call.name}' not found",
                    is_error=True,
                )

            response.raise_for_status()
            result_data = response.json()

            # Extract content from result
            content = result_data.get("content", "")
            if isinstance(content, list):
                # Handle array of content blocks
                content_parts = []
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        content_parts.append(item["text"])
                    elif isinstance(item, str):
                        content_parts.append(item)
                content = "\n".join(content_parts)
            elif isinstance(content, dict):
                content = str(content)

            logger.debug(
                LogEvents.MCP_TOOL_RESULT,
                tool_name=tool_call.name,
                result_length=len(content),
            )

            return ToolResult(
                tool_call_id=tool_call.id,
                content=content,
                is_error=result_data.get("isError", False),
            )

        except httpx.HTTPError as e:
            logger.error(
                LogEvents.MCP_TOOL_ERROR,
                tool_name=tool_call.name,
                error=str(e),
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"Tool execution failed: {e}",
                is_error=True,
            )

    async def execute_tools(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        """Execute multiple tools concurrently."""
        if not tool_calls:
            return []

        # Execute all tools concurrently
        tasks = [self.execute_tool(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(
                    ToolResult(
                        tool_call_id=tool_calls[i].id,
                        content=f"Tool execution error: {result}",
                        is_error=True,
                    )
                )
            else:
                final_results.append(result)

        return final_results

    async def health_check(self) -> bool:
        """Check if the MCP server is healthy."""
        if not self._enabled:
            return True  # Considered healthy if disabled

        try:
            response = await self._client.get(f"{self._server_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.warning("mcp_health_check_failed", error=str(e))
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
