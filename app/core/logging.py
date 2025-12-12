"""Structured logging configuration using structlog."""

import logging
import sys
from pathlib import Path

import structlog
from structlog.types import Processor

from app.config import get_settings, LogFormat


def setup_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()

    # Ensure log directory exists
    if settings.log_file_path:
        log_path = Path(settings.log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # Shared processors for all outputs
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # Choose renderer based on format
    if settings.log_format == LogFormat.CONSOLE or settings.is_development:
        # Development: colored console output
        final_processors: list[Processor] = [
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # Production: JSON output
        final_processors = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        renderer = structlog.processors.JSONRenderer()

    # Configure structlog
    structlog.configure(
        processors=final_processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # File handler (if configured)
    handlers: list[logging.Handler] = [console_handler]
    if settings.log_file_path:
        file_handler = logging.FileHandler(settings.log_file_path)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers = handlers
    root_logger.setLevel(settings.log_level)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a logger instance with optional component name."""
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(component=name)
    return logger


class LogEvents:
    """Standardized log event names for consistency."""

    # Lifecycle
    APP_STARTING = "app_starting"
    APP_STARTED = "app_started"
    APP_SHUTDOWN = "app_shutdown"

    # Webhook
    WEBHOOK_RECEIVED = "webhook_received"
    WEBHOOK_VALIDATED = "webhook_validated"
    WEBHOOK_VALIDATION_FAILED = "webhook_validation_failed"
    WEBHOOK_PROCESSED = "webhook_processed"

    # Message Processing
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_FROM_SELF = "message_from_self_ignored"
    MESSAGE_UNAUTHORIZED = "message_unauthorized"
    COMMAND_DETECTED = "command_detected"
    COMMAND_EXECUTED = "command_executed"

    # LLM Providers
    LLM_REQUEST_STARTED = "llm_request_started"
    LLM_STREAMING_STARTED = "llm_streaming_started"
    LLM_CHUNK_RECEIVED = "llm_chunk_received"
    LLM_REQUEST_COMPLETED = "llm_request_completed"
    LLM_REQUEST_FAILED = "llm_request_failed"
    LLM_TOOL_CALL = "llm_tool_call"
    LLM_PROVIDER_FALLBACK = "llm_provider_fallback"

    # MCP
    MCP_TOOL_INVOKED = "mcp_tool_invoked"
    MCP_TOOL_RESULT = "mcp_tool_result"
    MCP_TOOL_ERROR = "mcp_tool_error"

    # Webex
    WEBEX_MESSAGE_SENT = "webex_message_sent"
    WEBEX_MESSAGE_UPDATED = "webex_message_updated"
    WEBEX_API_ERROR = "webex_api_error"

    # User/Auth
    USER_AUTHENTICATED = "user_authenticated"
    USER_NOT_WHITELISTED = "user_not_whitelisted"
    USER_CONFIG_LOADED = "user_config_loaded"
    USER_PROVIDER_CHANGED = "user_provider_changed"

    # Conversation History
    HISTORY_RETRIEVED = "history_retrieved"
    HISTORY_UPDATED = "history_updated"
    HISTORY_CLEARED = "history_cleared"
