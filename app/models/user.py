"""User and conversation models."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class UserPreferences(BaseModel):
    """User-specific preferences."""

    response_style: str = "balanced"  # technical, detailed, concise, balanced
    max_response_length: int = Field(default=4000, ge=100, le=7000)
    include_references: bool = True
    streaming: bool = True


class UserConfig(BaseModel):
    """Configuration for an authorized user."""

    enabled: bool = True
    display_name: str | None = None
    provider: str | None = None  # anthropic, openai, gemini, ollama
    model: str | None = None  # Override default model
    system_prompt: str | None = None
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    is_admin: bool = False


class ConversationContext(BaseModel):
    """Conversation context for a room/DM."""

    room_id: str
    user_email: str
    messages: list[dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message_count: int = 0
    provider_used: str | None = None  # Track provider for this conversation

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation."""
        self.messages.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.message_count += 1
        self.last_updated = datetime.now(timezone.utc)

    def get_messages_for_llm(self, max_messages: int = 20) -> list[dict]:
        """Get recent messages formatted for LLM context."""
        # Return most recent messages, respecting the limit
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        return [{"role": m["role"], "content": m["content"]} for m in recent]

    def clear(self) -> None:
        """Clear conversation history."""
        self.messages = []
        self.message_count = 0
        self.last_updated = datetime.now(timezone.utc)


class UsersConfig(BaseModel):
    """Configuration for all users (loaded from users.json)."""

    users: dict[str, UserConfig] = Field(default_factory=dict)
    default_system_prompt: str = (
        "You are a helpful AI assistant for presales engineers. "
        "You help answer technical questions about networking, storage, compute, "
        "and cloud infrastructure. Provide accurate, detailed responses and cite "
        "sources when possible. If you're unsure about something, say so rather "
        "than guessing."
    )
    default_preferences: UserPreferences = Field(default_factory=UserPreferences)

    def get_user(self, email: str) -> UserConfig | None:
        """Get configuration for a specific user."""
        return self.users.get(email)

    def is_authorized(self, email: str) -> bool:
        """Check if a user is authorized (exists and enabled)."""
        user = self.users.get(email)
        return user is not None and user.enabled

    def get_system_prompt(self, email: str) -> str:
        """Get the system prompt for a user."""
        user = self.users.get(email)
        if user and user.system_prompt:
            return user.system_prompt
        return self.default_system_prompt
