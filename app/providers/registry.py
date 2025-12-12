"""Provider registry and factory for LLM providers."""

from typing import Any

from app.config import LLMProvider, ProviderConfig, get_settings
from app.core.exceptions import ConfigurationError, LLMProviderError
from app.core.logging import get_logger
from app.providers.anthropic import AnthropicProvider
from app.providers.base import BaseLLMProvider
from app.providers.gemini import GeminiProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai import OpenAIProvider

logger = get_logger("provider_registry")


class ProviderRegistry:
    """Registry and factory for LLM providers."""

    _providers: dict[LLMProvider, type[BaseLLMProvider]] = {
        LLMProvider.ANTHROPIC: AnthropicProvider,
        LLMProvider.OPENAI: OpenAIProvider,
        LLMProvider.GEMINI: GeminiProvider,
        LLMProvider.OLLAMA: OllamaProvider,
    }

    _instances: dict[str, BaseLLMProvider] = {}

    @classmethod
    def get_provider_class(cls, provider: LLMProvider) -> type[BaseLLMProvider]:
        """Get the provider class for a given provider type."""
        if provider not in cls._providers:
            raise ConfigurationError(f"Unknown provider: {provider}")
        return cls._providers[provider]

    @classmethod
    def create_provider(
        cls,
        provider: str | LLMProvider,
        config: ProviderConfig | None = None,
        **kwargs: Any,
    ) -> BaseLLMProvider:
        """Create a new provider instance.

        Args:
            provider: Provider name or enum
            config: Optional provider configuration
            **kwargs: Override configuration values

        Returns:
            Configured provider instance
        """
        if isinstance(provider, str):
            provider = LLMProvider(provider)

        settings = get_settings()

        # Get default config if not provided
        if config is None:
            config = settings.get_provider_config(provider)

        # Build constructor kwargs
        provider_kwargs: dict[str, Any] = {}

        if config.api_key:
            provider_kwargs["api_key"] = config.api_key
        if config.model:
            provider_kwargs["model"] = config.model
        if config.max_tokens:
            provider_kwargs["max_tokens"] = config.max_tokens
        if config.base_url:
            provider_kwargs["base_url"] = config.base_url
        if config.timeout:
            provider_kwargs["timeout"] = config.timeout

        # Apply overrides
        provider_kwargs.update(kwargs)

        # Create instance
        provider_class = cls.get_provider_class(provider)
        instance = provider_class(**provider_kwargs)

        logger.debug(
            "provider_created",
            provider=provider.value,
            model=instance.model,
        )

        return instance

    @classmethod
    def get_or_create_provider(
        cls,
        provider: str | LLMProvider,
        cache_key: str | None = None,
        **kwargs: Any,
    ) -> BaseLLMProvider:
        """Get a cached provider instance or create a new one.

        Args:
            provider: Provider name or enum
            cache_key: Optional key for caching (default: provider name)
            **kwargs: Override configuration values

        Returns:
            Provider instance (may be cached)
        """
        if isinstance(provider, str):
            provider = LLMProvider(provider)

        key = cache_key or provider.value

        if key not in cls._instances:
            cls._instances[key] = cls.create_provider(provider, **kwargs)

        return cls._instances[key]

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached provider instances."""
        cls._instances.clear()

    @classmethod
    async def get_healthy_provider(
        cls,
        preferred: LLMProvider | None = None,
        fallback_order: list[LLMProvider] | None = None,
    ) -> BaseLLMProvider:
        """Get a healthy provider, with fallback support.

        Args:
            preferred: Preferred provider to try first
            fallback_order: Order of providers to try if preferred fails

        Returns:
            A healthy provider instance

        Raises:
            LLMProviderError: If no healthy provider is available
        """
        settings = get_settings()
        available = settings.get_available_providers()

        if fallback_order is None:
            fallback_order = [
                LLMProvider.ANTHROPIC,
                LLMProvider.OPENAI,
                LLMProvider.GEMINI,
                LLMProvider.OLLAMA,
            ]

        # Build ordered list of providers to try
        providers_to_try: list[LLMProvider] = []

        if preferred and preferred in available:
            providers_to_try.append(preferred)

        for p in fallback_order:
            if p in available and p not in providers_to_try:
                providers_to_try.append(p)

        # Try each provider
        for provider in providers_to_try:
            try:
                instance = cls.get_or_create_provider(provider)
                if await instance.health_check():
                    logger.info("healthy_provider_found", provider=provider.value)
                    return instance
                else:
                    logger.warning("provider_unhealthy", provider=provider.value)
            except Exception as e:
                logger.warning(
                    "provider_health_check_failed",
                    provider=provider.value,
                    error=str(e),
                )

        raise LLMProviderError(
            "No healthy LLM provider available",
            provider="none",
        )


def get_provider(
    provider: str | LLMProvider | None = None,
    **kwargs: Any,
) -> BaseLLMProvider:
    """Convenience function to get a provider instance.

    Args:
        provider: Provider name (defaults to configured default)
        **kwargs: Override configuration values

    Returns:
        Provider instance
    """
    settings = get_settings()

    if provider is None:
        provider = settings.default_llm_provider

    return ProviderRegistry.get_or_create_provider(provider, **kwargs)
