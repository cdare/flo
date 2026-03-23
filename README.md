# Flo — Personal Assistant Agent

A conversational AI assistant that handles tasks via Discord and WhatsApp, powered by LangGraph orchestration and multi-tier LLM routing.

## Features

- **Multi-channel support** — Discord bot and WhatsApp webhook integrations
- **Smart LLM routing** — Uses cheap models (GPT-4o-mini) for simple tasks, premium models (GPT-4o) for complex planning
- **Skill-based tools** — Google Calendar, Gmail, and web search
- **Conversation memory** — SQLite-backed persistence for chat history and user preferences
- **User learning** — Remembers corrections and preferences across conversations

## Architecture

```
Discord / WhatsApp
        ↓
FastAPI Webhook Server (/chat)
        ↓
LangGraph Agent Orchestrator
   ├─ classify → route by complexity
   ├─ plan     → multi-step reasoning (premium LLM)
   ├─ execute  → tool calls (cheap LLM)
   └─ respond  → format reply
        ↓
Skill Layer
   ├─ CalendarSkill → Google Calendar API
   ├─ GmailSkill    → Gmail API
   └─ SearchSkill   → Web search (Tavily/SerpAPI)
        ↓
LLM Router (litellm)
```

## Requirements

- Python 3.12+
- [pyenv](https://github.com/pyenv/pyenv) with virtualenv (recommended)

## Installation

```bash
# Clone the repository
git clone https://github.com/cdare/flo.git
cd flo

# Install dependencies
make install-dev

# Copy environment template
cp .env.example .env
```

## Configuration

Edit `.env` with your API keys:

```bash
# Required — at least one LLM provider
OPENAI_API_KEY=sk-...

# Optional — for Gmail and Calendar skills
# Download credentials.json from Google Cloud Console
FLO_GOOGLE_CREDENTIALS_PATH=credentials.json

# Optional — for web search
FLO_SEARCH_API_KEY=tvly-...   # Tavily
FLO_SEARCH_PROVIDER=tavily

# Optional — Discord bot
DISCORD_BOT_TOKEN=...

# Optional — WhatsApp (Meta Cloud API)
WHATSAPP_VERIFY_TOKEN=...
WHATSAPP_API_TOKEN=...
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | OpenAI API key (required for default models) |
| `FLO_CHEAP_MODEL` | `gpt-4o-mini` | Model for simple tasks |
| `FLO_PREMIUM_MODEL` | `gpt-4o` | Model for complex planning |
| `FLO_DB_PATH` | `flo.db` | SQLite database path |
| `FLO_PORT` | `8000` | Server port |
| `FLO_LOG_LEVEL` | `info` | Logging level |
| `FLO_SEARCH_PROVIDER` | `tavily` | Search provider (`tavily` or `serpapi`) |
| `FLO_SEARCH_API_KEY` | — | Search provider API key |

## Usage

### Start the Server

```bash
make run       # Start in background
make status    # Check if running
make logs      # View recent logs
make stop      # Stop the server
```

### Send a Message

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "chris",
    "conversation_id": "conv1",
    "message": "What meetings do I have today?"
  }'
```

### Response

```json
{
  "response": "You have 2 meetings today:\n- 10:00 AM: Team standup\n- 2:00 PM: Project review",
  "conversation_id": "conv1"
}
```

### Health Check

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

## Google APIs Setup

To enable Calendar and Gmail skills:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable Calendar API + Gmail API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download as `credentials.json` in the project root
5. On first use, a browser window will open for authentication
6. Token is saved to `token.json` for future use

## Development

```bash
# Run tests
make test

# Run tests with coverage
make test-cov

# Lint code
make lint

# Auto-format
make format

# Type check
make typecheck
```

### Project Structure

```
src/flo/
├── config.py           # Pydantic settings
├── log.py              # Structured logging (structlog)
├── llm/
│   ├── router.py       # LLM routing (cheap/premium)
│   └── models.py       # TaskType, LLMResponse
├── agent/
│   ├── graph.py        # LangGraph StateGraph
│   ├── nodes.py        # Node factories
│   └── state.py        # AgentState schema
├── tools/
│   ├── base.py         # Skill dataclass, registry
│   ├── calendar/       # Google Calendar skill
│   ├── gmail/          # Gmail skill
│   └── search/         # Web search skill
└── server/
    ├── app.py          # FastAPI application
    ├── routes.py       # /chat, /health endpoints
    ├── models.py       # Request/Response schemas
    └── persistence.py  # SQLite setup
```

## License

MIT
