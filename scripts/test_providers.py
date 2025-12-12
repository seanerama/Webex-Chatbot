#!/usr/bin/env python3
"""Script to test LLM provider connectivity."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings, LLMProvider
from app.core.logging import setup_logging
from app.providers.registry import ProviderRegistry


async def test_provider(provider: LLMProvider) -> dict:
    """Test a single provider."""
    settings = get_settings()
    config = settings.get_provider_config(provider)

    result = {
        "provider": provider.value,
        "model": config.model,
        "configured": False,
        "healthy": False,
        "error": None,
    }

    # Check if configured
    if provider == LLMProvider.OLLAMA:
        result["configured"] = True  # Always available
    elif provider == LLMProvider.ANTHROPIC:
        result["configured"] = bool(settings.anthropic_api_key)
    elif provider == LLMProvider.OPENAI:
        result["configured"] = bool(settings.openai_api_key)
    elif provider == LLMProvider.GEMINI:
        result["configured"] = bool(settings.gemini_api_key)

    if not result["configured"]:
        result["error"] = "Not configured (missing API key)"
        return result

    # Test connectivity
    try:
        instance = ProviderRegistry.create_provider(provider)
        result["healthy"] = await instance.health_check()
        if not result["healthy"]:
            result["error"] = "Health check failed"
    except Exception as e:
        result["error"] = str(e)

    return result


async def test_all_providers() -> None:
    """Test all providers."""
    print("Testing LLM Providers...")
    print("=" * 50)

    for provider in LLMProvider:
        result = await test_provider(provider)

        status = ""
        if result["healthy"]:
            status = "OK"
        elif result["configured"]:
            status = "UNHEALTHY"
        else:
            status = "NOT CONFIGURED"

        print(f"\n{provider.value}:")
        print(f"  Status: {status}")
        print(f"  Model: {result['model']}")
        if result["error"]:
            print(f"  Error: {result['error']}")

    print("\n" + "=" * 50)


async def test_chat(provider_name: str, message: str = "Hello! Please respond with a short greeting.") -> None:
    """Test a chat request to a provider."""
    print(f"\nTesting chat with {provider_name}...")

    try:
        provider = LLMProvider(provider_name)
        instance = ProviderRegistry.create_provider(provider)

        from app.models.llm import ChatMessage, MessageRole

        messages = [ChatMessage(role=MessageRole.USER, content=message)]

        response = await instance.chat(messages=messages)

        print(f"Response: {response.content}")
        print(f"Model: {response.model}")
        print(f"Finish reason: {response.finish_reason}")
        if response.usage:
            print(f"Tokens: {response.usage.total_tokens}")

    except Exception as e:
        print(f"Error: {e}")


def main() -> None:
    """Main entry point."""
    setup_logging()

    import argparse

    parser = argparse.ArgumentParser(description="Test LLM providers")
    parser.add_argument("--provider", "-p", help="Test specific provider")
    parser.add_argument("--chat", "-c", action="store_true", help="Test chat functionality")
    parser.add_argument("--message", "-m", default="Hello!", help="Message to send for chat test")

    args = parser.parse_args()

    if args.provider and args.chat:
        asyncio.run(test_chat(args.provider, args.message))
    elif args.provider:
        result = asyncio.run(test_provider(LLMProvider(args.provider)))
        print(f"Provider: {result['provider']}")
        print(f"Healthy: {result['healthy']}")
        if result["error"]:
            print(f"Error: {result['error']}")
    else:
        asyncio.run(test_all_providers())


if __name__ == "__main__":
    main()
