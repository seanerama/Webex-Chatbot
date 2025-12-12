"""Webex webhook and message models."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class WebhookResource(str, Enum):
    """Webex webhook resource types."""

    MESSAGES = "messages"
    MEMBERSHIPS = "memberships"
    ROOMS = "rooms"


class WebhookEvent(str, Enum):
    """Webex webhook event types."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class WebhookData(BaseModel):
    """Data payload from webhook."""

    id: str
    room_id: str = Field(alias="roomId")
    room_type: str | None = Field(default=None, alias="roomType")
    person_id: str = Field(alias="personId")
    person_email: str = Field(alias="personEmail")
    created: datetime

    model_config = {"populate_by_name": True}


class WebhookPayload(BaseModel):
    """Complete webhook payload from Webex."""

    id: str
    name: str
    target_url: str = Field(alias="targetUrl")
    resource: WebhookResource
    event: WebhookEvent
    org_id: str = Field(alias="orgId")
    created_by: str = Field(alias="createdBy")
    app_id: str = Field(alias="appId")
    owned_by: str = Field(alias="ownedBy")
    status: str
    created: datetime
    actor_id: str = Field(alias="actorId")
    data: WebhookData

    model_config = {"populate_by_name": True}


class WebexMessage(BaseModel):
    """Message retrieved from Webex API."""

    id: str
    room_id: str = Field(alias="roomId")
    room_type: str = Field(alias="roomType")
    text: str | None = None
    markdown: str | None = None
    html: str | None = None
    person_id: str = Field(alias="personId")
    person_email: str = Field(alias="personEmail")
    created: datetime

    model_config = {"populate_by_name": True}

    @property
    def content(self) -> str:
        """Get message content, preferring markdown."""
        return self.markdown or self.text or ""

    @classmethod
    def from_sdk_message(cls, message: object) -> "WebexMessage":
        """Create from webexteamssdk Message object."""
        return cls(
            id=message.id,  # type: ignore[attr-defined]
            roomId=message.roomId,  # type: ignore[attr-defined]
            roomType=message.roomType,  # type: ignore[attr-defined]
            text=getattr(message, "text", None),
            markdown=getattr(message, "markdown", None),
            html=getattr(message, "html", None),
            personId=message.personId,  # type: ignore[attr-defined]
            personEmail=message.personEmail,  # type: ignore[attr-defined]
            created=message.created,  # type: ignore[attr-defined]
        )
