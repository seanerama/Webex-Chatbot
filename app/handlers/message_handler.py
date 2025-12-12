"""Handler for natural language messages."""

import asyncio
from typing import Any

from app.config import get_settings
from app.core.exceptions import LLMError
from app.core.logging import get_logger, LogEvents
from app.handlers.command_handler import CommandHandler
from app.models.webex import WebexMessage
from app.services.history_service import HistoryService
from app.services.llm_service import LLMService
from app.services.user_service import UserService
from app.services.webex_service import WebexService
from app.utils.markdown_detector import should_use_markdown

logger = get_logger("message_handler")


class MessageHandler:
    """Handler for processing user messages."""

    def __init__(
        self,
        webex_service: WebexService,
        user_service: UserService,
        history_service: HistoryService,
        llm_service: LLMService,
        command_handler: CommandHandler,
    ) -> None:
        self._webex = webex_service
        self._users = user_service
        self._history = history_service
        self._llm = llm_service
        self._commands = command_handler
        self._settings = get_settings()

    async def handle(self, message: WebexMessage) -> None:
        """
        Process an incoming message.

        Routes to command handler or LLM based on content.

        Args:
            message: Webex message to process
        """
        content = message.content.strip()
        user_email = message.person_email
        room_id = message.room_id

        logger.info(
            LogEvents.MESSAGE_RECEIVED,
            room_id=room_id,
            user_email=user_email,
            content_length=len(content),
        )

        # Strip bot mention if present (for group rooms)
        content = self._strip_bot_mention(content)

        if not content:
            logger.debug("empty_message_ignored")
            return

        # Check for commands
        if self._commands.is_command(content):
            response = await self._commands.handle(
                text=content,
                user_email=user_email,
                room_id=room_id,
            )
            if response:
                await self._webex.send_message(
                    room_id=room_id,
                    markdown=response,
                )
            return

        # Process as natural language
        await self._handle_chat_message(
            content=content,
            user_email=user_email,
            room_id=room_id,
        )

    def _strip_bot_mention(self, content: str) -> str:
        """Remove bot mention from message content."""
        bot_email = self._webex.bot_email

        # Remove email mention
        if bot_email in content:
            content = content.replace(bot_email, "").strip()

        # Remove common mention patterns
        # e.g., "@BotName" or "BotName:"
        import re
        content = re.sub(r"^@?\w+:\s*", "", content)

        return content.strip()

    async def _handle_chat_message(
        self,
        content: str,
        user_email: str,
        room_id: str,
    ) -> None:
        """Handle a natural language chat message."""
        # Get user configuration
        user_config = self._users.get_user_or_default(user_email)
        system_prompt = self._users.get_system_prompt(user_email)

        # Determine provider and model
        provider = user_config.provider
        model = user_config.model

        # Check for session override
        context = self._history.get_context(room_id)
        if context and context.provider_used:
            provider = context.provider_used

        # Get conversation history
        history = self._history.get_messages_for_llm(room_id)

        # Add user message to history
        self._history.add_message(
            room_id=room_id,
            user_email=user_email,
            role="user",
            content=content,
        )

        # Check if we should stream
        should_stream = user_config.preferences.streaming

        try:
            if should_stream:
                response_text = await self._stream_response(
                    content=content,
                    system_prompt=system_prompt,
                    history=history,
                    provider=provider,
                    model=model,
                    room_id=room_id,
                )
            else:
                response_text = await self._get_response(
                    content=content,
                    system_prompt=system_prompt,
                    history=history,
                    provider=provider,
                    model=model,
                )

            # Add assistant response to history
            self._history.add_message(
                room_id=room_id,
                user_email=user_email,
                role="assistant",
                content=response_text,
            )

            # Send response (if not already sent via streaming)
            if not should_stream:
                use_markdown = should_use_markdown(response_text)
                if use_markdown:
                    await self._webex.send_message(room_id=room_id, markdown=response_text)
                else:
                    await self._webex.send_message(room_id=room_id, text=response_text)

        except LLMError as e:
            logger.error(
                LogEvents.LLM_REQUEST_FAILED,
                error=str(e),
                provider=provider,
            )
            await self._webex.send_message(
                room_id=room_id,
                text=f"Sorry, I encountered an error: {e.message}",
            )
        except Exception as e:
            logger.error("message_processing_error", error=str(e))
            await self._webex.send_message(
                room_id=room_id,
                text="Sorry, an unexpected error occurred. Please try again.",
            )

    async def _get_response(
        self,
        content: str,
        system_prompt: str,
        history: list[dict[str, Any]],
        provider: str | None,
        model: str | None,
    ) -> str:
        """Get a non-streaming response from the LLM."""
        response = await self._llm.chat(
            message=content,
            system_prompt=system_prompt,
            history=history,
            provider_name=provider,
            model=model,
        )
        return response.content

    async def _stream_response(
        self,
        content: str,
        system_prompt: str,
        history: list[dict[str, Any]],
        provider: str | None,
        model: str | None,
        room_id: str,
    ) -> str:
        """Stream a response from the LLM with live updates."""
        # Send initial "thinking" message
        initial_msg_id = await self._webex.send_message(
            room_id=room_id,
            text="...",
        )

        accumulated_text = ""
        last_update_time = 0.0
        update_interval = 1.0  # Update every second

        try:
            async for chunk in self._llm.stream(
                message=content,
                system_prompt=system_prompt,
                history=history,
                provider_name=provider,
                model=model,
            ):
                if chunk.content:
                    accumulated_text += chunk.content

                    # Throttle updates to avoid rate limiting
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_update_time >= update_interval:
                        use_markdown = should_use_markdown(accumulated_text)
                        if use_markdown:
                            await self._webex.update_message(
                                message_id=initial_msg_id,
                                room_id=room_id,
                                markdown=accumulated_text + "...",
                            )
                        else:
                            await self._webex.update_message(
                                message_id=initial_msg_id,
                                room_id=room_id,
                                text=accumulated_text + "...",
                            )
                        last_update_time = current_time

                if chunk.done:
                    break

            # Final update with complete response
            if accumulated_text:
                use_markdown = should_use_markdown(accumulated_text)
                if use_markdown:
                    await self._webex.update_message(
                        message_id=initial_msg_id,
                        room_id=room_id,
                        markdown=accumulated_text,
                    )
                else:
                    await self._webex.update_message(
                        message_id=initial_msg_id,
                        room_id=room_id,
                        text=accumulated_text,
                    )

            return accumulated_text

        except Exception as e:
            # Try to update the message with error
            await self._webex.update_message(
                message_id=initial_msg_id,
                room_id=room_id,
                text=f"Error: {e}",
            )
            raise
