"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.core.logging import get_logger, setup_logging, LogEvents
from app.handlers.command_handler import CommandHandler
from app.handlers.message_handler import MessageHandler
from app.handlers.webhook_handler import WebhookHandler, verify_webhook_setup
from app.services.history_service import HistoryService
from app.services.llm_service import LLMService
from app.services.mcp_service import MCPService
from app.services.user_service import UserService
from app.services.webex_service import WebexService

# Initialize logging early
setup_logging()
logger = get_logger("main")


# Service instances (initialized in lifespan)
class AppState:
    """Application state container."""

    webex_service: WebexService
    user_service: UserService
    history_service: HistoryService
    mcp_service: MCPService
    llm_service: LLMService
    command_handler: CommandHandler
    message_handler: MessageHandler
    webhook_handler: WebhookHandler


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    settings = get_settings()

    logger.info(
        LogEvents.APP_STARTING,
        version=__version__,
        environment=settings.app_env.value,
        debug=settings.debug,
    )

    # Initialize services
    app_state.webex_service = WebexService()
    app_state.user_service = UserService()
    app_state.history_service = HistoryService()
    app_state.mcp_service = MCPService()
    app_state.llm_service = LLMService(mcp_service=app_state.mcp_service)

    # Initialize handlers
    app_state.command_handler = CommandHandler(
        user_service=app_state.user_service,
        history_service=app_state.history_service,
    )
    app_state.message_handler = MessageHandler(
        webex_service=app_state.webex_service,
        user_service=app_state.user_service,
        history_service=app_state.history_service,
        llm_service=app_state.llm_service,
        command_handler=app_state.command_handler,
    )
    app_state.webhook_handler = WebhookHandler(
        webex_service=app_state.webex_service,
        user_service=app_state.user_service,
        message_handler=app_state.message_handler,
    )

    # Initialize MCP tools
    try:
        await app_state.mcp_service.initialize()
    except Exception as e:
        logger.warning("mcp_initialization_failed", error=str(e))

    logger.info(
        LogEvents.APP_STARTED,
        available_providers=[p.value for p in settings.get_available_providers()],
        mcp_enabled=settings.mcp_enabled,
    )

    yield

    # Cleanup
    logger.info(LogEvents.APP_SHUTDOWN)
    app_state.webex_service.cleanup()
    await app_state.mcp_service.close()


# Create FastAPI app
app = FastAPI(
    title="Webex Presales Assistant",
    description="AI assistant for presales engineers via Webex Teams",
    version=__version__,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Routes
@app.get("/")
async def root() -> dict[str, Any]:
    """Root endpoint - basic info."""
    return {
        "name": "Webex Presales Assistant",
        "version": __version__,
        "status": "running",
    }


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    settings = get_settings()

    # Check webex connection
    webex_status = await verify_webhook_setup(app_state.webex_service)

    # Check MCP
    mcp_healthy = await app_state.mcp_service.health_check()

    # Get history stats
    history_stats = app_state.history_service.get_stats()

    return {
        "status": "healthy",
        "version": __version__,
        "environment": settings.app_env.value,
        "webex": webex_status,
        "mcp": {"enabled": settings.mcp_enabled, "healthy": mcp_healthy},
        "providers": {
            "available": [p.value for p in settings.get_available_providers()],
            "default": settings.default_llm_provider.value,
        },
        "conversations": history_stats,
    }


@app.get("/providers/health")
async def providers_health() -> dict[str, Any]:
    """Check health of all LLM providers."""
    return await app_state.llm_service.health_check()


@app.post("/webhook")
async def webhook(request: Request) -> dict[str, Any]:
    """Webex webhook endpoint."""
    return await app_state.webhook_handler.handle(request)


@app.post("/webhooks/messages")
async def webhook_messages(request: Request) -> dict[str, Any]:
    """Alternative webhook endpoint for messages."""
    return await app_state.webhook_handler.handle(request)


@app.get("/stats")
async def stats() -> dict[str, Any]:
    """Get application statistics."""
    return {
        "conversations": app_state.history_service.get_stats(),
        "users": {
            "authorized_count": len(app_state.user_service.list_authorized_users()),
            "admin_count": len(app_state.user_service.list_admins()),
        },
        "tools": {
            "count": len(app_state.mcp_service.get_tools()),
            "enabled": app_state.mcp_service.is_enabled,
        },
    }


@app.post("/admin/reload-users")
async def reload_users() -> dict[str, Any]:
    """Reload user configuration from file."""
    try:
        app_state.user_service.reload_config()
        return {
            "status": "ok",
            "message": "User configuration reloaded",
            "user_count": len(app_state.user_service.list_authorized_users()),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/admin/clear-history")
async def clear_all_history() -> dict[str, Any]:
    """Clear all conversation history."""
    stats_before = app_state.history_service.get_stats()
    # Clear by cleaning up old contexts with 0 hour threshold
    cleared = app_state.history_service.cleanup_old_contexts(max_age_hours=0)
    return {
        "status": "ok",
        "cleared_rooms": stats_before["total_rooms"],
        "cleared_messages": stats_before["total_messages"],
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler."""
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


# Development entry point
if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )
