"""Handler for slash commands."""

import re
from typing import Any, Callable, Coroutine

from app.config import LLMProvider, get_settings
from app.core.logging import get_logger, LogEvents
from app.services.history_service import HistoryService
from app.services.user_service import UserService
from app.providers.registry import ProviderRegistry

logger = get_logger("command_handler")

# Type alias for command handlers
CommandFunc = Callable[..., Coroutine[Any, Any, str]]


class CommandHandler:
    """Handler for bot slash commands."""

    def __init__(
        self,
        user_service: UserService,
        history_service: HistoryService,
    ) -> None:
        self._users = user_service
        self._history = history_service
        self._settings = get_settings()
        self._commands: dict[str, CommandFunc] = {}
        self._register_commands()

    def _register_commands(self) -> None:
        """Register all available commands."""
        self._commands = {
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/clear": self._cmd_clear,
            "/model": self._cmd_model,
            "/providers": self._cmd_providers,
            "/whoami": self._cmd_whoami,
            "/history": self._cmd_history,
        }

    def is_command(self, text: str) -> bool:
        """Check if text is a command."""
        return text.strip().startswith("/")

    def parse_command(self, text: str) -> tuple[str, list[str]]:
        """Parse command and arguments from text."""
        parts = text.strip().split()
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        return command, args

    async def handle(
        self,
        text: str,
        user_email: str,
        room_id: str,
    ) -> str | None:
        """
        Handle a command message.

        Args:
            text: Message text (including command)
            user_email: Email of user who sent command
            room_id: Room where command was sent

        Returns:
            Response message, or None if not a command
        """
        if not self.is_command(text):
            return None

        command, args = self.parse_command(text)

        logger.info(
            LogEvents.COMMAND_DETECTED,
            command=command,
            args=args,
            user_email=user_email,
        )

        handler = self._commands.get(command)
        if not handler:
            return self._unknown_command(command)

        try:
            response = await handler(
                user_email=user_email,
                room_id=room_id,
                args=args,
            )
            logger.info(
                LogEvents.COMMAND_EXECUTED,
                command=command,
                user_email=user_email,
            )
            return response
        except Exception as e:
            logger.error(
                "command_execution_error",
                command=command,
                error=str(e),
            )
            return f"Error executing command: {e}"

    def _unknown_command(self, command: str) -> str:
        """Response for unknown commands."""
        available = ", ".join(sorted(self._commands.keys()))
        return f"Unknown command: `{command}`\n\nAvailable commands: {available}"

    async def _cmd_help(self, **kwargs: Any) -> str:
        """Show help information."""
        return """**Webex Presales Assistant** - Available Commands

**General:**
- `/help` - Show this help message
- `/status` - Check bot and provider status
- `/whoami` - Show your user information

**Conversation:**
- `/clear` - Clear conversation history
- `/history` - Show conversation history stats

**Model Selection:**
- `/model` - Show current model
- `/model <provider>` - Switch to a provider (anthropic, openai, gemini, ollama)
- `/model <provider> <model>` - Switch to specific model
- `/providers` - List available providers

**Examples:**
- `/model anthropic` - Use Claude
- `/model openai gpt-4o` - Use GPT-4o
- `/model ollama llama3.1:8b` - Use local Llama

Just send a message to chat with the AI assistant!
"""

    async def _cmd_status(self, **kwargs: Any) -> str:
        """Show bot status."""
        settings = self._settings
        available = settings.get_available_providers()

        status_lines = [
            "**Bot Status**",
            "",
            f"- Default Provider: `{settings.default_llm_provider.value}`",
            f"- Default Model: `{settings.default_llm_model}`",
            f"- MCP Enabled: `{settings.mcp_enabled}`",
            f"- Environment: `{settings.app_env.value}`",
            "",
            "**Available Providers:**",
        ]

        for provider in available:
            config = settings.get_provider_config(provider)
            status_lines.append(f"- `{provider.value}`: {config.model}")

        # Add history stats
        history_stats = self._history.get_stats()
        status_lines.extend([
            "",
            "**Conversation Stats:**",
            f"- Active Rooms: {history_stats['total_rooms']}",
            f"- Total Messages: {history_stats['total_messages']}",
        ])

        return "\n".join(status_lines)

    async def _cmd_clear(self, room_id: str, **kwargs: Any) -> str:
        """Clear conversation history."""
        cleared = self._history.clear_history(room_id)
        if cleared:
            return "Conversation history cleared."
        return "No conversation history to clear."

    async def _cmd_model(
        self,
        user_email: str,
        room_id: str,
        args: list[str],
        **kwargs: Any,
    ) -> str:
        """Show or change the model."""
        # Get current context
        context = self._history.get_context(room_id)
        current_provider = context.provider_used if context else None

        if not args:
            # Show current model
            user_config = self._users.get_user(user_email)
            user_provider = user_config.provider if user_config else None
            user_model = user_config.model if user_config else None

            lines = ["**Current Model Configuration:**", ""]

            if current_provider:
                lines.append(f"- Session Provider: `{current_provider}`")
            if user_provider:
                lines.append(f"- User Default: `{user_provider}`")
            if user_model:
                lines.append(f"- User Model: `{user_model}`")

            lines.extend([
                f"- System Default: `{self._settings.default_llm_provider.value}`",
                f"- System Model: `{self._settings.default_llm_model}`",
            ])

            return "\n".join(lines)

        # Change model
        provider_name = args[0].lower()
        model_name = args[1] if len(args) > 1 else None

        # Validate provider
        try:
            provider = LLMProvider(provider_name)
        except ValueError:
            available = ", ".join(p.value for p in LLMProvider)
            return f"Unknown provider: `{provider_name}`\n\nAvailable: {available}"

        if provider not in self._settings.get_available_providers():
            return f"Provider `{provider_name}` is not configured."

        # Set the provider for this conversation
        self._history.set_provider(room_id, provider_name)

        response = f"Switched to `{provider_name}`"
        if model_name:
            response += f" with model `{model_name}`"

        return response

    async def _cmd_providers(self, **kwargs: Any) -> str:
        """List available providers."""
        available = self._settings.get_available_providers()

        lines = ["**Available LLM Providers:**", ""]

        for provider in LLMProvider:
            config = self._settings.get_provider_config(provider)
            if provider in available:
                status = "configured"
                lines.append(f"- `{provider.value}`: {config.model} ({status})")
            else:
                lines.append(f"- `{provider.value}`: not configured")

        return "\n".join(lines)

    async def _cmd_whoami(self, user_email: str, **kwargs: Any) -> str:
        """Show user information."""
        info = self._users.get_user_info(user_email)

        lines = [
            "**Your Information:**",
            "",
            f"- Email: `{info['email']}`",
            f"- Authorized: `{info['authorized']}`",
        ]

        if info.get("display_name"):
            lines.append(f"- Display Name: {info['display_name']}")
        if info.get("provider"):
            lines.append(f"- Preferred Provider: `{info['provider']}`")
        if info.get("model"):
            lines.append(f"- Preferred Model: `{info['model']}`")
        if info.get("is_admin"):
            lines.append("- Role: **Admin**")

        return "\n".join(lines)

    async def _cmd_history(self, room_id: str, **kwargs: Any) -> str:
        """Show conversation history stats."""
        context = self._history.get_context(room_id)

        if not context:
            return "No conversation history in this room."

        lines = [
            "**Conversation History:**",
            "",
            f"- Messages: {context.message_count}",
            f"- Started: {context.created_at.isoformat()}",
            f"- Last Updated: {context.last_updated.isoformat()}",
        ]

        if context.provider_used:
            lines.append(f"- Provider: `{context.provider_used}`")

        return "\n".join(lines)
