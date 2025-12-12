"""Handler for Webex webhooks."""

import hashlib
import hmac
import uuid
from typing import Any

from fastapi import HTTPException, Request
import structlog

from app.config import get_settings
from app.core.logging import get_logger, LogEvents
from app.handlers.message_handler import MessageHandler
from app.models.webex import WebhookPayload
from app.services.user_service import UserService
from app.services.webex_service import WebexService

logger = get_logger("webhook_handler")


class WebhookHandler:
    """Handles incoming webhooks from Webex."""

    def __init__(
        self,
        webex_service: WebexService,
        user_service: UserService,
        message_handler: MessageHandler,
    ) -> None:
        self._webex = webex_service
        self._users = user_service
        self._messages = message_handler
        self._settings = get_settings()

    def _validate_signature(self, body: bytes, signature: str | None) -> bool:
        """Validate webhook signature using HMAC-SHA1."""
        secret = self._settings.webex_webhook_secret

        if not secret:
            logger.debug("webhook_signature_check_skipped", reason="no_secret")
            return True

        if not signature:
            logger.warning(
                LogEvents.WEBHOOK_VALIDATION_FAILED,
                reason="missing_signature",
            )
            return False

        # Calculate expected signature
        expected = hmac.new(
            key=secret.encode("utf-8"),
            msg=body,
            digestmod=hashlib.sha1,
        ).hexdigest()

        # Secure comparison
        if not hmac.compare_digest(signature, expected):
            logger.warning(
                LogEvents.WEBHOOK_VALIDATION_FAILED,
                reason="invalid_signature",
            )
            return False

        logger.debug(LogEvents.WEBHOOK_VALIDATED)
        return True

    async def handle(self, request: Request) -> dict[str, Any]:
        """
        Process an incoming webhook.

        Args:
            request: FastAPI request object

        Returns:
            Response dict with status

        Raises:
            HTTPException: For validation errors
        """
        # Generate request ID for tracing
        request_id = str(uuid.uuid4())[:8]

        # Bind context for logging
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Read and validate body
        body = await request.body()

        # Validate signature
        signature = request.headers.get("X-Spark-Signature")
        if not self._validate_signature(body, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse payload
        try:
            payload = WebhookPayload.model_validate_json(body)
        except Exception as e:
            logger.error("webhook_parse_error", error=str(e))
            raise HTTPException(status_code=400, detail="Invalid payload") from e

        logger.info(
            LogEvents.WEBHOOK_RECEIVED,
            webhook_id=payload.id,
            resource=payload.resource.value,
            event=payload.event.value,
            actor_email=payload.data.person_email,
        )

        # Only process message:created events
        if payload.resource.value != "messages" or payload.event.value != "created":
            logger.debug("webhook_ignored", reason="not_message_created")
            return {"status": "ignored", "reason": "not_message_created"}

        # Ignore messages from self
        if self._webex.is_from_self(payload.data.person_email):
            logger.debug(LogEvents.MESSAGE_FROM_SELF)
            return {"status": "ignored", "reason": "from_self"}

        # Check user authorization
        if not self._users.is_authorized(payload.data.person_email):
            logger.warning(
                LogEvents.USER_NOT_WHITELISTED,
                email=payload.data.person_email,
            )
            await self._webex.send_message(
                room_id=payload.data.room_id,
                text="Sorry, you are not authorized to use this bot. Please contact an administrator.",
            )
            return {"status": "unauthorized"}

        # Fetch full message content
        try:
            message = await self._webex.get_message(payload.data.id)
        except Exception as e:
            logger.error("message_fetch_failed", error=str(e))
            return {"status": "error", "error": "Failed to fetch message"}

        # Process the message
        try:
            await self._messages.handle(message)
            logger.info(LogEvents.WEBHOOK_PROCESSED, message_id=payload.data.id)
            return {"status": "processed", "message_id": payload.data.id}
        except Exception as e:
            logger.error("message_processing_failed", error=str(e))
            return {"status": "error", "error": str(e)}


async def verify_webhook_setup(webex_service: WebexService) -> dict[str, Any]:
    """
    Verify webhook is properly configured.

    Returns information about the current webhook setup.
    """
    try:
        bot_email = webex_service.bot_email
        bot_id = webex_service.bot_id

        return {
            "status": "ok",
            "bot_email": bot_email,
            "bot_id": bot_id,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }
