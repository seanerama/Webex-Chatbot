"""Application configuration using Pydantic Settings."""

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"


class LogFormat(str, Enum):
    """Log output formats."""

    JSON = "json"
    CONSOLE = "console"


class Environment(str, Enum):
    """Application environments."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ProviderConfig:
    """Configuration for a specific LLM provider."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        base_url: str | None = None,
        timeout: int = 120,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.base_url = base_url
        self.timeout = timeout


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Webex Configuration
    webex_bot_token: str = Field(..., description="Webex bot access token")
    webex_webhook_secret: str | None = Field(
        default=None, description="Webhook signature verification secret"
    )

    # Default LLM Provider
    default_llm_provider: LLMProvider = Field(
        default=LLMProvider.ANTHROPIC, description="Default LLM provider"
    )
    default_llm_model: str = Field(
        default="claude-sonnet-4-20250514", description="Default model to use"
    )

    # Anthropic Configuration
    anthropic_api_key: str | None = Field(default=None)
    anthropic_model: str = Field(default="claude-sonnet-4-20250514")
    anthropic_max_tokens: int = Field(default=8192)

    # OpenAI Configuration
    openai_api_key: str | None = Field(default=None)
    openai_model: str = Field(default="gpt-4o")
    openai_max_tokens: int = Field(default=4096)

    # Gemini Configuration
    gemini_api_key: str | None = Field(default=None)
    gemini_model: str = Field(default="gemini-1.5-pro")
    gemini_max_tokens: int = Field(default=8192)

    # Ollama Configuration
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3.1:8b")
    ollama_timeout: int = Field(default=120)

    # MCP Configuration
    mcp_server_url: str = Field(default="http://localhost:8080")
    mcp_enabled: bool = Field(default=True)

    # Application Settings
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    app_env: Environment = Field(default=Environment.DEVELOPMENT)
    debug: bool = Field(default=True)

    # Logging Configuration
    log_level: str = Field(default="DEBUG")
    log_format: LogFormat = Field(default=LogFormat.JSON)
    log_file_path: str = Field(default="./logs/bot.log")

    # Users configuration file path
    users_config_path: str = Field(default="./users.json")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v_upper

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == Environment.PRODUCTION

    def get_provider_config(self, provider: str | LLMProvider) -> ProviderConfig:
        """Get configuration for a specific provider."""
        if isinstance(provider, str):
            provider = LLMProvider(provider)

        configs = {
            LLMProvider.ANTHROPIC: ProviderConfig(
                api_key=self.anthropic_api_key,
                model=self.anthropic_model,
                max_tokens=self.anthropic_max_tokens,
            ),
            LLMProvider.OPENAI: ProviderConfig(
                api_key=self.openai_api_key,
                model=self.openai_model,
                max_tokens=self.openai_max_tokens,
            ),
            LLMProvider.GEMINI: ProviderConfig(
                api_key=self.gemini_api_key,
                model=self.gemini_model,
                max_tokens=self.gemini_max_tokens,
            ),
            LLMProvider.OLLAMA: ProviderConfig(
                base_url=self.ollama_base_url,
                model=self.ollama_model,
                timeout=self.ollama_timeout,
            ),
        }
        return configs[provider]

    def get_available_providers(self) -> list[LLMProvider]:
        """Get list of providers with valid configuration."""
        providers = []

        if self.anthropic_api_key:
            providers.append(LLMProvider.ANTHROPIC)
        if self.openai_api_key:
            providers.append(LLMProvider.OPENAI)
        if self.gemini_api_key:
            providers.append(LLMProvider.GEMINI)

        # Ollama is always available (local)
        providers.append(LLMProvider.OLLAMA)

        return providers

    def is_provider_available(self, provider: str | LLMProvider) -> bool:
        """Check if a provider is configured and available."""
        if isinstance(provider, str):
            provider = LLMProvider(provider)
        return provider in self.get_available_providers()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
