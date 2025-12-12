# Webex Presales Assistant Bot — Design Guide

> **Purpose**: A Webex Teams chatbot that acts as an AI assistant for presales engineers, helping with networking, storage, and compute questions. Supports multiple LLM providers (Anthropic Claude, OpenAI GPT, Google Gemini, and Ollama) with access to custom FastMCP tools for knowledge base search, product information, and technical documentation.
>
> **Audience**: AI Coding Agent / Development Team
>
> **Note**: This document uses pseudocode for implementation patterns. The coding agent will handle actual code generation.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Configuration Management](#3-configuration-management)
4. [Logging Strategy](#4-logging-strategy)
5. [Core Components](#5-core-components)
6. [Webex Integration](#6-webex-integration)
7. [LLM Provider Abstraction](#7-llm-provider-abstraction)
8. [MCP Integration](#8-mcp-integration)
9. [Conversation History Management](#9-conversation-history-management)
10. [User Management & Access Control](#10-user-management--access-control)
11. [Message Flow & Response Handling](#11-message-flow--response-handling)
12. [Error Handling](#12-error-handling)
13. [Local Development Setup](#13-local-development-setup)
14. [API Reference](#14-api-reference)
15. [Testing Strategy](#15-testing-strategy)
16. [Future Considerations](#16-future-considerations)

---

## 1. Architecture Overview

### High-Level Architecture

```
┌─────────────────┐     HTTPS      ┌─────────────────┐
│   Webex Cloud   │◄──────────────►│     ngrok       │
└─────────────────┘                └────────┬────────┘
                                            │
                                            ▼ localhost:8000
┌───────────────────────────────────────────────────────────────┐
│                      FastAPI Application                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │  Webhook    │  │   User      │  │   Conversation      │   │
│  │  Handler    │  │   Manager   │  │   History Store     │   │
│  └──────┬──────┘  └─────────────┘  └─────────────────────┘   │
│         │                                                      │
│         ▼                                                      │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              Message Processing Pipeline                 │  │
│  │  ┌─────────┐  ┌─────────────┐  ┌───────────────────┐   │  │
│  │  │ Logging │─►│ Auth Check  │─►│ Command Router    │   │  │
│  │  └─────────┘  └─────────────┘  └─────────┬─────────┘   │  │
│  └──────────────────────────────────────────┼──────────────┘  │
│                                              │                  │
│                                              ▼                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              LLM Provider Abstraction Layer              │  │
│  │  ┌─────────────────────────────────────────────────┐    │  │
│  │  │              BaseLLMProvider (ABC)               │    │  │
│  │  │  - chat()      - stream()     - health_check()  │    │  │
│  │  │  - get_tools() - supports_tools()               │    │  │
│  │  └─────────────────────────────────────────────────┘    │  │
│  │         ▲              ▲              ▲          ▲       │  │
│  │         │              │              │          │       │  │
│  │  ┌──────┴───┐  ┌──────┴───┐  ┌──────┴───┐ ┌────┴────┐  │  │
│  │  │ Anthropic │  │  OpenAI  │  │  Gemini  │ │  Ollama │  │  │
│  │  │ Provider  │  │ Provider │  │ Provider │ │ Provider│  │  │
│  │  └──────────┘  └──────────┘  └──────────┘ └─────────┘  │  │
│  │                                                          │  │
│  │  ┌─────────────────────────────────────────────────┐    │  │
│  │  │            Provider Registry / Factory           │    │  │
│  │  └─────────────────────────────────────────────────┘    │  │
│  └─────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                    MCP Tool Router                       │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌────────────────┐  │  │
│  │  │   Tool      │  │  Execution  │  │    Response    │  │  │
│  │  │  Registry   │  │   Engine    │  │   Formatter    │  │  │
│  │  └─────────────┘  └─────────────┘  └────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                     FastMCP Server                             │
│                    (Custom Tools)                              │
└───────────────────────────────────────────────────────────────┘
```

### Supported LLM Providers

| Provider | Streaming | Tool Calling | Local | Notes |
|----------|-----------|--------------|-------|-------|
| **Anthropic (Claude)** | ✅ | ✅ | ❌ | Best tool use, extended thinking |
| **OpenAI (GPT-4)** | ✅ | ✅ | ❌ | Function calling, JSON mode |
| **Google (Gemini)** | ✅ | ✅ | ❌ | Multimodal, large context |
| **Ollama** | ✅ | ✅ | ✅ | Privacy, no API costs |

### Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Web Framework | FastAPI | Async support, automatic OpenAPI docs, Pydantic validation |
| Webex SDK | webexteamssdk | Official SDK, well-maintained |
| HTTP Client | httpx | Async support, streaming responses |
| Logging | structlog | Structured JSON logs, excellent for debugging |
| Configuration | python-dotenv + Pydantic Settings | Type-safe, validation, .env support |
| Data Storage | In-memory (dict) | Simple, sufficient for conversation history |
| Tunnel | ngrok | Industry standard for local webhook development |

### Design Principles

1. **Provider Agnostic**: Core logic doesn't depend on specific LLM provider
2. **Separation of Concerns**: Each module has a single responsibility
3. **Async-First**: All I/O operations are async for better performance
4. **Fail-Safe**: Graceful degradation, provider fallback support
5. **Observable**: Comprehensive logging at every decision point
6. **Configurable**: Per-user providers, models, and system prompts

---

## 2. Project Structure

```
webex-presales-assistant/
├── .env                          # Environment variables (git-ignored)
├── .env.example                  # Template for environment variables
├── pyproject.toml                # Project dependencies and metadata
├── README.md                     # Quick start guide
│
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI application entry point
│   ├── config.py                 # Pydantic settings and configuration
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── logging.py            # Structlog configuration
│   │   └── exceptions.py         # Custom exception classes
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── webex.py              # Webex webhook payload models
│   │   ├── llm.py                # Unified LLM request/response models
│   │   ├── tools.py              # Tool/function calling models
│   │   └── user.py               # User and conversation models
│   │
│   ├── providers/                # LLM Provider Abstraction Layer
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract base provider class
│   │   ├── registry.py           # Provider registry and factory
│   │   ├── anthropic.py          # Claude API provider
│   │   ├── openai.py             # OpenAI API provider
│   │   ├── gemini.py             # Google Gemini provider
│   │   └── ollama.py             # Ollama local provider
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── webex_service.py      # Webex API interactions
│   │   ├── llm_service.py        # Unified LLM orchestration service
│   │   ├── mcp_service.py        # MCP tool execution service
│   │   ├── user_service.py       # User management and auth
│   │   └── history_service.py    # Conversation history management
│   │
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── webhook_handler.py    # Webhook processing logic
│   │   ├── command_handler.py    # Slash command processing
│   │   └── message_handler.py    # Natural language processing
│   │
│   └── utils/
│       ├── __init__.py
│       ├── markdown_detector.py  # Detect markdown in responses
│       ├── message_chunker.py    # Split long messages for Webex
│       └── tool_converter.py     # Convert tools between provider formats
│
├── scripts/
│   ├── setup_webhook.py          # One-time webhook registration
│   └── test_providers.py         # Verify provider connectivity
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Pytest fixtures
│   ├── test_providers/           # Provider-specific tests
│   │   ├── test_base.py
│   │   ├── test_anthropic.py
│   │   ├── test_openai.py
│   │   ├── test_gemini.py
│   │   └── test_ollama.py
│   ├── test_llm_service.py
│   └── test_user_service.py
│
└── logs/                         # Log files directory (git-ignored)
    └── .gitkeep
```

---

## 3. Configuration Management

### Environment Variables (.env)

```bash
# =============================================================================
# Webex Configuration
# =============================================================================
WEBEX_BOT_TOKEN=your_bot_access_token_here
WEBEX_WEBHOOK_SECRET=your_webhook_secret_here  # Optional but recommended

# =============================================================================
# Default LLM Provider (used when user has no preference)
# Options: anthropic, openai, gemini, ollama
# =============================================================================
DEFAULT_LLM_PROVIDER=anthropic
DEFAULT_LLM_MODEL=claude-sonnet-4-20250514

# =============================================================================
# Anthropic (Claude) Configuration
# =============================================================================
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514
ANTHROPIC_MAX_TOKENS=8192

# =============================================================================
# OpenAI Configuration
# =============================================================================
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
OPENAI_MAX_TOKENS=4096

# =============================================================================
# Google Gemini Configuration
# =============================================================================
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-1.5-pro
GEMINI_MAX_TOKENS=8192

# =============================================================================
# Ollama Configuration (Local)
# =============================================================================
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_TIMEOUT=120

# =============================================================================
# FastMCP Configuration
# =============================================================================
MCP_SERVER_URL=http://localhost:8080
MCP_ENABLED=true

# =============================================================================
# Application Settings
# =============================================================================
APP_HOST=0.0.0.0
APP_PORT=8000
APP_ENV=development
DEBUG=true

# =============================================================================
# Logging Configuration
# =============================================================================
LOG_LEVEL=DEBUG
LOG_FORMAT=json
LOG_FILE_PATH=./logs/bot.log
LOG_ROTATION_SIZE=10MB
LOG_RETENTION_DAYS=7

# =============================================================================
# ngrok Configuration (for local development)
# =============================================================================
NGROK_AUTHTOKEN=your_ngrok_auth_token  # Optional, for reserved domains
```

### Configuration Class (app/config.py) - Pseudocode

```
CLASS Settings:
    # Webex
    webex_bot_token: string (required)
    webex_webhook_secret: string (optional)
    
    # Default Provider
    default_llm_provider: enum[anthropic, openai, gemini, ollama]
    default_llm_model: string
    
    # Anthropic
    anthropic_api_key: string (optional)
    anthropic_model: string = "claude-sonnet-4-20250514"
    anthropic_max_tokens: int = 8192
    
    # OpenAI
    openai_api_key: string (optional)
    openai_model: string = "gpt-4o"
    openai_max_tokens: int = 4096
    
    # Gemini
    gemini_api_key: string (optional)
    gemini_model: string = "gemini-1.5-pro"
    gemini_max_tokens: int = 8192
    
    # Ollama
    ollama_base_url: string = "http://localhost:11434"
    ollama_model: string = "llama3.1:8b"
    ollama_timeout: int = 120
    
    # MCP
    mcp_server_url: string
    mcp_enabled: bool = true
    
    # Application
    app_host, app_port, app_env, debug
    
    # Logging
    log_level, log_format, log_file_path
    
    METHOD get_provider_config(provider_name) -> ProviderConfig:
        """Return config dict for specified provider"""
        MATCH provider_name:
            "anthropic" -> return {api_key, model, max_tokens}
            "openai" -> return {api_key, model, max_tokens}
            "gemini" -> return {api_key, model, max_tokens}
            "ollama" -> return {base_url, model, timeout}
    
    METHOD get_available_providers() -> list[string]:
        """Return list of providers with valid configuration"""
        providers = []
        IF anthropic_api_key: providers.append("anthropic")
        IF openai_api_key: providers.append("openai")
        IF gemini_api_key: providers.append("gemini")
        providers.append("ollama")  # Always available (local)
        RETURN providers

FUNCTION get_settings() -> Settings:
    """Cached settings instance using lru_cache"""
```

### User Configuration (users.json)

Per-user provider preferences, system prompts, and settings:

```json
{
  "users": {
    "alice@example.com": {
      "enabled": true,
      "display_name": "Alice - Network Specialist",
      "provider": "anthropic",
      "model": "claude-sonnet-4-20250514",
      "system_prompt": "You are a technical presales assistant specializing in enterprise networking solutions. Help with network architecture, SD-WAN, routing protocols, and security. Provide accurate technical details and help prepare customer-facing materials.",
      "preferences": {
        "response_style": "technical",
        "max_response_length": 4000,
        "include_references": true,
        "streaming": true
      }
    },
    "bob@example.com": {
      "enabled": true,
      "display_name": "Bob - Storage Solutions",
      "provider": "ollama",
      "model": "llama3.1:8b",
      "system_prompt": "You are a presales engineer assistant focused on storage and data management solutions. Help with SAN/NAS architecture, backup strategies, data protection, and storage sizing calculations.",
      "preferences": {
        "response_style": "detailed",
        "streaming": true
      }
    },
    "admin@example.com": {
      "enabled": true,
      "display_name": "Admin",
      "provider": "openai",
      "model": "gpt-4o",
      "system_prompt": "You are a senior presales architect assistant with expertise across networking, storage, compute, and cloud infrastructure. Provide comprehensive technical guidance and help with complex multi-domain solutions.",
      "is_admin": true
    }
  },
  "default_system_prompt": "You are a helpful AI assistant for presales engineers. You help answer technical questions about networking, storage, compute, and cloud infrastructure. Provide accurate, detailed responses and cite sources when possible. If you're unsure about something, say so rather than guessing.",
  "default_preferences": {
    "response_style": "balanced",
    "max_response_length": 4000,
    "include_references": true,
    "streaming": true
  }
}
```

### Provider Selection Priority

```
1. User-specific provider (from users.json)
2. Per-message override (via /model command)
3. Default provider (from .env)
4. Fallback chain (if primary fails): anthropic -> openai -> gemini -> ollama
```

---

## 4. Logging Strategy

### Logging Philosophy

Every significant event should be logged with enough context to debug issues without access to the running system. Logs are structured JSON for easy parsing and analysis.

### Log Levels Usage

| Level | Use For | Examples |
|-------|---------|----------|
| DEBUG | Detailed diagnostic info | Request/response bodies, state transitions |
| INFO | Normal operations | Incoming messages, successful responses |
| WARNING | Unexpected but handled | Rate limits, retry attempts, provider fallbacks |
| ERROR | Failures requiring attention | API errors, timeouts, auth failures |
| CRITICAL | System-level failures | Unable to start, all providers down |

### Structured Logging Setup (app/core/logging.py) - Pseudocode

```
FUNCTION setup_logging():
    """Configure structured logging for the application"""
    settings = get_settings()
    
    # Ensure log directory exists
    IF settings.log_file_path:
        CREATE_DIRECTORY(parent_of(settings.log_file_path))
    
    # Shared processors for all outputs
    shared_processors = [
        merge_contextvars,      # Include bound context
        add_log_level,          # Add level field
        add_timestamp_iso,      # ISO format timestamps
        render_stack_info,      # Include stack traces
        decode_unicode          # Handle unicode properly
    ]
    
    # Development: colored console output
    # Production: JSON output
    IF settings.log_format == "console" OR settings.is_development:
        processors = shared_processors + [ConsoleRenderer(colors=true)]
    ELSE:
        processors = shared_processors + [format_exc_info, JSONRenderer()]
    
    CONFIGURE_STRUCTLOG(
        processors=processors,
        min_level=settings.log_level,
        cache_logger=true
    )


FUNCTION get_logger(name: string = None) -> BoundLogger:
    """Get a logger instance with optional component name"""
    logger = structlog.get_logger()
    IF name:
        logger = logger.bind(component=name)
    RETURN logger
```

### Logging Context Pattern - Pseudocode

```
ASYNC FUNCTION process_webhook(request_id: string, message_data: dict):
    # Clear any existing context and bind new values
    clear_contextvars()
    bind_contextvars(
        request_id=request_id,
        user_email=message_data.get("personEmail"),
        room_id=message_data.get("roomId")
    )
    
    logger = get_logger()
    
    # All subsequent logs automatically include this context
    logger.info("processing_webhook_started")
    
    # ... processing logic ...
    
    logger.info("processing_webhook_completed", duration_ms=elapsed)
```

### Log Event Catalog - Pseudocode

```
CLASS LogEvents:
    """Standardized log event names for consistency"""
    
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
    
    # LLM Providers (generic)
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
```

### Example Log Output (JSON)

```json
{
  "event": "llm_request_completed",
  "level": "info",
  "timestamp": "2024-01-15T10:30:45.123456Z",
  "request_id": "req_abc123",
  "user_email": "alice@example.com",
  "room_id": "Y2lzY29...",
  "component": "llm_service",
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514",
  "prompt_tokens": 256,
  "completion_tokens": 512,
  "duration_ms": 3450,
  "tool_calls": 2,
  "streamed": true
}
```

---

## 5. Core Components

### 5.1 Models (Pydantic Data Classes) - Pseudocode

#### Webex Models (app/models/webex.py)

```
ENUM WebhookResource:
    MESSAGES = "messages"
    MEMBERSHIPS = "memberships"
    ROOMS = "rooms"


ENUM WebhookEvent:
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


CLASS WebhookData:
    """Data payload from webhook"""
    id: string
    room_id: string (alias: "roomId")
    room_type: string (optional, alias: "roomType")
    person_id: string (alias: "personId")
    person_email: string (alias: "personEmail")
    created: datetime


CLASS WebhookPayload:
    """Complete webhook payload from Webex"""
    id: string
    name: string
    target_url: string (alias: "targetUrl")
    resource: WebhookResource
    event: WebhookEvent
    org_id: string (alias: "orgId")
    created_by: string (alias: "createdBy")
    app_id: string (alias: "appId")
    owned_by: string (alias: "ownedBy")
    status: string
    created: datetime
    actor_id: string (alias: "actorId")
    data: WebhookData


CLASS WebexMessage:
    """Message retrieved from Webex API"""
    id: string
    room_id: string (alias: "roomId")
    room_type: string (alias: "roomType")
    text: string (optional)
    markdown: string (optional)
    html: string (optional)
    person_id: string (alias: "personId")
    person_email: string (alias: "personEmail")
    created: datetime
    
    PROPERTY content -> string:
        """Get message content, preferring markdown"""
        RETURN self.markdown OR self.text OR ""
```

#### LLM Models (app/models/llm.py)

```
ENUM MessageRole:
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


CLASS ToolCall:
    """Tool call requested by the model"""
    id: string
    name: string
    arguments: dict


CLASS ToolResult:
    """Result from a tool execution"""
    tool_call_id: string
    content: string
    is_error: bool = false


CLASS ChatMessage:
    """A single message in the conversation (provider-agnostic)"""
    role: MessageRole
    content: string
    tool_calls: list[ToolCall] (optional)
    tool_call_id: string (optional)
    
    METHOD to_anthropic_format() -> dict:
        """Convert to Anthropic message format"""
        # Anthropic uses 'tool_use' blocks for tool calls
        ...
    
    METHOD to_openai_format() -> dict:
        """Convert to OpenAI message format"""
        # OpenAI uses 'function_call' in message
        ...
    
    METHOD to_gemini_format() -> dict:
        """Convert to Gemini message format"""
        # Gemini uses 'parts' with function_call
        ...
    
    METHOD to_ollama_format() -> dict:
        """Convert to Ollama message format"""
        # Ollama follows OpenAI-like format
        ...


CLASS LLMResponse:
    """Unified response from any LLM provider"""
    content: string
    tool_calls: list[ToolCall] (optional)
    finish_reason: string  # "stop", "tool_calls", "length", "error"
    usage: TokenUsage (optional)
    model: string
    provider: string


CLASS TokenUsage:
    """Token usage statistics"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


CLASS StreamChunk:
    """Streaming chunk from LLM (provider-agnostic)"""
    content: string (optional)
    tool_calls: list[ToolCall] (optional)
    done: bool
    finish_reason: string (optional)
```

#### Tool Models (app/models/tools.py)

```
CLASS Tool:
    """Unified tool definition (provider-agnostic)"""
    name: string
    description: string
    parameters: dict  # JSON Schema format
    
    METHOD to_anthropic_format() -> dict:
        RETURN {
            name: self.name,
            description: self.description,
            input_schema: self.parameters
        }
    
    METHOD to_openai_format() -> dict:
        RETURN {
            type: "function",
            function: {
                name: self.name,
                description: self.description,
                parameters: self.parameters
            }
        }
    
    METHOD to_gemini_format() -> FunctionDeclaration:
        # Gemini uses Protocol Buffers format
        RETURN FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=convert_json_schema_to_gemini(self.parameters)
        )
    
    METHOD to_ollama_format() -> dict:
        # Ollama uses OpenAI-compatible format
        RETURN self.to_openai_format()
```

#### User Models (app/models/user.py)

```
CLASS UserPreferences:
    """User-specific preferences"""
    response_style: string = "balanced"  # technical, detailed, concise, balanced
    max_response_length: int = 4000 (min: 100, max: 7000)
    include_references: bool = true
    streaming: bool = true


CLASS UserConfig:
    """Configuration for an authorized user"""
    enabled: bool = true
    display_name: string (optional)
    provider: string (optional)  # anthropic, openai, gemini, ollama
    model: string (optional)     # Override default model
    system_prompt: string (optional)
    preferences: UserPreferences = default
    is_admin: bool = false


CLASS ConversationContext:
    """Conversation context for a room/DM"""
    room_id: string
    user_email: string
    messages: list[dict] = []
    created_at: string
    last_updated: string
    message_count: int = 0
    provider_used: string (optional)  # Track provider for this conversation
```

---

## 6. Webex Integration

### Webex Service (app/services/webex_service.py) - Pseudocode

```
CONSTANTS:
    MAX_MESSAGE_LENGTH = 7439  # Webex message length limit


CLASS WebexService:
    """Service for Webex API operations"""
    
    CONSTRUCTOR():
        settings = get_settings()
        self._api = WebexTeamsAPI(access_token=settings.webex_bot_token)
        self._bot_info = None  # Cached bot info
    
    PROPERTY bot_email -> string:
        """Get the bot's email address (cached)"""
        IF self._bot_info IS None:
            self._bot_info = self._api.people.me()
        RETURN self._bot_info.emails[0]
    
    PROPERTY bot_id -> string:
        """Get the bot's person ID (cached)"""
        IF self._bot_info IS None:
            self._bot_info = self._api.people.me()
        RETURN self._bot_info.id
    
    ASYNC METHOD get_message(message_id: string) -> WebexMessage:
        """Retrieve a message by ID"""
        LOG.debug("fetching_message", message_id=message_id)
        
        TRY:
            # Run sync SDK call in thread pool
            message = AWAIT run_in_executor(
                self._api.messages.get, message_id
            )
            
            LOG.debug("message_fetched",
                message_id=message_id,
                has_text=bool(message.text),
                has_markdown=bool(message.markdown)
            )
            
            RETURN WebexMessage.from_dict(message.to_dict())
            
        CATCH ApiError as e:
            LOG.error("webex_api_error", message_id=message_id, error=e)
            RAISE WebexAPIError(f"Failed to get message: {e}")
    
    ASYNC METHOD send_message(
        room_id: string,
        text: string = None,
        markdown: string = None
    ) -> string:
        """
        Send a message to a room.
        Automatically chunks long messages into multiple sends.
        Returns: The message ID of the last sent message
        """
        content = markdown OR text OR ""
        
        # Chunk if necessary
        chunks = chunk_message(content, MAX_MESSAGE_LENGTH)
        
        LOG.info("sending_message",
            room_id=room_id,
            content_length=len(content),
            chunk_count=len(chunks)
        )
        
        last_message_id = None
        
        FOR i, chunk IN enumerate(chunks):
            TRY:
                kwargs = {roomId: room_id}
                IF markdown:
                    kwargs.markdown = chunk
                ELSE:
                    kwargs.text = chunk
                
                message = AWAIT run_in_executor(
                    self._api.messages.create, **kwargs
                )
                
                last_message_id = message.id
                
                LOG.debug("webex_message_sent",
                    message_id=message.id,
                    chunk_index=i
                )
                
                # Small delay between chunks to avoid rate limiting
                IF i < len(chunks) - 1:
                    AWAIT sleep(0.5)
                    
            CATCH ApiError as e:
                LOG.error("webex_api_error", room_id=room_id, error=e)
                RAISE WebexAPIError(f"Failed to send message: {e}")
        
        RETURN last_message_id
    
    ASYNC METHOD update_message(
        message_id: string,
        room_id: string,
        text: string = None,
        markdown: string = None
    ):
        """Update an existing message (for streaming updates)"""
        TRY:
            kwargs = {messageId: message_id, roomId: room_id}
            IF markdown:
                kwargs.markdown = markdown
            ELSE:
                kwargs.text = text
            
            AWAIT run_in_executor(
                self._api.messages.update, **kwargs
            )
            
            LOG.debug("webex_message_updated", message_id=message_id)
            
        CATCH ApiError as e:
            LOG.warning("message_update_failed", message_id=message_id, error=e)
            # Don't raise - update failures are non-critical for streaming
    
    METHOD is_from_self(person_email: string) -> bool:
        """Check if a message is from the bot itself"""
        RETURN person_email == self.bot_email
```

### Webhook Handler (app/handlers/webhook_handler.py) - Pseudocode

```
CLASS WebhookHandler:
    """Handles incoming webhooks from Webex"""
    
    CONSTRUCTOR(
        webex_service: WebexService,
        user_service: UserService,
        message_handler: MessageHandler
    ):
        self.webex = webex_service
        self.users = user_service
        self.messages = message_handler
        self.settings = get_settings()
    
    ASYNC METHOD validate_signature(request: Request, body: bytes) -> bool:
        """Validate webhook signature if secret is configured"""
        IF NOT self.settings.webex_webhook_secret:
            LOG.debug("webhook_signature_check_skipped", reason="no_secret")
            RETURN true
        
        signature = request.headers.get("X-Spark-Signature")
        IF NOT signature:
            LOG.warning("webhook_validation_failed", reason="missing_signature")
            RETURN false
        
        expected = hmac_sha1(
            key=self.settings.webex_webhook_secret,
            message=body
        )
        
        IF NOT secure_compare(signature, expected):
            LOG.warning("webhook_validation_failed", reason="invalid_signature")
            RETURN false
        
        LOG.debug("webhook_validated")
        RETURN true
    
    ASYNC METHOD handle(request: Request) -> dict:
        """Process an incoming webhook"""
        # Read and validate body
        body = AWAIT request.body()
        
        IF NOT AWAIT self.validate_signature(request, body):
            RAISE HTTPException(status=401, detail="Invalid signature")
        
        # Parse payload
        TRY:
            payload = WebhookPayload.parse_json(body)
        CATCH Exception as e:
            LOG.error("webhook_parse_error", error=e)
            RAISE HTTPException(status=400, detail="Invalid payload")
        
        LOG.info("webhook_received",
            webhook_id=payload.id,
            resource=payload.resource,
            event=payload.event,
            actor_email=payload.data.person_email
        )
        
        # Only process message:created events
        IF payload.resource != "messages" OR payload.event != "created":
            LOG.debug("webhook_ignored", reason="not_message_created")
            RETURN {status: "ignored"}
        
        # Ignore messages from self
        IF self.webex.is_from_self(payload.data.person_email):
            LOG.debug("message_from_self_ignored")
            RETURN {status: "ignored"}
        
        # Check user authorization
        IF NOT self.users.is_authorized(payload.data.person_email):
            LOG.warning("user_not_whitelisted", email=payload.data.person_email)
            AWAIT self.webex.send_message(
                room_id=payload.data.room_id,
                text="⚠️ Sorry, you are not authorized to use this bot."
            )
            RETURN {status: "unauthorized"}
        
        # Fetch full message content
        message = AWAIT self.webex.get_message(payload.data.id)
        
        # Process the message
        AWAIT self.messages.handle(message)
        
        LOG.info("webhook_processed", message_id=payload.data.id)
        RETURN {status: "processed"}
```

### Message Chunker Utility (app/utils/message_chunker.py) - Pseudocode

```
FUNCTION chunk_message(content: string, max_length: int) -> list[string]:
    """
    Split a long message into chunks that fit within Webex limits.
    Tries to split at natural boundaries (paragraphs, newlines, sentences, spaces).
    """
    IF len(content) <= max_length:
        RETURN [content]
    
    chunks = []
    remaining = content
    
    WHILE len(remaining) > max_length:
        # Find best split point
        chunk = remaining[:max_length]
        
        # Try to split at paragraph boundary
        split_point = chunk.rfind("\n\n")
        
        # Fall back to newline
        IF split_point < max_length * 0.5:
            split_point = chunk.rfind("\n")
        
        # Fall back to sentence boundary
        IF split_point < max_length * 0.5:
            FOR delimiter IN [". ", "! ", "? "]:
                pos = chunk.rfind(delimiter)
                IF pos > split_point:
                    split_point = pos + 1
        
        # Fall back to space
        IF split_point < max_length * 0.5:
            split_point = chunk.rfind(" ")
        
        # Worst case: hard cut
        IF split_point < max_length * 0.3:
            split_point = max_length
        
        chunks.append(remaining[:split_point].strip())
        remaining = remaining[split_point:].strip()
    
    IF remaining:
        chunks.append(remaining)
    
    RETURN chunks
```

### Markdown Detector Utility (app/utils/markdown_detector.py) - Pseudocode

```
# Patterns that indicate markdown content
MARKDOWN_PATTERNS = [
    r"```",                    # Code blocks
    r"^#{1,6}\s",              # Headers
    r"^\s*[-*+]\s",            # Unordered lists
    r"^\s*\d+\.\s",            # Ordered lists
    r"\*\*[^*]+\*\*",          # Bold
    r"\*[^*]+\*",              # Italic
    r"__[^_]+__",              # Bold (alt)
    r"_[^_]+_",                # Italic (alt)
    r"\[.+\]\(.+\)",           # Links
    r"^\s*>\s",                # Blockquotes
    r"\|.+\|",                 # Tables
]


FUNCTION contains_markdown(text: string) -> bool:
    """Check if text contains markdown formatting"""
    FOR pattern IN MARKDOWN_PATTERNS:
        IF regex_search(pattern, text, MULTILINE):
            RETURN true
    RETURN false
```

---

## 7. LLM Provider Abstraction

### Overview

The provider abstraction layer enables seamless switching between LLM backends while maintaining a consistent interface for the rest of the application. Each provider handles its own API specifics, authentication, and response formatting.

### Unified Models (app/models/llm.py) - Pseudocode

```
ENUM MessageRole:
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

CLASS ChatMessage:
    role: MessageRole
    content: string
    tool_calls: list[ToolCall] (optional)
    tool_call_id: string (optional)
    
    METHOD to_anthropic_format() -> dict
    METHOD to_openai_format() -> dict
    METHOD to_gemini_format() -> dict
    METHOD to_ollama_format() -> dict

CLASS ToolCall:
    id: string
    name: string
    arguments: dict
    
CLASS ToolResult:
    tool_call_id: string
    content: string
    is_error: bool = false

CLASS LLMResponse:
    content: string
    tool_calls: list[ToolCall] (optional)
    finish_reason: string  # "stop", "tool_calls", "length", "error"
    usage: TokenUsage (optional)
    model: string
    provider: string

CLASS TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

CLASS StreamChunk:
    content: string (optional)
    tool_calls: list[ToolCall] (optional)
    done: bool
    finish_reason: string (optional)
```

### Base Provider Interface (app/providers/base.py) - Pseudocode

```
ABSTRACT CLASS BaseLLMProvider:
    """
    Abstract base class for all LLM providers.
    Defines the contract that all providers must implement.
    """
    
    PROPERTY name -> string:
        """Provider identifier (anthropic, openai, gemini, ollama)"""
        ABSTRACT
    
    PROPERTY supports_streaming -> bool:
        """Whether provider supports streaming responses"""
        RETURN true  # Default, override if needed
    
    PROPERTY supports_tools -> bool:
        """Whether provider supports tool/function calling"""
        RETURN true  # Default, override if needed
    
    ABSTRACT ASYNC METHOD chat(
        messages: list[ChatMessage],
        system_prompt: string (optional),
        tools: list[Tool] (optional),
        max_tokens: int (optional),
        temperature: float = 0.7
    ) -> LLMResponse:
        """
        Send a chat completion request.
        Returns complete response (non-streaming).
        """
        PASS
    
    ABSTRACT ASYNC METHOD stream(
        messages: list[ChatMessage],
        system_prompt: string (optional),
        tools: list[Tool] (optional),
        max_tokens: int (optional),
        temperature: float = 0.7
    ) -> AsyncIterator[StreamChunk]:
        """
        Send a streaming chat completion request.
        Yields chunks as they arrive.
        """
        PASS
    
    ABSTRACT ASYNC METHOD health_check() -> bool:
        """Check if provider is available and configured."""
        PASS
    
    METHOD convert_tools_to_provider_format(tools: list[Tool]) -> list[dict]:
        """Convert unified tool format to provider-specific format."""
        # Default implementation, override per provider
        RETURN [tool.to_dict() FOR tool IN tools]
    
    METHOD convert_response_to_unified(raw_response: dict) -> LLMResponse:
        """Convert provider response to unified format."""
        ABSTRACT


CLASS ProviderConfig:
    """Configuration for a provider instance."""
    api_key: string (optional)
    base_url: string (optional)
    model: string
    max_tokens: int
    timeout: int = 120
    extra_options: dict = {}
```

### Anthropic Provider (app/providers/anthropic.py) - Pseudocode

```
CLASS AnthropicProvider(BaseLLMProvider):
    """Claude API provider implementation."""
    
    CONSTRUCTOR(config: ProviderConfig):
        self.client = AnthropicClient(api_key=config.api_key)
        self.model = config.model
        self.max_tokens = config.max_tokens
    
    PROPERTY name -> "anthropic"
    
    ASYNC METHOD chat(messages, system_prompt, tools, max_tokens, temperature) -> LLMResponse:
        # Build request
        request = {
            model: self.model,
            max_tokens: max_tokens OR self.max_tokens,
            messages: [msg.to_anthropic_format() FOR msg IN messages]
        }
        
        IF system_prompt:
            request.system = system_prompt
        
        IF tools:
            request.tools = self._convert_tools(tools)
        
        # Send request
        LOG.info("anthropic_request_started", model=self.model)
        
        TRY:
            response = AWAIT self.client.messages.create(**request)
            RETURN self._convert_response(response)
        CATCH AnthropicError as e:
            LOG.error("anthropic_request_failed", error=e)
            RAISE ProviderError(e)
    
    ASYNC METHOD stream(messages, system_prompt, tools, max_tokens, temperature) -> AsyncIterator[StreamChunk]:
        request = BUILD_REQUEST(...)  # Same as chat
        request.stream = true
        
        LOG.info("anthropic_stream_started", model=self.model)
        
        ASYNC WITH self.client.messages.stream(**request) AS stream:
            FOR EACH event IN stream:
                IF event.type == "content_block_delta":
                    YIELD StreamChunk(
                        content=event.delta.text,
                        done=false
                    )
                ELIF event.type == "message_stop":
                    YIELD StreamChunk(done=true, finish_reason="stop")
                ELIF event.type == "tool_use":
                    YIELD StreamChunk(
                        tool_calls=[self._parse_tool_call(event)],
                        done=false
                    )
    
    METHOD _convert_tools(tools) -> list[dict]:
        """Convert to Anthropic tool format"""
        RETURN [
            {
                name: tool.name,
                description: tool.description,
                input_schema: tool.parameters
            }
            FOR tool IN tools
        ]
    
    METHOD _convert_response(raw) -> LLMResponse:
        content = ""
        tool_calls = []
        
        FOR block IN raw.content:
            IF block.type == "text":
                content += block.text
            ELIF block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input
                ))
        
        RETURN LLMResponse(
            content=content,
            tool_calls=tool_calls IF tool_calls ELSE None,
            finish_reason=raw.stop_reason,
            provider="anthropic",
            model=self.model,
            usage=TokenUsage(...)
        )
    
    ASYNC METHOD health_check() -> bool:
        TRY:
            # Simple models list check
            AWAIT self.client.models.list()
            RETURN true
        CATCH:
            RETURN false
```

### OpenAI Provider (app/providers/openai.py) - Pseudocode

```
CLASS OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider implementation."""
    
    CONSTRUCTOR(config: ProviderConfig):
        self.client = OpenAIClient(api_key=config.api_key)
        self.model = config.model
        self.max_tokens = config.max_tokens
    
    PROPERTY name -> "openai"
    
    ASYNC METHOD chat(messages, system_prompt, tools, max_tokens, temperature) -> LLMResponse:
        # Prepare messages (OpenAI includes system in messages array)
        openai_messages = []
        IF system_prompt:
            openai_messages.append({role: "system", content: system_prompt})
        
        openai_messages.extend([msg.to_openai_format() FOR msg IN messages])
        
        request = {
            model: self.model,
            messages: openai_messages,
            max_tokens: max_tokens OR self.max_tokens,
            temperature: temperature
        }
        
        IF tools:
            request.tools = self._convert_tools(tools)
            request.tool_choice = "auto"
        
        LOG.info("openai_request_started", model=self.model)
        
        TRY:
            response = AWAIT self.client.chat.completions.create(**request)
            RETURN self._convert_response(response)
        CATCH OpenAIError as e:
            LOG.error("openai_request_failed", error=e)
            RAISE ProviderError(e)
    
    ASYNC METHOD stream(messages, system_prompt, tools, max_tokens, temperature) -> AsyncIterator[StreamChunk]:
        request = BUILD_REQUEST(...)  # Same as chat
        request.stream = true
        
        LOG.info("openai_stream_started", model=self.model)
        
        ASYNC FOR chunk IN AWAIT self.client.chat.completions.create(**request):
            delta = chunk.choices[0].delta
            
            IF delta.content:
                YIELD StreamChunk(content=delta.content, done=false)
            
            IF delta.tool_calls:
                # OpenAI streams tool calls incrementally
                YIELD StreamChunk(
                    tool_calls=self._accumulate_tool_calls(delta.tool_calls),
                    done=false
                )
            
            IF chunk.choices[0].finish_reason:
                YIELD StreamChunk(
                    done=true,
                    finish_reason=chunk.choices[0].finish_reason
                )
    
    METHOD _convert_tools(tools) -> list[dict]:
        """Convert to OpenAI function calling format"""
        RETURN [
            {
                type: "function",
                function: {
                    name: tool.name,
                    description: tool.description,
                    parameters: tool.parameters
                }
            }
            FOR tool IN tools
        ]
    
    METHOD _convert_response(raw) -> LLMResponse:
        choice = raw.choices[0]
        message = choice.message
        
        tool_calls = None
        IF message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments)
                )
                FOR tc IN message.tool_calls
            ]
        
        RETURN LLMResponse(
            content=message.content OR "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            provider="openai",
            model=self.model,
            usage=TokenUsage(
                prompt_tokens=raw.usage.prompt_tokens,
                completion_tokens=raw.usage.completion_tokens,
                total_tokens=raw.usage.total_tokens
            )
        )
```

### Gemini Provider (app/providers/gemini.py) - Pseudocode

```
CLASS GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider implementation."""
    
    CONSTRUCTOR(config: ProviderConfig):
        genai.configure(api_key=config.api_key)
        self.model = genai.GenerativeModel(config.model)
        self.max_tokens = config.max_tokens
    
    PROPERTY name -> "gemini"
    
    ASYNC METHOD chat(messages, system_prompt, tools, max_tokens, temperature) -> LLMResponse:
        # Gemini uses a different conversation structure
        chat_history = []
        
        FOR msg IN messages:
            gemini_role = "user" IF msg.role == USER ELSE "model"
            chat_history.append({
                role: gemini_role,
                parts: [msg.content]
            })
        
        generation_config = {
            max_output_tokens: max_tokens OR self.max_tokens,
            temperature: temperature
        }
        
        # Handle tools (Gemini calls them "function declarations")
        tool_config = None
        IF tools:
            tool_config = self._convert_tools(tools)
        
        LOG.info("gemini_request_started", model=self.model.model_name)
        
        TRY:
            # Start chat with history
            chat = self.model.start_chat(history=chat_history[:-1])
            
            # Send last message
            response = AWAIT chat.send_message_async(
                chat_history[-1].parts[0],
                generation_config=generation_config,
                tools=tool_config,
                system_instruction=system_prompt
            )
            
            RETURN self._convert_response(response)
        CATCH GoogleAPIError as e:
            LOG.error("gemini_request_failed", error=e)
            RAISE ProviderError(e)
    
    ASYNC METHOD stream(messages, system_prompt, tools, max_tokens, temperature) -> AsyncIterator[StreamChunk]:
        # Similar setup to chat
        chat = self.model.start_chat(history=PREPARED_HISTORY)
        
        LOG.info("gemini_stream_started", model=self.model.model_name)
        
        response = AWAIT chat.send_message_async(
            LAST_MESSAGE,
            stream=true,
            ...
        )
        
        ASYNC FOR chunk IN response:
            IF chunk.text:
                YIELD StreamChunk(content=chunk.text, done=false)
            
            IF chunk.candidates[0].content.parts HAS function_call:
                YIELD StreamChunk(
                    tool_calls=[self._parse_function_call(chunk)],
                    done=false
                )
        
        YIELD StreamChunk(done=true, finish_reason="stop")
    
    METHOD _convert_tools(tools) -> list:
        """Convert to Gemini function declaration format"""
        function_declarations = []
        FOR tool IN tools:
            function_declarations.append(
                genai.protos.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters=self._convert_schema(tool.parameters)
                )
            )
        RETURN [genai.protos.Tool(function_declarations=function_declarations)]
    
    METHOD _convert_response(raw) -> LLMResponse:
        content = ""
        tool_calls = []
        
        FOR part IN raw.candidates[0].content.parts:
            IF part.text:
                content += part.text
            IF part.function_call:
                tool_calls.append(ToolCall(
                    id=generate_uuid(),  # Gemini doesn't provide IDs
                    name=part.function_call.name,
                    arguments=dict(part.function_call.args)
                ))
        
        RETURN LLMResponse(
            content=content,
            tool_calls=tool_calls IF tool_calls ELSE None,
            finish_reason=raw.candidates[0].finish_reason.name,
            provider="gemini",
            model=self.model.model_name
        )
```

### Ollama Provider (app/providers/ollama.py) - Pseudocode

```
CLASS OllamaProvider(BaseLLMProvider):
    """Ollama local provider implementation."""
    
    CONSTRUCTOR(config: ProviderConfig):
        self.base_url = config.base_url OR "http://localhost:11434"
        self.model = config.model
        self.timeout = config.timeout
        self.http_client = AsyncHTTPClient(base_url=self.base_url, timeout=self.timeout)
    
    PROPERTY name -> "ollama"
    
    ASYNC METHOD chat(messages, system_prompt, tools, max_tokens, temperature) -> LLMResponse:
        # Build Ollama request
        ollama_messages = []
        IF system_prompt:
            ollama_messages.append({role: "system", content: system_prompt})
        
        ollama_messages.extend([msg.to_ollama_format() FOR msg IN messages])
        
        request = {
            model: self.model,
            messages: ollama_messages,
            stream: false,
            options: {
                num_predict: max_tokens,
                temperature: temperature
            }
        }
        
        IF tools:
            request.tools = self._convert_tools(tools)
        
        LOG.info("ollama_request_started", model=self.model, base_url=self.base_url)
        
        TRY:
            response = AWAIT self.http_client.post("/api/chat", json=request)
            response.raise_for_status()
            RETURN self._convert_response(response.json())
        CATCH HTTPError as e:
            LOG.error("ollama_request_failed", error=e)
            RAISE ProviderError(e)
    
    ASYNC METHOD stream(messages, system_prompt, tools, max_tokens, temperature) -> AsyncIterator[StreamChunk]:
        request = BUILD_REQUEST(...)  # Same as chat
        request.stream = true
        
        LOG.info("ollama_stream_started", model=self.model)
        
        ASYNC WITH self.http_client.stream("POST", "/api/chat", json=request) AS response:
            ASYNC FOR line IN response.aiter_lines():
                IF NOT line:
                    CONTINUE
                
                chunk_data = json.loads(line)
                
                IF chunk_data.message.content:
                    YIELD StreamChunk(
                        content=chunk_data.message.content,
                        done=false
                    )
                
                IF chunk_data.message.tool_calls:
                    YIELD StreamChunk(
                        tool_calls=[
                            ToolCall(
                                id=tc.id OR generate_uuid(),
                                name=tc.function.name,
                                arguments=tc.function.arguments
                            )
                            FOR tc IN chunk_data.message.tool_calls
                        ],
                        done=false
                    )
                
                IF chunk_data.done:
                    YIELD StreamChunk(done=true, finish_reason="stop")
    
    METHOD _convert_tools(tools) -> list[dict]:
        """Convert to Ollama tool format (similar to OpenAI)"""
        RETURN [
            {
                type: "function",
                function: {
                    name: tool.name,
                    description: tool.description,
                    parameters: tool.parameters
                }
            }
            FOR tool IN tools
        ]
    
    ASYNC METHOD health_check() -> bool:
        TRY:
            response = AWAIT self.http_client.get("/api/tags")
            RETURN response.status_code == 200
        CATCH:
            RETURN false
    
    ASYNC METHOD close():
        """Cleanup HTTP client"""
        AWAIT self.http_client.aclose()
```

### Provider Registry (app/providers/registry.py) - Pseudocode

```
CLASS ProviderRegistry:
    """
    Factory and registry for LLM providers.
    Handles provider instantiation, caching, and fallback.
    """
    
    CONSTRUCTOR(settings: Settings):
        self.settings = settings
        self._providers: dict[string, BaseLLMProvider] = {}
        self._provider_classes = {
            "anthropic": AnthropicProvider,
            "openai": OpenAIProvider,
            "gemini": GeminiProvider,
            "ollama": OllamaProvider
        }
    
    METHOD get_provider(name: string) -> BaseLLMProvider:
        """
        Get or create a provider instance by name.
        Caches instances for reuse.
        """
        IF name NOT IN self._provider_classes:
            RAISE ValueError(f"Unknown provider: {name}")
        
        IF name NOT IN self._providers:
            config = self.settings.get_provider_config(name)
            provider_class = self._provider_classes[name]
            self._providers[name] = provider_class(config)
            LOG.info("provider_initialized", provider=name)
        
        RETURN self._providers[name]
    
    METHOD get_provider_for_user(user_email: string, user_service: UserService) -> BaseLLMProvider:
        """
        Get the appropriate provider for a user based on their preferences.
        Falls back to default if user preference unavailable.
        """
        user_config = user_service.get_user_config(user_email)
        
        IF user_config AND user_config.provider:
            provider_name = user_config.provider
            LOG.debug("using_user_provider", user=user_email, provider=provider_name)
        ELSE:
            provider_name = self.settings.default_llm_provider
            LOG.debug("using_default_provider", user=user_email, provider=provider_name)
        
        RETURN self.get_provider(provider_name)
    
    ASYNC METHOD get_available_providers() -> list[tuple[string, bool]]:
        """
        Check which providers are available and healthy.
        Returns list of (provider_name, is_healthy) tuples.
        """
        results = []
        
        FOR name IN self.settings.get_available_providers():
            TRY:
                provider = self.get_provider(name)
                healthy = AWAIT provider.health_check()
                results.append((name, healthy))
            CATCH:
                results.append((name, false))
        
        RETURN results
    
    METHOD get_fallback_chain(primary: string) -> list[string]:
        """
        Get ordered list of providers to try if primary fails.
        """
        all_providers = ["anthropic", "openai", "gemini", "ollama"]
        chain = [primary]
        
        FOR provider IN all_providers:
            IF provider != primary AND provider IN self.settings.get_available_providers():
                chain.append(provider)
        
        RETURN chain
    
    ASYNC METHOD close_all():
        """Cleanup all provider instances"""
        FOR provider IN self._providers.values():
            IF hasattr(provider, "close"):
                AWAIT provider.close()


# Convenience function
FUNCTION get_registry() -> ProviderRegistry:
    """Get cached registry instance"""
    RETURN ProviderRegistry(get_settings())
```

### LLM Service (app/services/llm_service.py) - Pseudocode

```
CLASS LLMService:
    """
    High-level service for LLM interactions.
    Handles provider selection, tool execution loop, and response formatting.
    """
    
    CONSTRUCTOR(
        registry: ProviderRegistry,
        mcp_service: MCPService,
        user_service: UserService
    ):
        self.registry = registry
        self.mcp = mcp_service
        self.users = user_service
    
    ASYNC METHOD chat(
        user_email: string,
        messages: list[ChatMessage],
        room_id: string,
        stream: bool = true,
        provider_override: string = None,
        model_override: string = None
    ) -> AsyncIterator[string] OR LLMResponse:
        """
        Main entry point for chat completions.
        Handles provider selection and tool execution loop.
        """
        # Get user configuration
        user_config = self.users.get_user_config(user_email)
        system_prompt = self.users.get_system_prompt(user_email)
        
        # Determine provider
        provider_name = provider_override OR user_config.provider OR self.settings.default_llm_provider
        provider = self.registry.get_provider(provider_name)
        
        # Get MCP tools if available
        tools = None
        IF self.mcp.enabled AND provider.supports_tools:
            tools = AWAIT self.mcp.get_tools()
        
        LOG.info("llm_chat_started",
            user=user_email,
            provider=provider_name,
            message_count=len(messages),
            has_tools=tools IS NOT None,
            stream=stream
        )
        
        IF stream:
            RETURN self._stream_with_tools(
                provider, messages, system_prompt, tools, user_config
            )
        ELSE:
            RETURN AWAIT self._chat_with_tools(
                provider, messages, system_prompt, tools, user_config
            )
    
    ASYNC METHOD _chat_with_tools(
        provider: BaseLLMProvider,
        messages: list[ChatMessage],
        system_prompt: string,
        tools: list[Tool],
        user_config: UserConfig
    ) -> LLMResponse:
        """
        Non-streaming chat with automatic tool execution loop.
        """
        current_messages = messages.copy()
        max_iterations = 10  # Prevent infinite loops
        
        FOR iteration IN range(max_iterations):
            response = AWAIT provider.chat(
                messages=current_messages,
                system_prompt=system_prompt,
                tools=tools,
                max_tokens=user_config.preferences.max_response_length
            )
            
            # If no tool calls, we're done
            IF NOT response.tool_calls:
                LOG.info("llm_chat_completed", iterations=iteration + 1)
                RETURN response
            
            # Execute tool calls
            LOG.info("executing_tool_calls", count=len(response.tool_calls))
            
            # Add assistant message with tool calls
            current_messages.append(ChatMessage(
                role=ASSISTANT,
                content=response.content,
                tool_calls=response.tool_calls
            ))
            
            # Execute each tool and add results
            FOR tool_call IN response.tool_calls:
                result = AWAIT self.mcp.execute_tool(
                    name=tool_call.name,
                    arguments=tool_call.arguments
                )
                
                current_messages.append(ChatMessage(
                    role=TOOL,
                    content=result.content,
                    tool_call_id=tool_call.id
                ))
        
        LOG.warning("max_tool_iterations_reached")
        RETURN response
    
    ASYNC METHOD _stream_with_tools(
        provider: BaseLLMProvider,
        messages: list[ChatMessage],
        system_prompt: string,
        tools: list[Tool],
        user_config: UserConfig
    ) -> AsyncIterator[string]:
        """
        Streaming chat with automatic tool execution loop.
        Yields content chunks as they arrive.
        """
        current_messages = messages.copy()
        max_iterations = 10
        
        FOR iteration IN range(max_iterations):
            accumulated_content = ""
            accumulated_tool_calls = []
            
            ASYNC FOR chunk IN provider.stream(
                messages=current_messages,
                system_prompt=system_prompt,
                tools=tools,
                max_tokens=user_config.preferences.max_response_length
            ):
                # Yield content chunks to caller
                IF chunk.content:
                    accumulated_content += chunk.content
                    YIELD chunk.content
                
                # Accumulate tool calls
                IF chunk.tool_calls:
                    accumulated_tool_calls.extend(chunk.tool_calls)
                
                IF chunk.done:
                    BREAK
            
            # If no tool calls, we're done
            IF NOT accumulated_tool_calls:
                LOG.info("llm_stream_completed", iterations=iteration + 1)
                RETURN
            
            # Execute tools (not streamed - happens between stream segments)
            LOG.info("executing_tool_calls_mid_stream", count=len(accumulated_tool_calls))
            
            current_messages.append(ChatMessage(
                role=ASSISTANT,
                content=accumulated_content,
                tool_calls=accumulated_tool_calls
            ))
            
            FOR tool_call IN accumulated_tool_calls:
                result = AWAIT self.mcp.execute_tool(
                    name=tool_call.name,
                    arguments=tool_call.arguments
                )
                
                current_messages.append(ChatMessage(
                    role=TOOL,
                    content=result.content,
                    tool_call_id=tool_call.id
                ))
            
            # Continue streaming with tool results
            # (Loop continues with updated messages)
        
        LOG.warning("max_tool_iterations_reached")
    
    ASYNC METHOD health_check() -> dict[string, bool]:
        """Check health of all configured providers"""
        RETURN dict(AWAIT self.registry.get_available_providers())
```

---

## 8. MCP Integration

### MCP Service (app/services/mcp_service.py) - Pseudocode

The MCP (Model Context Protocol) server provides the assistant with access to specialized presales tools like knowledge base search, product documentation, pricing lookups, and competitive analysis.

```
CLASS MCPService:
    """
    Service for MCP (Model Context Protocol) tool execution.
    Communicates with custom FastMCP server for presales tools.
    
    Example tools that might be available:
    - search_knowledge_base: Search internal technical documentation
    - get_product_specs: Retrieve product specifications and datasheets
    - lookup_pricing: Get pricing information for products/solutions
    - compare_products: Compare features across product lines
    - search_case_studies: Find relevant customer case studies
    - get_compatibility_matrix: Check product compatibility
    """
    
    CONSTRUCTOR(settings: Settings):
        self.enabled = settings.mcp_enabled
        self.server_url = settings.mcp_server_url
        self.http_client = AsyncHTTPClient(
            base_url=self.server_url,
            timeout=60
        )
        self._tools_cache: list[Tool] = None
        self._cache_timestamp: datetime = None
        self._cache_ttl = timedelta(minutes=5)
    
    PROPERTY is_enabled -> bool:
        RETURN self.enabled
    
    ASYNC METHOD get_tools() -> list[Tool]:
        """
        Fetch available tools from MCP server.
        Results are cached for performance.
        """
        IF NOT self.enabled:
            RETURN []
        
        # Check cache
        IF self._tools_cache AND self._cache_timestamp:
            IF datetime.now() - self._cache_timestamp < self._cache_ttl:
                RETURN self._tools_cache
        
        TRY:
            response = AWAIT self.http_client.get("/tools")
            response.raise_for_status()
            
            mcp_tools = response.json()
            
            self._tools_cache = [
                Tool(
                    name=t["name"],
                    description=t.get("description", ""),
                    parameters=t.get("inputSchema", {})
                )
                FOR t IN mcp_tools.get("tools", [])
            ]
            self._cache_timestamp = datetime.now()
            
            LOG.info("mcp_tools_fetched", count=len(self._tools_cache))
            RETURN self._tools_cache
            
        CATCH HTTPError as e:
            LOG.error("mcp_tools_fetch_failed", error=e)
            RETURN []
    
    ASYNC METHOD execute_tool(name: string, arguments: dict) -> ToolResult:
        """
        Execute a tool on the MCP server.
        """
        IF NOT self.enabled:
            RETURN ToolResult(
                tool_call_id="",
                content="MCP tools are disabled",
                is_error=true
            )
        
        LOG.info("mcp_tool_executing", tool=name, arguments=arguments)
        
        TRY:
            response = AWAIT self.http_client.post(
                "/tools/call",
                json={name: name, arguments: arguments}
            )
            response.raise_for_status()
            
            result = response.json()
            
            LOG.info("mcp_tool_completed", tool=name, success=true)
            
            RETURN ToolResult(
                tool_call_id="",  # Will be set by caller
                content=json.dumps(result) IF isinstance(result, dict) ELSE str(result),
                is_error=false
            )
            
        CATCH HTTPError as e:
            LOG.error("mcp_tool_failed", tool=name, error=e)
            RETURN ToolResult(
                tool_call_id="",
                content=f"Tool execution failed: {e}",
                is_error=true
            )
    
    ASYNC METHOD health_check() -> bool:
        """Check if MCP server is available"""
        IF NOT self.enabled:
            RETURN true  # Disabled is "healthy"
        
        TRY:
            response = AWAIT self.http_client.get("/health")
            RETURN response.status_code == 200
        CATCH:
            RETURN false
    
    METHOD invalidate_cache():
        """Force refresh of tools on next request"""
        self._tools_cache = None
        self._cache_timestamp = None
    
    ASYNC METHOD close():
        """Cleanup HTTP client"""
        AWAIT self.http_client.aclose()


CLASS Tool:
    """Unified tool definition"""
    name: string
    description: string
    parameters: dict  # JSON Schema
    
    METHOD to_dict() -> dict:
        RETURN {
            name: self.name,
            description: self.description,
            parameters: self.parameters
        }
```

### Example MCP Tools for Presales

```json
{
  "tools": [
    {
      "name": "search_knowledge_base",
      "description": "Search the internal knowledge base for technical documentation, best practices, and solution guides",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": {"type": "string", "description": "Search query"},
          "category": {"type": "string", "enum": ["networking", "storage", "compute", "cloud", "security"]},
          "max_results": {"type": "integer", "default": 5}
        },
        "required": ["query"]
      }
    },
    {
      "name": "get_product_specs",
      "description": "Retrieve detailed specifications for a product",
      "inputSchema": {
        "type": "object",
        "properties": {
          "product_id": {"type": "string"},
          "product_name": {"type": "string"}
        }
      }
    },
    {
      "name": "compare_products",
      "description": "Compare features and specifications across multiple products",
      "inputSchema": {
        "type": "object",
        "properties": {
          "products": {"type": "array", "items": {"type": "string"}},
          "aspects": {"type": "array", "items": {"type": "string"}, "description": "Aspects to compare (performance, price, features, etc.)"}
        },
        "required": ["products"]
      }
    },
    {
      "name": "search_case_studies",
      "description": "Find relevant customer case studies and success stories",
      "inputSchema": {
        "type": "object",
        "properties": {
          "industry": {"type": "string"},
          "solution_type": {"type": "string"},
          "company_size": {"type": "string", "enum": ["smb", "midmarket", "enterprise"]}
        }
      }
    }
  ]
}
```

### Tool Format Conversion (app/utils/tool_converter.py) - Pseudocode

```
CLASS ToolConverter:
    """
    Converts tool definitions between different provider formats.
    Each provider has slightly different schemas for function calling.
    """
    
    STATIC METHOD to_anthropic(tool: Tool) -> dict:
        """Convert to Anthropic tool format"""
        RETURN {
            name: tool.name,
            description: tool.description,
            input_schema: tool.parameters
        }
    
    STATIC METHOD to_openai(tool: Tool) -> dict:
        """Convert to OpenAI function calling format"""
        RETURN {
            type: "function",
            function: {
                name: tool.name,
                description: tool.description,
                parameters: tool.parameters
            }
        }
    
    STATIC METHOD to_gemini(tool: Tool) -> FunctionDeclaration:
        """Convert to Gemini function declaration"""
        RETURN genai.protos.FunctionDeclaration(
            name=tool.name,
            description=tool.description,
            parameters=ToolConverter._schema_to_gemini(tool.parameters)
        )
    
    STATIC METHOD to_ollama(tool: Tool) -> dict:
        """Convert to Ollama format (same as OpenAI)"""
        RETURN ToolConverter.to_openai(tool)
    
    STATIC METHOD _schema_to_gemini(json_schema: dict) -> Schema:
        """Convert JSON Schema to Gemini Schema proto"""
        # Gemini uses a different schema format
        # Map JSON Schema types to Gemini types
        type_mapping = {
            "string": Type.STRING,
            "number": Type.NUMBER,
            "integer": Type.INTEGER,
            "boolean": Type.BOOLEAN,
            "array": Type.ARRAY,
            "object": Type.OBJECT
        }
        
        # Recursively convert schema
        ...
```

---

## 9. Conversation History Management

### History Service (app/services/history_service.py) - Pseudocode

```
CLASS ConversationContext:
    """Context for a single conversation (room/DM)"""
    room_id: string
    user_email: string
    messages: list[dict]
    created_at: datetime
    last_updated: datetime
    message_count: int
    provider_used: string (optional)  # Track which provider for this conversation


CLASS HistoryService:
    """
    Manages conversation history per room/direct message.
    Uses room_id as key since:
    - Direct messages have unique room_id per user pair
    - Group rooms share context among all participants
    """
    
    CONSTANTS:
        MAX_HISTORY_MESSAGES = 50
        MAX_HISTORY_CHARS = 32000  # ~8000 tokens
    
    CONSTRUCTOR():
        self._histories: dict[string, ConversationContext] = {}
    
    METHOD get_context(room_id: string, user_email: string) -> ConversationContext:
        """Get or create conversation context for a room"""
        IF room_id NOT IN self._histories:
            self._histories[room_id] = ConversationContext(
                room_id=room_id,
                user_email=user_email,
                messages=[],
                created_at=now(),
                last_updated=now(),
                message_count=0
            )
            LOG.debug("history_created", room_id=room_id)
        
        RETURN self._histories[room_id]
    
    METHOD get_messages(room_id: string) -> list[ChatMessage]:
        """Get conversation messages as ChatMessage objects"""
        context = self._histories.get(room_id)
        IF NOT context:
            RETURN []
        
        messages = []
        FOR m IN context.messages:
            messages.append(ChatMessage(
                role=MessageRole(m["role"]),
                content=m["content"],
                tool_calls=m.get("tool_calls"),
                tool_call_id=m.get("tool_call_id")
            ))
        
        LOG.debug("history_retrieved", room_id=room_id, count=len(messages))
        RETURN messages
    
    METHOD add_user_message(room_id: string, user_email: string, content: string):
        """Add a user message to history"""
        context = self.get_context(room_id, user_email)
        
        context.messages.append({
            role: "user",
            content: content,
            timestamp: now_iso(),
            email: user_email
        })
        context.message_count += 1
        context.last_updated = now_iso()
        
        # Truncate if needed
        self._truncate_history(context)
        
        LOG.debug("history_updated", room_id=room_id, role="user")
    
    METHOD add_assistant_message(room_id: string, content: string, tool_calls: list = None):
        """Add an assistant message to history"""
        context = self._histories.get(room_id)
        IF NOT context:
            RETURN
        
        message = {
            role: "assistant",
            content: content,
            timestamp: now_iso()
        }
        IF tool_calls:
            message.tool_calls = tool_calls
        
        context.messages.append(message)
        context.message_count += 1
        context.last_updated = now_iso()
        
        self._truncate_history(context)
        LOG.debug("history_updated", room_id=room_id, role="assistant")
    
    METHOD add_tool_result(room_id: string, tool_call_id: string, content: string):
        """Add a tool result message to history"""
        context = self._histories.get(room_id)
        IF NOT context:
            RETURN
        
        context.messages.append({
            role: "tool",
            content: content,
            tool_call_id: tool_call_id,
            timestamp: now_iso()
        })
    
    METHOD clear_history(room_id: string) -> bool:
        """Clear conversation history for a room"""
        IF room_id IN self._histories:
            DELETE self._histories[room_id]
            LOG.info("history_cleared", room_id=room_id)
            RETURN true
        RETURN false
    
    METHOD _truncate_history(context: ConversationContext):
        """Truncate history to fit within limits"""
        messages = context.messages
        
        # Calculate total characters
        total_chars = SUM(len(m.content) FOR m IN messages)
        
        # Remove oldest messages (preserving system message if present)
        WHILE len(messages) > 2 AND (
            len(messages) > MAX_HISTORY_MESSAGES OR 
            total_chars > MAX_HISTORY_CHARS
        ):
            # Find first non-system message to remove
            IF messages[0].role == "system":
                removed = messages.pop(1)
            ELSE:
                removed = messages.pop(0)
            
            total_chars -= len(removed.content)
        
        context.messages = messages
    
    METHOD get_stats() -> dict:
        """Get statistics about stored histories"""
        RETURN {
            active_conversations: len(self._histories),
            total_messages: SUM(ctx.message_count FOR ctx IN self._histories.values())
        }
```

---

## 10. User Management & Access Control

### User Service (app/services/user_service.py) - Pseudocode

```
CLASS UserPreferences:
    """User-specific preferences"""
    code_style: string = "black"
    max_response_length: int = 4000
    include_explanations: bool = true
    streaming: bool = true


CLASS UserConfig:
    """Configuration for an authorized user"""
    enabled: bool = true
    display_name: string (optional)
    provider: string (optional)      # anthropic, openai, gemini, ollama
    model: string (optional)         # Override default model for provider
    system_prompt: string (optional)
    preferences: UserPreferences
    is_admin: bool = false


CLASS UserService:
    """
    Manages user authorization and per-user configuration.
    Users must be whitelisted to interact with the bot.
    Each user can have custom providers, models, and system prompts.
    """
    
    CONSTRUCTOR(config_path: Path = "users.json"):
        self.config_path = config_path
        self._users: dict[string, UserConfig] = {}
        self._default_system_prompt: string = ""
        self._default_preferences: UserPreferences = UserPreferences()
        self._load_config()
    
    METHOD _load_config():
        """Load user configuration from JSON file"""
        IF NOT self.config_path.exists():
            LOG.warning("user_config_not_found", path=self.config_path)
            RETURN
        
        TRY:
            data = json.load(self.config_path)
            
            self._default_system_prompt = data.get("default_system_prompt", "")
            
            IF "default_preferences" IN data:
                self._default_preferences = UserPreferences(**data["default_preferences"])
            
            FOR email, config IN data.get("users", {}).items():
                self._users[email.lower()] = UserConfig(**config)
            
            LOG.info("user_config_loaded", user_count=len(self._users))
            
        CATCH Exception as e:
            LOG.error("user_config_load_error", error=e)
    
    METHOD reload_config():
        """Reload configuration from file (admin command)"""
        self._users.clear()
        self._load_config()
        LOG.info("user_config_reloaded")
    
    METHOD is_authorized(email: string) -> bool:
        """Check if user is whitelisted and enabled"""
        normalized = email.lower()
        user = self._users.get(normalized)
        
        IF user IS None:
            LOG.debug("user_not_in_whitelist", email=normalized)
            RETURN false
        
        IF NOT user.enabled:
            LOG.debug("user_disabled", email=normalized)
            RETURN false
        
        LOG.debug("user_authenticated", email=normalized)
        RETURN true
    
    METHOD get_user_config(email: string) -> UserConfig OR None:
        """Get full configuration for a user"""
        RETURN self._users.get(email.lower())
    
    METHOD get_provider(email: string) -> string OR None:
        """Get user's preferred provider (or None for default)"""
        user = self._users.get(email.lower())
        IF user AND user.provider:
            RETURN user.provider
        RETURN None
    
    METHOD get_model(email: string) -> string OR None:
        """Get user's preferred model (or None for provider default)"""
        user = self._users.get(email.lower())
        IF user AND user.model:
            RETURN user.model
        RETURN None
    
    METHOD get_system_prompt(email: string) -> string:
        """Get system prompt for user (custom or default)"""
        user = self._users.get(email.lower())
        
        IF user AND user.system_prompt:
            LOG.debug("using_custom_prompt", email=email)
            RETURN user.system_prompt
        
        RETURN self._default_system_prompt
    
    METHOD get_preferences(email: string) -> UserPreferences:
        """Get preferences for user (custom or default)"""
        user = self._users.get(email.lower())
        
        IF user:
            RETURN user.preferences
        
        RETURN self._default_preferences
    
    METHOD is_admin(email: string) -> bool:
        """Check if user has admin privileges"""
        user = self._users.get(email.lower())
        RETURN user IS NOT None AND user.is_admin
    
    METHOD list_users() -> list[string]:
        """List all whitelisted user emails"""
        RETURN list(self._users.keys())
    
    METHOD add_user(
        email: string,
        provider: string = None,
        system_prompt: string = None,
        save: bool = true
    ):
        """Add a user to the whitelist (admin only)"""
        normalized = email.lower()
        
        self._users[normalized] = UserConfig(
            enabled=true,
            provider=provider,
            system_prompt=system_prompt
        )
        
        LOG.info("user_added", email=normalized)
        
        IF save:
            self._save_config()
    
    METHOD remove_user(email: string, save: bool = true) -> bool:
        """Remove a user from the whitelist (admin only)"""
        normalized = email.lower()
        
        IF normalized IN self._users:
            DELETE self._users[normalized]
            LOG.info("user_removed", email=normalized)
            
            IF save:
                self._save_config()
            RETURN true
        
        RETURN false
    
    METHOD update_user_provider(email: string, provider: string, model: string = None):
        """Update user's preferred provider (can be done via /model command)"""
        normalized = email.lower()
        user = self._users.get(normalized)
        
        IF user:
            user.provider = provider
            IF model:
                user.model = model
            LOG.info("user_provider_updated", email=normalized, provider=provider)
    
    METHOD _save_config():
        """Persist current configuration to file"""
        data = {
            default_system_prompt: self._default_system_prompt,
            default_preferences: self._default_preferences.to_dict(),
            users: {
                email: config.to_dict()
                FOR email, config IN self._users.items()
            }
        }
        
        TRY:
            json.dump(data, self.config_path, indent=2)
            LOG.debug("user_config_saved")
        CATCH Exception as e:
            LOG.error("user_config_save_error", error=e)
```
```

---

## 11. Message Flow & Response Handling

### Message Handler (app/handlers/message_handler.py) - Pseudocode

```
CLASS MessageHandler:
    """Handles incoming messages and orchestrates responses"""
    
    CONSTRUCTOR(
        webex: WebexService,
        llm: LLMService,
        history: HistoryService,
        users: UserService
    ):
        self.webex = webex
        self.llm = llm
        self.history = history
        self.users = users
        self.commands = CommandHandler(webex, llm, history, users)
    
    CONSTANTS:
        STREAM_UPDATE_INTERVAL = 1.5  # seconds
        MIN_CONTENT_FOR_UPDATE = 50   # characters
    
    ASYNC METHOD handle(message: WebexMessage):
        """Process an incoming message"""
        content = message.content.strip()
        
        LOG.info("message_received",
            message_id=message.id,
            room_id=message.room_id,
            user_email=message.person_email,
            content_length=len(content)
        )
        
        # Check for slash commands
        IF content.startswith("/"):
            AWAIT self.commands.handle(message)
            RETURN
        
        # Process as natural language query
        AWAIT self._process_query(message)
    
    ASYNC METHOD _process_query(message: WebexMessage):
        """Process a natural language query through LLM"""
        room_id = message.room_id
        user_email = message.person_email
        content = message.content.strip()
        
        # Get user configuration
        user_config = self.users.get_user_config(user_email)
        preferences = user_config.preferences IF user_config ELSE default_preferences
        
        # Add to history
        self.history.add_user_message(room_id, user_email, content)
        
        # Get conversation history
        history_messages = self.history.get_messages(room_id)
        
        # Send typing indicator
        placeholder_id = AWAIT self.webex.send_message(
            room_id=room_id,
            text="🤔 Thinking..."
        )
        
        TRY:
            full_response = ""
            last_update_time = now()
            
            # Determine streaming behavior
            should_stream = preferences.streaming
            
            IF should_stream:
                ASYNC FOR chunk IN self.llm.chat(
                    user_email=user_email,
                    messages=history_messages,
                    room_id=room_id,
                    stream=true
                ):
                    full_response += chunk
                    
                    # Update message periodically for non-markdown
                    time_since_update = now() - last_update_time
                    
                    IF (time_since_update >= STREAM_UPDATE_INTERVAL AND
                        len(full_response) >= MIN_CONTENT_FOR_UPDATE AND
                        NOT contains_markdown(full_response)):
                        
                        AWAIT self.webex.update_message(
                            message_id=placeholder_id,
                            room_id=room_id,
                            text=full_response + " ▌"
                        )
                        last_update_time = now()
            ELSE:
                response = AWAIT self.llm.chat(
                    user_email=user_email,
                    messages=history_messages,
                    room_id=room_id,
                    stream=false
                )
                full_response = response.content
            
            # Send final response
            IF full_response:
                self.history.add_assistant_message(room_id, full_response)
                
                IF contains_markdown(full_response):
                    AWAIT self.webex.update_message(
                        message_id=placeholder_id,
                        room_id=room_id,
                        markdown=full_response
                    )
                ELSE:
                    AWAIT self.webex.update_message(
                        message_id=placeholder_id,
                        room_id=room_id,
                        text=full_response
                    )
                
                LOG.info("response_sent",
                    room_id=room_id,
                    response_length=len(full_response),
                    provider=self.llm.get_provider_name(user_email)
                )
            ELSE:
                AWAIT self.webex.update_message(
                    message_id=placeholder_id,
                    room_id=room_id,
                    text="I wasn't able to generate a response. Please try again."
                )
                
        CATCH ProviderError as e:
            LOG.error("response_generation_failed", room_id=room_id, error=e)
            
            AWAIT self.webex.update_message(
                message_id=placeholder_id,
                room_id=room_id,
                text=f"❌ Sorry, I encountered an error: {e.message}"
            )
```

### Command Handler (app/handlers/command_handler.py) - Pseudocode

```
CLASS CommandHandler:
    """Handles slash commands for utility functions"""
    
    CONSTRUCTOR(
        webex: WebexService,
        llm: LLMService,
        history: HistoryService,
        users: UserService
    ):
        self.webex = webex
        self.llm = llm
        self.history = history
        self.users = users
        
        # Command registry
        self._commands = {
            "/help": self._cmd_help,
            "/clear": self._cmd_clear,
            "/status": self._cmd_status,
            "/history": self._cmd_history,
            "/model": self._cmd_model,
            "/providers": self._cmd_providers,
            "/reload": self._cmd_reload,  # Admin only
        }
    
    ASYNC METHOD handle(message: WebexMessage):
        """Process a slash command"""
        parts = message.content.strip().split()
        command = parts[0].lower()
        args = parts[1:]
        
        LOG.info("command_detected", command=command, args=args)
        
        handler = self._commands.get(command)
        
        IF handler:
            AWAIT handler(message, args)
            LOG.info("command_executed", command=command)
        ELSE:
            AWAIT self.webex.send_message(
                room_id=message.room_id,
                text=f"Unknown command: `{command}`. Use `/help` for available commands."
            )
    
    ASYNC METHOD _cmd_help(message, args):
        """Display help information"""
        help_text = """
**Available Commands**

• `/help` - Show this help message
• `/clear` - Clear conversation history for this room
• `/status` - Show bot status and your configuration
• `/history` - Show conversation statistics
• `/model [provider] [model]` - Switch LLM provider/model
• `/providers` - List available providers and their status

**Usage**
Just ask your question naturally! I can help with:
• Networking (SD-WAN, routing, switching, security)
• Storage (SAN, NAS, backup, data protection)
• Compute (servers, virtualization, HCI)
• Cloud infrastructure and hybrid solutions
• Product comparisons and specifications
• Customer case studies and references

**Tips**
• I remember conversation context in this room
• I have access to knowledge base and product tools via MCP
• Use `/model` to switch between Claude, GPT-4, Gemini, or local Ollama
"""
        
        IF self.users.is_admin(message.person_email):
            help_text += """
**Admin Commands**
• `/reload` - Reload user configuration
"""
        
        AWAIT self.webex.send_message(room_id=message.room_id, markdown=help_text)
    
    ASYNC METHOD _cmd_model(message, args):
        """Switch LLM provider or model"""
        user_email = message.person_email
        
        IF len(args) == 0:
            # Show current model
            user_config = self.users.get_user_config(user_email)
            current_provider = user_config.provider IF user_config ELSE "default"
            current_model = user_config.model IF user_config ELSE "default"
            
            AWAIT self.webex.send_message(
                room_id=message.room_id,
                markdown=f"""**Current Model Configuration**
• Provider: `{current_provider}`
• Model: `{current_model}`

Use `/model <provider> [model]` to change.
Available providers: `anthropic`, `openai`, `gemini`, `ollama`
"""
            )
            RETURN
        
        provider = args[0].lower()
        model = args[1] IF len(args) > 1 ELSE None
        
        # Validate provider
        available = AWAIT self.llm.health_check()
        IF provider NOT IN available OR NOT available[provider]:
            AWAIT self.webex.send_message(
                room_id=message.room_id,
                text=f"❌ Provider `{provider}` is not available. Use `/providers` to see available options."
            )
            RETURN
        
        # Update user preference
        self.users.update_user_provider(user_email, provider, model)
        
        # Clear history for fresh context with new model
        self.history.clear_history(message.room_id)
        
        response = f"✅ Switched to **{provider}**"
        IF model:
            response += f" with model `{model}`"
        response += "\n\nConversation history cleared for fresh context."
        
        AWAIT self.webex.send_message(room_id=message.room_id, markdown=response)
    
    ASYNC METHOD _cmd_providers(message, args):
        """List available providers and their health status"""
        health = AWAIT self.llm.health_check()
        
        status_lines = ["**Available LLM Providers**\n"]
        
        FOR provider, is_healthy IN health.items():
            status_icon = "✅" IF is_healthy ELSE "❌"
            status_lines.append(f"• {status_icon} **{provider}**")
        
        status_lines.append("\nUse `/model <provider>` to switch providers.")
        
        AWAIT self.webex.send_message(
            room_id=message.room_id,
            markdown="\n".join(status_lines)
        )
    
    ASYNC METHOD _cmd_status(message, args):
        """Show bot status and user configuration"""
        user_email = message.person_email
        user_config = self.users.get_user_config(user_email)
        
        # Get provider health
        health = AWAIT self.llm.health_check()
        healthy_count = SUM(1 FOR h IN health.values() IF h)
        
        provider = user_config.provider IF user_config ELSE settings.default_llm_provider
        model = user_config.model IF user_config ELSE "default"
        
        status_text = f"""**Bot Status**

• **Healthy Providers**: {healthy_count}/{len(health)}
• **MCP Tools**: {"Enabled" IF mcp.enabled ELSE "Disabled"}
• **Environment**: {settings.app_env}

**Your Configuration**
• **Email**: {user_email}
• **Provider**: {provider}
• **Model**: {model}
• **Admin**: {"Yes" IF self.users.is_admin(user_email) ELSE "No"}
"""
        
        AWAIT self.webex.send_message(room_id=message.room_id, markdown=status_text)
    
    ASYNC METHOD _cmd_clear(message, args):
        """Clear conversation history"""
        cleared = self.history.clear_history(message.room_id)
        
        IF cleared:
            AWAIT self.webex.send_message(
                room_id=message.room_id,
                text="✅ Conversation history cleared. Starting fresh!"
            )
        ELSE:
            AWAIT self.webex.send_message(
                room_id=message.room_id,
                text="ℹ️ No history to clear."
            )
    
    ASYNC METHOD _cmd_history(message, args):
        """Show conversation statistics"""
        context = self.history.get_context(message.room_id, message.person_email)
        stats = self.history.get_stats()
        
        status_text = f"""**Conversation Stats**

**This Room**
• Messages: {context.message_count}
• Started: {context.created_at}
• Last Activity: {context.last_updated}

**Global**
• Active Conversations: {stats['active_conversations']}
• Total Messages: {stats['total_messages']}
"""
        
        AWAIT self.webex.send_message(room_id=message.room_id, markdown=status_text)
    
    ASYNC METHOD _cmd_reload(message, args):
        """Reload configuration (admin only)"""
        IF NOT self.users.is_admin(message.person_email):
            AWAIT self.webex.send_message(
                room_id=message.room_id,
                text="⚠️ This command requires admin privileges."
            )
            RETURN
        
        self.users.reload_config()
        
        AWAIT self.webex.send_message(
            room_id=message.room_id,
            text="✅ Configuration reloaded."
        )
```

---

## 12. Error Handling

### Custom Exceptions (app/core/exceptions.py) - Pseudocode

```
CLASS BotError(Exception):
    """Base exception for bot errors"""
    message: string
    details: dict
    recoverable: bool = true


CLASS WebexAPIError(BotError):
    """Error communicating with Webex API"""
    PASS


CLASS ProviderError(BotError):
    """Error from any LLM provider"""
    provider: string
    original_error: Exception


CLASS MCPError(BotError):
    """Error communicating with MCP server"""
    tool_name: string (optional)


CLASS AuthorizationError(BotError):
    """User authorization failure"""
    user_email: string


CLASS ConfigurationError(BotError):
    """Configuration error"""
    config_key: string
```

### Error Handling Strategy - Pseudocode

```
# In app/main.py

ASYNC FUNCTION bot_error_handler(request, exc: BotError):
    """Handle application-specific errors"""
    LOG.error("bot_error",
        error_type=type(exc).__name__,
        message=exc.message,
        details=exc.details,
        recoverable=exc.recoverable
    )
    
    RETURN JSONResponse(
        status_code=500,
        content={
            error: type(exc).__name__,
            message: exc.message,
            recoverable: exc.recoverable
        }
    )


ASYNC FUNCTION provider_error_handler(request, exc: ProviderError):
    """Handle LLM provider errors with potential fallback"""
    LOG.error("provider_error",
        provider=exc.provider,
        error=exc.message
    )
    
    # Could trigger fallback to another provider here
    # For now, just return error
    RETURN JSONResponse(
        status_code=503,
        content={
            error: "ProviderError",
            message: f"LLM provider {exc.provider} failed: {exc.message}",
            provider: exc.provider
        }
    )


# Provider fallback logic (in LLMService)
ASYNC METHOD chat_with_fallback(
    user_email: string,
    messages: list,
    primary_provider: string
) -> AsyncIterator[string]:
    """
    Attempt chat with fallback providers if primary fails.
    """
    fallback_chain = self.registry.get_fallback_chain(primary_provider)
    last_error = None
    
    FOR provider_name IN fallback_chain:
        TRY:
            provider = self.registry.get_provider(provider_name)
            
            ASYNC FOR chunk IN provider.stream(messages, ...):
                YIELD chunk
            
            RETURN  # Success, exit
            
        CATCH ProviderError as e:
            LOG.warning("provider_failed_trying_fallback",
                failed_provider=provider_name,
                error=e.message
            )
            last_error = e
            CONTINUE
    
    # All providers failed
    RAISE ProviderError(
        message=f"All providers failed. Last error: {last_error.message}",
        provider="all"
    )
```

### Graceful Degradation Patterns

```
# Pattern 1: MCP Tool Failure
IF tool execution fails:
    - Return error message as tool result
    - Let LLM handle gracefully (it will explain the error)
    - Don't crash the entire request

# Pattern 2: Provider Timeout
IF provider times out:
    - Log timeout with provider details
    - If streaming, send partial response with notice
    - Offer to retry or switch providers

# Pattern 3: Rate Limiting
IF rate limited by provider:
    - Check other providers' availability
    - Queue request with delay
    - Notify user of delay

# Pattern 4: Invalid Tool Call
IF LLM generates invalid tool call:
    - Return validation error as tool result
    - Let LLM self-correct
    - Limit retry attempts (max 3)
```

---

## 13. Local Development Setup

### Prerequisites

1. **Python 3.11+**
2. **At least one LLM provider configured**:
   - Anthropic API key, OR
   - OpenAI API key, OR
   - Google Gemini API key, OR
   - Ollama installed and running locally
3. **ngrok** account and CLI installed
4. **Webex Bot** created at developer.webex.com

### Step-by-Step Setup

```bash
# 1. Clone and setup project
git clone <repository>
cd webex-presales-assistant

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Copy environment template
cp .env.example .env

# 5. Edit .env with your values
# - Add WEBEX_BOT_TOKEN from developer.webex.com
# - Add at least one LLM provider API key
# - Set DEFAULT_LLM_PROVIDER to your preferred provider

# 6. Create users.json
cat > users.json << 'EOF'
{
  "users": {
    "your-email@example.com": {
      "enabled": true,
      "provider": "anthropic",
      "system_prompt": "You are a helpful presales assistant for enterprise infrastructure solutions."
    }
  },
  "default_system_prompt": "You are a helpful AI assistant for presales engineers."
}
EOF

# 7. (Optional) Start Ollama if using local models
ollama serve
ollama pull llama3.1:8b

# 8. Start the FastAPI app
uvicorn app.main:app --reload --port 8000

# 9. In another terminal, start ngrok
ngrok http 8000

# 10. Register webhook (one-time)
python scripts/setup_webhook.py --url https://YOUR-NGROK-URL.ngrok.io/webhook
```

### Provider Setup Scripts (scripts/test_providers.py) - Pseudocode

```
#!/usr/bin/env python3
"""
Test connectivity to all configured LLM providers.
Run this to verify your setup before starting the bot.
"""

ASYNC FUNCTION main():
    settings = get_settings()
    registry = ProviderRegistry(settings)
    
    print("Testing LLM Providers...")
    print("=" * 50)
    
    available = settings.get_available_providers()
    
    FOR provider_name IN available:
        TRY:
            provider = registry.get_provider(provider_name)
            healthy = AWAIT provider.health_check()
            
            IF healthy:
                print(f"✅ {provider_name}: Connected")
                
                # Quick test message
                response = AWAIT provider.chat(
                    messages=[ChatMessage(role=USER, content="Say 'hello' in one word")],
                    max_tokens=10
                )
                print(f"   Test response: {response.content[:50]}...")
            ELSE:
                print(f"❌ {provider_name}: Health check failed")
                
        CATCH Exception as e:
            print(f"❌ {provider_name}: {e}")
    
    print("=" * 50)
    
    # Test MCP if enabled
    IF settings.mcp_enabled:
        TRY:
            mcp = MCPService(settings)
            healthy = AWAIT mcp.health_check()
            
            IF healthy:
                tools = AWAIT mcp.get_tools()
                print(f"✅ MCP Server: Connected ({len(tools)} tools available)")
            ELSE:
                print(f"❌ MCP Server: Health check failed")
        CATCH Exception as e:
            print(f"❌ MCP Server: {e}")


IF __name__ == "__main__":
    asyncio.run(main())
```

### Webhook Setup Script (scripts/setup_webhook.py) - Pseudocode

```
#!/usr/bin/env python3
"""
One-time webhook registration script.
Run this after getting your ngrok URL.
"""

FUNCTION main():
    PARSE arguments:
        --url: Public webhook URL (required)
        --name: Webhook name (default: "Presales Assistant Bot")
    
    settings = get_settings()
    api = WebexTeamsAPI(access_token=settings.webex_bot_token)
    
    # Delete existing webhooks with same name
    existing = api.webhooks.list()
    FOR webhook IN existing:
        IF webhook.name == args.name:
            print(f"Deleting existing webhook: {webhook.id}")
            api.webhooks.delete(webhook.id)
    
    # Create new webhook
    webhook = api.webhooks.create(
        name=args.name,
        targetUrl=f"{args.url}/webhook",
        resource="messages",
        event="created",
        secret=settings.webex_webhook_secret
    )
    
    print("✅ Webhook created!")
    print(f"   ID: {webhook.id}")
    print(f"   URL: {webhook.targetUrl}")


IF __name__ == "__main__":
    main()
```

---

## 14. API Reference

### FastAPI Application (app/main.py) - Pseudocode

```
"""FastAPI application entry point"""

ASYNC FUNCTION lifespan(app: FastAPI):
    """Application lifespan handler - startup and shutdown"""
    
    # === STARTUP ===
    LOG.info("app_starting",
        environment=settings.app_env,
        default_provider=settings.default_llm_provider,
        mcp_enabled=settings.mcp_enabled
    )
    
    # Initialize services
    app.state.mcp = MCPService(settings)
    app.state.registry = ProviderRegistry(settings)
    app.state.webex = WebexService()
    app.state.history = HistoryService()
    app.state.users = UserService()
    
    app.state.llm = LLMService(
        registry=app.state.registry,
        mcp_service=app.state.mcp,
        user_service=app.state.users
    )
    
    app.state.message_handler = MessageHandler(
        webex=app.state.webex,
        llm=app.state.llm,
        history=app.state.history,
        users=app.state.users
    )
    
    app.state.webhook_handler = WebhookHandler(
        webex_service=app.state.webex,
        user_service=app.state.users,
        message_handler=app.state.message_handler
    )
    
    # Health checks
    provider_health = AWAIT app.state.llm.health_check()
    LOG.info("provider_health_check", results=provider_health)
    
    IF app.state.mcp.is_enabled:
        mcp_ok = AWAIT app.state.mcp.health_check()
        LOG.info("mcp_health_check", healthy=mcp_ok)
    
    LOG.info("app_started")
    
    YIELD  # App runs here
    
    # === SHUTDOWN ===
    AWAIT app.state.registry.close_all()
    AWAIT app.state.mcp.close()
    
    LOG.info("app_shutdown")


app = FastAPI(
    title="Webex Presales Assistant",
    description="Multi-provider AI assistant for presales engineers",
    version="2.0.0",
    lifespan=lifespan
)


# === ENDPOINTS ===

@app.post("/webhook")
ASYNC FUNCTION webhook_endpoint(request: Request):
    """Webex webhook endpoint - receives all incoming messages"""
    RETURN AWAIT request.app.state.webhook_handler.handle(request)


@app.get("/health")
ASYNC FUNCTION health_check(request: Request):
    """Health check endpoint for monitoring"""
    provider_health = AWAIT request.app.state.llm.health_check()
    mcp_health = AWAIT request.app.state.mcp.health_check()
    
    all_healthy = any(provider_health.values()) AND (NOT mcp_enabled OR mcp_health)
    
    RETURN {
        status: "healthy" IF all_healthy ELSE "degraded",
        providers: provider_health,
        mcp: mcp_health IF mcp_enabled ELSE "disabled"
    }


@app.get("/stats")
ASYNC FUNCTION stats(request: Request):
    """Get bot statistics"""
    RETURN {
        history: request.app.state.history.get_stats(),
        users: {
            whitelisted: len(request.app.state.users.list_users())
        },
        providers: {
            available: settings.get_available_providers(),
            default: settings.default_llm_provider
        }
    }


@app.get("/providers")
ASYNC FUNCTION list_providers(request: Request):
    """List available providers and their status"""
    health = AWAIT request.app.state.llm.health_check()
    
    RETURN {
        providers: [
            {
                name: name,
                healthy: is_healthy,
                default_model: settings.get_provider_config(name).model
            }
            FOR name, is_healthy IN health.items()
        ]
    }
```

### Endpoints Summary

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook` | POST | Webex webhook receiver |
| `/health` | GET | Health check (all providers + MCP) |
| `/stats` | GET | Bot statistics |
| `/providers` | GET | List available providers and status |

---

## 15. Testing Strategy

### Test Structure

```
tests/
├── conftest.py                # Shared fixtures
├── test_providers/            # Provider-specific tests
│   ├── test_base.py           # Base provider interface tests
│   ├── test_anthropic.py      # Anthropic provider tests
│   ├── test_openai.py         # OpenAI provider tests
│   ├── test_gemini.py         # Gemini provider tests
│   └── test_ollama.py         # Ollama provider tests
├── test_llm_service.py        # LLM orchestration tests
├── test_webhook_handler.py    # Webhook processing tests
├── test_message_handler.py    # Message routing tests
├── test_user_service.py       # User management tests
├── test_history_service.py    # History management tests
├── test_mcp_service.py        # MCP integration tests
└── integration/
    └── test_end_to_end.py     # Full flow tests
```

### Example Test (tests/test_user_service.py) - Pseudocode

```
"""Tests for UserService with multi-provider support"""

FIXTURE user_config_file():
    """Create a temporary user config file"""
    config = {
        users: {
            "test@example.com": {
                enabled: true,
                provider: "anthropic",
                model: "claude-sonnet-4-20250514",
                system_prompt: "You are a presales assistant for networking solutions."
            },
            "ollama@example.com": {
                enabled: true,
                provider: "ollama",
                model: "llama3.1:8b"
            },
            "disabled@example.com": {
                enabled: false
            }
        },
        default_system_prompt: "You are a helpful presales assistant."
    }
    
    RETURN create_temp_json_file(config)


FIXTURE user_service(user_config_file):
    """Create UserService with test config"""
    RETURN UserService(config_path=user_config_file)


CLASS TestUserService:
    """Tests for UserService"""
    
    TEST test_authorized_user(user_service):
        """Authorized user should pass"""
        ASSERT user_service.is_authorized("test@example.com") IS true
    
    TEST test_unauthorized_user(user_service):
        """Unknown user should fail"""
        ASSERT user_service.is_authorized("unknown@example.com") IS false
    
    TEST test_disabled_user(user_service):
        """Disabled user should fail"""
        ASSERT user_service.is_authorized("disabled@example.com") IS false
    
    TEST test_case_insensitive_email(user_service):
        """Email matching should be case-insensitive"""
        ASSERT user_service.is_authorized("TEST@EXAMPLE.COM") IS true
    
    TEST test_custom_system_prompt(user_service):
        """User should get custom system prompt"""
        prompt = user_service.get_system_prompt("test@example.com")
        ASSERT prompt == "Test prompt"
    
    TEST test_user_provider_preference(user_service):
        """User should get their configured provider"""
        provider = user_service.get_provider("test@example.com")
        ASSERT provider == "anthropic"
        
        provider = user_service.get_provider("ollama@example.com")
        ASSERT provider == "ollama"
    
    TEST test_user_model_preference(user_service):
        """User should get their configured model"""
        model = user_service.get_model("test@example.com")
        ASSERT model == "claude-sonnet-4-20250514"
```

### Example Provider Test (tests/test_providers/test_base.py) - Pseudocode

```
"""Tests for provider abstraction layer"""

CLASS TestProviderRegistry:
    """Tests for ProviderRegistry"""
    
    TEST test_get_available_providers(mock_settings):
        """Should return list of configured providers"""
        mock_settings.anthropic_api_key = "sk-test"
        mock_settings.openai_api_key = None
        mock_settings.gemini_api_key = "gem-test"
        
        registry = ProviderRegistry(mock_settings)
        available = registry.settings.get_available_providers()
        
        ASSERT "anthropic" IN available
        ASSERT "openai" NOT IN available
        ASSERT "gemini" IN available
        ASSERT "ollama" IN available  # Always available
    
    TEST test_provider_caching(mock_settings):
        """Provider instances should be cached"""
        registry = ProviderRegistry(mock_settings)
        
        provider1 = registry.get_provider("anthropic")
        provider2 = registry.get_provider("anthropic")
        
        ASSERT provider1 IS provider2  # Same instance
    
    TEST test_fallback_chain(mock_settings):
        """Fallback chain should exclude primary provider"""
        registry = ProviderRegistry(mock_settings)
        
        chain = registry.get_fallback_chain("anthropic")
        
        ASSERT chain[0] == "anthropic"  # Primary first
        ASSERT "anthropic" NOT IN chain[1:]  # Not repeated


CLASS TestAnthropicProvider:
    """Tests for Anthropic provider"""
    
    ASYNC TEST test_chat_basic(mock_anthropic_client):
        """Basic chat should work"""
        provider = AnthropicProvider(config)
        
        response = AWAIT provider.chat(
            messages=[ChatMessage(role=USER, content="Hello")],
            system_prompt="Be helpful"
        )
        
        ASSERT response.content IS NOT empty
        ASSERT response.provider == "anthropic"
    
    ASYNC TEST test_tool_conversion(mock_anthropic_client):
        """Tools should convert to Anthropic format"""
        provider = AnthropicProvider(config)
        
        tool = Tool(
            name="test_tool",
            description="A test tool",
            parameters={type: "object", properties: {}}
        )
        
        converted = provider._convert_tools([tool])
        
        ASSERT converted[0].name == "test_tool"
        ASSERT "input_schema" IN converted[0]  # Anthropic uses input_schema
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run provider tests only
pytest tests/test_providers/ -v

# Run specific provider
pytest tests/test_providers/test_anthropic.py -v

# Run with logging output
pytest -v --log-cli-level=DEBUG

# Run integration tests (requires running services)
pytest tests/integration/ -v --run-integration
```

---

## 16. Future Considerations

### Potential Enhancements

1. **Persistent Storage**
   - Move conversation history to Redis or SQLite
   - Enable history survival across restarts
   - Persist user provider preferences
   - Cache frequently accessed knowledge base content

2. **Rate Limiting**
   - Add per-user rate limiting
   - Per-provider rate limit tracking
   - Queue management for high load

3. **Observability**
   - OpenTelemetry integration for distributed tracing
   - Prometheus metrics endpoint (per-provider metrics)
   - Grafana dashboards for provider comparison
   - Query analytics for knowledge base improvement

4. **Security**
   - Webhook signature validation (currently optional)
   - Input sanitization for tool inputs
   - API key rotation support
   - Audit logging for compliance

5. **Provider Enhancements**
   - Automatic cost tracking per provider
   - Smart provider selection based on query type
   - A/B testing between providers
   - Provider-specific feature flags (extended thinking, vision, etc.)

6. **Presales-Specific Features**
   - Integration with CRM systems (Salesforce, etc.)
   - Deal/opportunity context awareness
   - Automated proposal generation assistance
   - Customer-specific knowledge base access
   - Competitive intelligence tools

7. **Websocket Migration**
   - Eliminate ngrok dependency
   - Better for production deployments
   - Real-time streaming improvements

8. **Group Room Intelligence**
   - User mention detection (@bot)
   - Thread-aware responses
   - Multi-user context in group rooms
   - Role-based access to sensitive information

9. **Advanced MCP Features**
   - Tool result caching
   - Parallel tool execution
   - Provider-specific tool formatting optimization
   - Knowledge base indexing and search improvements

---

## Appendix A: Dependencies (pyproject.toml)

```toml
[project]
name = "webex-presales-assistant"
version = "2.0.0"
description = "Multi-provider AI assistant for presales engineers on Webex Teams"
requires-python = ">=3.11"

dependencies = [
    # Web Framework
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    
    # Webex
    "webexteamssdk>=1.6.1",
    
    # HTTP Client
    "httpx>=0.26.0",
    
    # LLM Providers
    "anthropic>=0.18.0",
    "openai>=1.12.0",
    "google-generativeai>=0.4.0",
    
    # Configuration
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "python-dotenv>=1.0.0",
    
    # Logging
    "structlog>=24.1.0",
    
    # Utilities
    "tenacity>=8.2.0",  # Retry logic
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "respx>=0.20.0",  # HTTP mocking
    "ruff>=0.2.0",    # Linting
    "mypy>=1.8.0",    # Type checking
]
```

---

## Appendix B: Quick Reference - Provider Comparison

| Feature | Anthropic | OpenAI | Gemini | Ollama |
|---------|-----------|--------|--------|--------|
| **API Style** | Messages API | Chat Completions | GenerativeAI | OpenAI-compatible |
| **Tool Format** | `input_schema` | `function.parameters` | `FunctionDeclaration` | OpenAI-style |
| **System Prompt** | Separate field | In messages array | `system_instruction` | In messages array |
| **Streaming** | SSE events | SSE chunks | Async iterator | NDJSON lines |
| **Max Tokens Field** | `max_tokens` | `max_tokens` | `max_output_tokens` | `num_predict` |
| **Tool Call ID** | Required | Required | Generated | Optional |

---

## Appendix C: Environment Variables Quick Reference

```bash
# Required
WEBEX_BOT_TOKEN=           # From developer.webex.com

# At least one provider required
ANTHROPIC_API_KEY=         # Claude API
OPENAI_API_KEY=            # GPT-4 API  
GEMINI_API_KEY=            # Gemini API
# Ollama requires no key (local)

# Defaults
DEFAULT_LLM_PROVIDER=anthropic
DEFAULT_LLM_MODEL=claude-sonnet-4-20250514

# Optional
WEBEX_WEBHOOK_SECRET=      # Webhook validation
MCP_SERVER_URL=http://localhost:8080
MCP_ENABLED=true
LOG_LEVEL=INFO
```

---

*Document Version: 2.0*  
*Last Updated: 2024*  
*Multi-Provider Presales Assistant with Anthropic, OpenAI, Gemini, and Ollama support*
