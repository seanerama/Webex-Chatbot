"""Conversation history management service."""

from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger, LogEvents
from app.models.user import ConversationContext

logger = get_logger("history_service")


class HistoryService:
    """Service for managing conversation history.

    Uses in-memory storage for simplicity. In production,
    this could be backed by Redis, DynamoDB, etc.
    """

    def __init__(self, max_history_per_room: int = 50) -> None:
        self._history: dict[str, ConversationContext] = {}
        self._max_history = max_history_per_room

    def get_or_create_context(
        self,
        room_id: str,
        user_email: str,
    ) -> ConversationContext:
        """Get existing context or create a new one."""
        if room_id not in self._history:
            self._history[room_id] = ConversationContext(
                room_id=room_id,
                user_email=user_email,
            )
            logger.debug(
                "conversation_context_created",
                room_id=room_id,
                user_email=user_email,
            )
        return self._history[room_id]

    def get_context(self, room_id: str) -> ConversationContext | None:
        """Get conversation context for a room."""
        context = self._history.get(room_id)
        if context:
            logger.debug(
                LogEvents.HISTORY_RETRIEVED,
                room_id=room_id,
                message_count=context.message_count,
            )
        return context

    def add_message(
        self,
        room_id: str,
        user_email: str,
        role: str,
        content: str,
    ) -> ConversationContext:
        """Add a message to the conversation history."""
        context = self.get_or_create_context(room_id, user_email)
        context.add_message(role, content)

        # Trim history if too long
        if len(context.messages) > self._max_history:
            context.messages = context.messages[-self._max_history:]

        logger.debug(
            LogEvents.HISTORY_UPDATED,
            room_id=room_id,
            role=role,
            message_count=context.message_count,
        )

        return context

    def get_messages_for_llm(
        self,
        room_id: str,
        max_messages: int = 20,
    ) -> list[dict[str, Any]]:
        """Get conversation messages formatted for LLM context."""
        context = self._history.get(room_id)
        if not context:
            return []
        return context.get_messages_for_llm(max_messages)

    def clear_history(self, room_id: str) -> bool:
        """Clear conversation history for a room."""
        if room_id in self._history:
            self._history[room_id].clear()
            logger.info(LogEvents.HISTORY_CLEARED, room_id=room_id)
            return True
        return False

    def delete_context(self, room_id: str) -> bool:
        """Completely delete conversation context for a room."""
        if room_id in self._history:
            del self._history[room_id]
            logger.info("conversation_context_deleted", room_id=room_id)
            return True
        return False

    def set_provider(self, room_id: str, provider: str) -> None:
        """Set the provider being used for a conversation."""
        context = self._history.get(room_id)
        if context:
            context.provider_used = provider
            logger.debug(
                "conversation_provider_set",
                room_id=room_id,
                provider=provider,
            )

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about conversation history."""
        total_rooms = len(self._history)
        total_messages = sum(c.message_count for c in self._history.values())
        active_rooms = sum(
            1
            for c in self._history.values()
            if (datetime.now(timezone.utc) - c.last_updated).seconds < 3600
        )

        return {
            "total_rooms": total_rooms,
            "total_messages": total_messages,
            "active_rooms_last_hour": active_rooms,
        }

    def cleanup_old_contexts(self, max_age_hours: int = 24) -> int:
        """Remove conversation contexts older than max_age_hours."""
        now = datetime.now(timezone.utc)
        to_remove = []

        for room_id, context in self._history.items():
            age_hours = (now - context.last_updated).total_seconds() / 3600
            if age_hours > max_age_hours:
                to_remove.append(room_id)

        for room_id in to_remove:
            del self._history[room_id]

        if to_remove:
            logger.info(
                "old_contexts_cleaned",
                removed_count=len(to_remove),
                max_age_hours=max_age_hours,
            )

        return len(to_remove)
