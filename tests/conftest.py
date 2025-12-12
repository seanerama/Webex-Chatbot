"""Pytest configuration and fixtures."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.webex_bot_token = "test_token"
    settings.webex_webhook_secret = None
    settings.default_llm_provider = MagicMock(value="anthropic")
    settings.default_llm_model = "claude-sonnet-4-20250514"
    settings.anthropic_api_key = "test_key"
    settings.mcp_enabled = False
    settings.app_env = MagicMock(value="development")
    settings.is_development = True
    settings.log_level = "DEBUG"
    return settings


@pytest.fixture
def mock_webex_service():
    """Create mock Webex service."""
    service = MagicMock()
    service.bot_email = "bot@example.com"
    service.bot_id = "bot123"
    service.is_from_self = MagicMock(return_value=False)
    service.get_message = AsyncMock()
    service.send_message = AsyncMock(return_value="msg123")
    service.update_message = AsyncMock()
    return service


@pytest.fixture
def mock_llm_response():
    """Create mock LLM response."""
    from app.models.llm import LLMResponse, TokenUsage

    return LLMResponse(
        content="This is a test response.",
        tool_calls=None,
        finish_reason="stop",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        model="claude-sonnet-4-20250514",
        provider="anthropic",
    )


@pytest.fixture
def sample_chat_messages():
    """Create sample chat messages."""
    from app.models.llm import ChatMessage, MessageRole

    return [
        ChatMessage(role=MessageRole.USER, content="Hello"),
        ChatMessage(role=MessageRole.ASSISTANT, content="Hi there!"),
        ChatMessage(role=MessageRole.USER, content="How are you?"),
    ]


@pytest.fixture
def sample_tool():
    """Create sample tool definition."""
    from app.models.tools import Tool

    return Tool(
        name="search_kb",
        description="Search the knowledge base",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    )


@pytest.fixture
def sample_webhook_payload():
    """Create sample webhook payload."""
    return {
        "id": "webhook123",
        "name": "Test Webhook",
        "targetUrl": "https://example.com/webhook",
        "resource": "messages",
        "event": "created",
        "orgId": "org123",
        "createdBy": "user123",
        "appId": "app123",
        "ownedBy": "creator",
        "status": "active",
        "created": "2024-01-15T10:00:00.000Z",
        "actorId": "actor123",
        "data": {
            "id": "msg123",
            "roomId": "room123",
            "roomType": "direct",
            "personId": "person123",
            "personEmail": "user@example.com",
            "created": "2024-01-15T10:00:00.000Z",
        },
    }
