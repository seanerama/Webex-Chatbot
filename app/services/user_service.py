"""User management and authorization service."""

import json
from pathlib import Path
from typing import Any

from app.config import LLMProvider, get_settings
from app.core.exceptions import ConfigurationError, UserNotAuthorizedError
from app.core.logging import get_logger, LogEvents
from app.models.user import UserConfig, UserPreferences, UsersConfig

logger = get_logger("user_service")


class UserService:
    """Service for managing users and their configurations."""

    def __init__(self, config_path: str | None = None) -> None:
        settings = get_settings()
        self._config_path = Path(config_path or settings.users_config_path)
        self._config: UsersConfig | None = None
        self._load_config()

    def _load_config(self) -> None:
        """Load user configuration from file."""
        if not self._config_path.exists():
            logger.warning(
                "users_config_not_found",
                path=str(self._config_path),
            )
            # Create default config
            self._config = UsersConfig()
            return

        try:
            with open(self._config_path) as f:
                data = json.load(f)

            # Parse users
            users: dict[str, UserConfig] = {}
            for email, user_data in data.get("users", {}).items():
                # Parse preferences if present
                prefs_data = user_data.pop("preferences", {})
                preferences = UserPreferences(**prefs_data) if prefs_data else UserPreferences()
                users[email] = UserConfig(preferences=preferences, **user_data)

            # Parse default preferences
            default_prefs_data = data.get("default_preferences", {})
            default_prefs = (
                UserPreferences(**default_prefs_data)
                if default_prefs_data
                else UserPreferences()
            )

            self._config = UsersConfig(
                users=users,
                default_system_prompt=data.get(
                    "default_system_prompt", UsersConfig().default_system_prompt
                ),
                default_preferences=default_prefs,
            )

            logger.info(
                LogEvents.USER_CONFIG_LOADED,
                user_count=len(users),
                config_path=str(self._config_path),
            )

        except json.JSONDecodeError as e:
            logger.error("users_config_parse_error", error=str(e))
            raise ConfigurationError(f"Invalid users.json: {e}") from e
        except Exception as e:
            logger.error("users_config_load_error", error=str(e))
            raise ConfigurationError(f"Failed to load users config: {e}") from e

    def reload_config(self) -> None:
        """Reload user configuration from file."""
        self._load_config()

    @property
    def config(self) -> UsersConfig:
        """Get the users configuration."""
        if self._config is None:
            self._config = UsersConfig()
        return self._config

    def is_authorized(self, email: str) -> bool:
        """Check if a user is authorized to use the bot."""
        # If no users are configured, allow all (development mode)
        if not self.config.users:
            logger.debug("no_users_configured_allowing_all")
            return True

        authorized = self.config.is_authorized(email)
        if not authorized:
            logger.warning(LogEvents.USER_NOT_WHITELISTED, email=email)
        return authorized

    def get_user(self, email: str) -> UserConfig | None:
        """Get user configuration."""
        return self.config.get_user(email)

    def get_user_or_default(self, email: str) -> UserConfig:
        """Get user configuration or return default."""
        user = self.config.get_user(email)
        if user:
            return user
        # Return a default configuration
        return UserConfig(
            enabled=True,
            preferences=self.config.default_preferences,
        )

    def get_system_prompt(self, email: str) -> str:
        """Get the system prompt for a user."""
        return self.config.get_system_prompt(email)

    def get_provider_for_user(self, email: str) -> str | None:
        """Get the preferred provider for a user."""
        user = self.config.get_user(email)
        return user.provider if user else None

    def get_model_for_user(self, email: str) -> str | None:
        """Get the preferred model for a user."""
        user = self.config.get_user(email)
        return user.model if user else None

    def get_preferences(self, email: str) -> UserPreferences:
        """Get user preferences."""
        user = self.config.get_user(email)
        if user:
            return user.preferences
        return self.config.default_preferences

    def is_admin(self, email: str) -> bool:
        """Check if a user is an admin."""
        user = self.config.get_user(email)
        return user.is_admin if user else False

    def require_authorization(self, email: str) -> None:
        """Raise exception if user is not authorized."""
        if not self.is_authorized(email):
            raise UserNotAuthorizedError(email)

    def get_user_info(self, email: str) -> dict[str, Any]:
        """Get formatted user info for display."""
        user = self.config.get_user(email)
        if not user:
            return {
                "email": email,
                "authorized": self.is_authorized(email),
                "display_name": None,
                "provider": None,
                "model": None,
                "is_admin": False,
            }

        return {
            "email": email,
            "authorized": user.enabled,
            "display_name": user.display_name,
            "provider": user.provider,
            "model": user.model,
            "is_admin": user.is_admin,
            "preferences": user.preferences.model_dump(),
        }

    def list_authorized_users(self) -> list[str]:
        """List all authorized user emails."""
        return [
            email
            for email, user in self.config.users.items()
            if user.enabled
        ]

    def list_admins(self) -> list[str]:
        """List all admin user emails."""
        return [
            email
            for email, user in self.config.users.items()
            if user.enabled and user.is_admin
        ]
