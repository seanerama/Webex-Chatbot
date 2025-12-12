# Webex Presales Assistant Bot

An AI-powered Webex Teams chatbot that assists presales engineers with networking, storage, and compute questions. Supports multiple LLM providers and integrates with FastMCP for custom tools.

## Features

- **Multi-LLM Support**: Anthropic Claude, OpenAI GPT, Google Gemini, and Ollama (local)
- **Provider Abstraction**: Easily switch between providers per-user or per-session
- **FastMCP Integration**: Custom tools for knowledge base search, product info, and technical docs
- **User Management**: Per-user provider preferences, system prompts, and access control
- **Conversation History**: Maintains context across messages
- **Streaming Responses**: Real-time response streaming to Webex
- **Automatic Fallback**: Failover between providers if one is unavailable

## Quick Start

### Prerequisites

- Python 3.11+
- A Webex Bot account (create at [developer.webex.com](https://developer.webex.com))
- At least one LLM provider API key (or Ollama for local)
- ngrok (for local development)

### Installation

```bash
# Clone the repository
git clone https://github.com/seanerama/Webex-Chatbot.git
cd Webex-Chatbot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
```

### Configuration

Edit `.env` with your credentials:

```bash
# Required
WEBEX_BOT_TOKEN=your_bot_token_here

# At least one LLM provider
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-...
# or
GEMINI_API_KEY=...
# or use Ollama (no API key needed)
```

### Running Locally

```bash
# Start ngrok tunnel
ngrok http 8000

# In another terminal, set up webhook
python scripts/setup_webhook.py setup https://your-ngrok-url.ngrok.io/webhook

# Run the bot
python -m app.main
# or
uvicorn app.main:app --reload
```

## Usage

### Bot Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/status` | Check bot and provider status |
| `/clear` | Clear conversation history |
| `/model` | Show current model |
| `/model <provider>` | Switch to a different provider |
| `/providers` | List available providers |
| `/whoami` | Show your user info |

### Example Interactions

```
User: /model anthropic
Bot: Switched to `anthropic`

User: What are the key benefits of SD-WAN?
Bot: SD-WAN (Software-Defined Wide Area Network) offers several key benefits...

User: /clear
Bot: Conversation history cleared.
```

## Project Structure

```
webex-presales-assistant/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration management
│   ├── core/                # Logging, exceptions
│   ├── models/              # Pydantic data models
│   ├── providers/           # LLM provider implementations
│   ├── services/            # Business logic services
│   ├── handlers/            # Request handlers
│   └── utils/               # Utility functions
├── scripts/                 # Setup and test scripts
├── tests/                   # Test suite
└── logs/                    # Log files
```

## User Configuration

Create `users.json` to configure per-user settings:

```json
{
  "users": {
    "alice@example.com": {
      "enabled": true,
      "provider": "anthropic",
      "system_prompt": "You are a networking specialist..."
    }
  },
  "default_system_prompt": "You are a helpful AI assistant..."
}
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Basic info |
| `/health` | GET | Health check |
| `/webhook` | POST | Webex webhook handler |
| `/providers/health` | GET | Check LLM provider status |
| `/stats` | GET | Application statistics |

## Development

```bash
# Run tests
pytest

# Type checking
mypy app

# Linting
ruff check app

# Format code
ruff format app
```

## License

MIT
