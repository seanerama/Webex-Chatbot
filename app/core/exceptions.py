"""Custom exception classes for the application."""

from typing import Any


class BotException(Exception):
    """Base exception for all bot-related errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - {self.details}"
        return self.message


class ConfigurationError(BotException):
    """Raised when there's a configuration error."""

    pass


class WebexAPIError(BotException):
    """Raised when Webex API calls fail."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.status_code = status_code


class LLMError(BotException):
    """Base exception for LLM-related errors."""

    pass


class LLMProviderError(LLMError):
    """Raised when an LLM provider encounters an error."""

    def __init__(
        self,
        message: str,
        provider: str,
        model: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.provider = provider
        self.model = model
        self.status_code = status_code

    def __str__(self) -> str:
        base = f"[{self.provider}] {self.message}"
        if self.model:
            base = f"[{self.provider}/{self.model}] {self.message}"
        if self.details:
            base = f"{base} - {self.details}"
        return base


class LLMRateLimitError(LLMProviderError):
    """Raised when rate limited by an LLM provider."""

    def __init__(
        self,
        message: str,
        provider: str,
        retry_after: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, provider, **kwargs)
        self.retry_after = retry_after


class LLMAuthenticationError(LLMProviderError):
    """Raised when authentication with an LLM provider fails."""

    pass


class LLMContextLengthError(LLMProviderError):
    """Raised when the context length is exceeded."""

    def __init__(
        self,
        message: str,
        provider: str,
        max_tokens: int | None = None,
        requested_tokens: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, provider, **kwargs)
        self.max_tokens = max_tokens
        self.requested_tokens = requested_tokens


class MCPError(BotException):
    """Raised when MCP tool operations fail."""

    def __init__(
        self,
        message: str,
        tool_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.tool_name = tool_name


class UserNotAuthorizedError(BotException):
    """Raised when a user is not authorized to use the bot."""

    def __init__(self, email: str) -> None:
        super().__init__(f"User not authorized: {email}")
        self.email = email


class ConversationError(BotException):
    """Raised when there's an error with conversation management."""

    pass
