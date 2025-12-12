"""Webex API service for messaging operations."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from webexteamssdk import WebexTeamsAPI
from webexteamssdk.exceptions import ApiError

from app.config import get_settings
from app.core.exceptions import WebexAPIError
from app.core.logging import get_logger, LogEvents
from app.models.webex import WebexMessage
from app.utils.message_chunker import chunk_message

logger = get_logger("webex_service")

# Webex message length limit
MAX_MESSAGE_LENGTH = 7439


class WebexService:
    """Service for Webex API operations."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api = WebexTeamsAPI(access_token=settings.webex_bot_token)
        self._bot_info: Any | None = None
        self._executor = ThreadPoolExecutor(max_workers=4)

    async def _run_sync(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous function in a thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: func(*args, **kwargs),
        )

    def _get_bot_info(self) -> Any:
        """Get bot info (cached, synchronous)."""
        if self._bot_info is None:
            self._bot_info = self._api.people.me()
        return self._bot_info

    @property
    def bot_email(self) -> str:
        """Get the bot's email address (cached)."""
        return self._get_bot_info().emails[0]

    @property
    def bot_id(self) -> str:
        """Get the bot's person ID (cached)."""
        return self._get_bot_info().id

    def is_from_self(self, person_email: str) -> bool:
        """Check if a message is from the bot itself."""
        return person_email == self.bot_email

    async def get_message(self, message_id: str) -> WebexMessage:
        """Retrieve a message by ID."""
        logger.debug("fetching_message", message_id=message_id)

        try:
            message = await self._run_sync(self._api.messages.get, message_id)

            logger.debug(
                "message_fetched",
                message_id=message_id,
                has_text=bool(getattr(message, "text", None)),
                has_markdown=bool(getattr(message, "markdown", None)),
            )

            return WebexMessage.from_sdk_message(message)

        except ApiError as e:
            logger.error(LogEvents.WEBEX_API_ERROR, message_id=message_id, error=str(e))
            raise WebexAPIError(
                f"Failed to get message: {e}",
                status_code=getattr(e, "status_code", None),
            ) from e

    async def send_message(
        self,
        room_id: str,
        text: str | None = None,
        markdown: str | None = None,
    ) -> str:
        """
        Send a message to a room.

        Automatically chunks long messages into multiple sends.

        Returns:
            The message ID of the last sent message
        """
        content = markdown or text or ""

        # Chunk if necessary
        chunks = chunk_message(content, MAX_MESSAGE_LENGTH)

        logger.info(
            "sending_message",
            room_id=room_id,
            content_length=len(content),
            chunk_count=len(chunks),
        )

        last_message_id = ""

        for i, chunk in enumerate(chunks):
            try:
                kwargs: dict[str, Any] = {"roomId": room_id}
                if markdown:
                    kwargs["markdown"] = chunk
                else:
                    kwargs["text"] = chunk

                message = await self._run_sync(
                    self._api.messages.create,
                    **kwargs,
                )

                last_message_id = message.id

                logger.debug(
                    LogEvents.WEBEX_MESSAGE_SENT,
                    message_id=message.id,
                    chunk_index=i,
                )

                # Small delay between chunks to avoid rate limiting
                if i < len(chunks) - 1:
                    await asyncio.sleep(0.5)

            except ApiError as e:
                logger.error(LogEvents.WEBEX_API_ERROR, room_id=room_id, error=str(e))
                raise WebexAPIError(
                    f"Failed to send message: {e}",
                    status_code=getattr(e, "status_code", None),
                ) from e

        return last_message_id

    async def update_message(
        self,
        message_id: str,
        room_id: str,
        text: str | None = None,
        markdown: str | None = None,
    ) -> None:
        """Update an existing message (for streaming updates)."""
        try:
            kwargs: dict[str, Any] = {
                "messageId": message_id,
                "roomId": room_id,
            }
            if markdown:
                kwargs["markdown"] = markdown
            else:
                kwargs["text"] = text

            await self._run_sync(self._api.messages.update, **kwargs)

            logger.debug(LogEvents.WEBEX_MESSAGE_UPDATED, message_id=message_id)

        except ApiError as e:
            # Don't raise - update failures are non-critical for streaming
            logger.warning(
                "message_update_failed",
                message_id=message_id,
                error=str(e),
            )

    async def delete_message(self, message_id: str) -> None:
        """Delete a message."""
        try:
            await self._run_sync(self._api.messages.delete, message_id)
            logger.debug("message_deleted", message_id=message_id)
        except ApiError as e:
            logger.warning("message_delete_failed", message_id=message_id, error=str(e))

    async def get_room_info(self, room_id: str) -> dict[str, Any]:
        """Get information about a room."""
        try:
            room = await self._run_sync(self._api.rooms.get, room_id)
            return {
                "id": room.id,
                "title": room.title,
                "type": room.type,
                "is_locked": getattr(room, "isLocked", False),
            }
        except ApiError as e:
            logger.error("room_info_failed", room_id=room_id, error=str(e))
            raise WebexAPIError(f"Failed to get room info: {e}") from e

    async def send_typing_indicator(self, room_id: str) -> None:
        """Send a typing indicator to a room.

        Note: Webex doesn't have a direct typing indicator API,
        but we can simulate it by sending and deleting a message.
        """
        # Webex doesn't support typing indicators directly
        pass

    def cleanup(self) -> None:
        """Cleanup resources."""
        self._executor.shutdown(wait=False)
