#!/usr/bin/env python3
"""Script to set up Webex webhook for the bot."""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from webexteamssdk import WebexTeamsAPI
from webexteamssdk.exceptions import ApiError

from app.config import get_settings


def setup_webhook(target_url: str, name: str = "Presales Assistant Webhook") -> None:
    """Set up or update the Webex webhook."""
    settings = get_settings()
    api = WebexTeamsAPI(access_token=settings.webex_bot_token)

    # Get bot info
    bot = api.people.me()
    print(f"Bot: {bot.displayName} ({bot.emails[0]})")

    # List existing webhooks
    existing = list(api.webhooks.list())
    print(f"Found {len(existing)} existing webhooks")

    # Find webhook with same name
    webhook_to_update = None
    for wh in existing:
        if wh.name == name:
            webhook_to_update = wh
            break

    webhook_data = {
        "name": name,
        "targetUrl": target_url,
        "resource": "messages",
        "event": "created",
    }

    if settings.webex_webhook_secret:
        webhook_data["secret"] = settings.webex_webhook_secret

    if webhook_to_update:
        # Update existing
        print(f"Updating webhook: {webhook_to_update.id}")
        webhook = api.webhooks.update(
            webhookId=webhook_to_update.id,
            **webhook_data,
        )
        print(f"Updated webhook: {webhook.id}")
    else:
        # Create new
        print("Creating new webhook...")
        webhook = api.webhooks.create(**webhook_data)
        print(f"Created webhook: {webhook.id}")

    print(f"  Name: {webhook.name}")
    print(f"  Target URL: {webhook.targetUrl}")
    print(f"  Resource: {webhook.resource}")
    print(f"  Event: {webhook.event}")
    print(f"  Status: {webhook.status}")


def list_webhooks() -> None:
    """List all webhooks."""
    settings = get_settings()
    api = WebexTeamsAPI(access_token=settings.webex_bot_token)

    webhooks = list(api.webhooks.list())
    print(f"Found {len(webhooks)} webhooks:\n")

    for wh in webhooks:
        print(f"  ID: {wh.id}")
        print(f"  Name: {wh.name}")
        print(f"  Target: {wh.targetUrl}")
        print(f"  Resource: {wh.resource}")
        print(f"  Event: {wh.event}")
        print(f"  Status: {wh.status}")
        print()


def delete_webhook(webhook_id: str) -> None:
    """Delete a webhook."""
    settings = get_settings()
    api = WebexTeamsAPI(access_token=settings.webex_bot_token)

    try:
        api.webhooks.delete(webhook_id)
        print(f"Deleted webhook: {webhook_id}")
    except ApiError as e:
        print(f"Error deleting webhook: {e}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Manage Webex webhooks")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Setup command
    setup_parser = subparsers.add_parser("setup", help="Set up webhook")
    setup_parser.add_argument("url", help="Target URL for webhook")
    setup_parser.add_argument("--name", default="Presales Assistant Webhook", help="Webhook name")

    # List command
    subparsers.add_parser("list", help="List all webhooks")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a webhook")
    delete_parser.add_argument("id", help="Webhook ID to delete")

    args = parser.parse_args()

    if args.command == "setup":
        setup_webhook(args.url, args.name)
    elif args.command == "list":
        list_webhooks()
    elif args.command == "delete":
        delete_webhook(args.id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
