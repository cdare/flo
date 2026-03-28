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

### LLM Provider Options

Flo uses [litellm](https://docs.litellm.ai/) for LLM abstraction, supporting 100+ models. Switch providers by changing `FLO_CHEAP_MODEL` and `FLO_PREMIUM_MODEL`:

| Provider | Model String | Example |
|----------|-------------|--------|
| OpenAI | `gpt-4o`, `gpt-4o-mini`, `o3-mini` | `FLO_PREMIUM_MODEL=gpt-4o` |
| Anthropic | `anthropic/claude-3-5-sonnet-20241022`, `anthropic/claude-3-5-haiku-20241022` | `FLO_PREMIUM_MODEL=anthropic/claude-3-5-sonnet-20241022` |
| Google | `gemini/gemini-2.0-flash`, `gemini/gemini-2.0-pro` | `FLO_CHEAP_MODEL=gemini/gemini-2.0-flash` |
| Groq | `groq/llama-3.3-70b-versatile` | `FLO_CHEAP_MODEL=groq/llama-3.3-70b-versatile` |
| Mistral | `mistral/mistral-large-latest` | `FLO_PREMIUM_MODEL=mistral/mistral-large-latest` |
| Ollama (local) | `ollama/llama3.1:8b`, `ollama/llama3.2:3b` | `FLO_CHEAP_MODEL=ollama/llama3.2:3b` |

#### Recommended Configurations

**Cost-optimized** (cheapest viable):
```bash
FLO_CHEAP_MODEL=gemini/gemini-2.0-flash
FLO_PREMIUM_MODEL=gpt-4o-mini
```

**Quality-optimized** (best results):
```bash
FLO_CHEAP_MODEL=gpt-4o
FLO_PREMIUM_MODEL=anthropic/claude-3-5-sonnet-20241022
```

**Privacy-first** (local only, requires [Ollama](https://ollama.ai/)):
```bash
FLO_CHEAP_MODEL=ollama/llama3.2:3b
FLO_PREMIUM_MODEL=ollama/llama3.1:8b
# Start Ollama first: ollama serve
```

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

To enable Calendar and Gmail skills, you need Google OAuth credentials. See [docs/tools.md](docs/tools.md) for detailed step-by-step instructions.

Quick summary:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable Calendar API + Gmail API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download as `credentials.json` in the project root
5. On first use, a browser window will open for authentication
6. Token is saved to `token.json` for future use

## Remote Server Deployment

These instructions cover deploying Flo on a Ubuntu 20.04+ VPS or cloud instance.

### Server Requirements

- Ubuntu 20.04+ (or equivalent Linux distro)
- Python 3.12+
- git

### Install

```bash
git clone https://github.com/cdare/flo.git
cd flo
make install-dev
```

### Configure

```bash
cp .env.example .env
# Edit .env — set your API keys and:
FLO_ENV=production
# Optionally set an absolute DB path so data survives redeployments:
FLO_DB_PATH=/var/lib/flo/flo.db
```

### Transfer Google Credentials

If you use Calendar or Gmail, copy your credential files from your local machine:

```bash
scp credentials.json token.json user@your-server:/path/to/flo/
```

### Open Firewall Port

```bash
sudo ufw allow 8000
sudo ufw reload
```

### Quick Start

```bash
make run      # Start server in background (PID-managed)
make status   # Confirm it's running
make logs     # Tail logs
make stop     # Stop server
```

The server listens on `0.0.0.0:8000` by default.

### Systemd Service (Recommended for Production)

Create `/etc/systemd/system/flo.service`:

```ini
[Unit]
Description=Flo Personal Assistant
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/path/to/flo
EnvironmentFile=/path/to/flo/.env
ExecStart=/path/to/flo/.venv/bin/uvicorn flo.server.app:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable flo
sudo systemctl start flo
sudo systemctl status flo
```

### Nginx Reverse Proxy (Optional)

To serve Flo behind a domain name with SSL, add a site config in `/etc/nginx/sites-available/flo`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/flo /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Then use [Certbot](https://certbot.eff.org/) to add HTTPS.

---

## Discord Bot Setup

### 1. Create a Discord Application

1. Go to [https://discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application**, give it a name (e.g. "Flo")
3. Under the **Bot** tab, click **Add Bot**
4. Copy the **Token** — you'll need this in a moment

### 2. Enable Required Intents

Still on the **Bot** tab, scroll to **Privileged Gateway Intents** and enable:

- **Message Content Intent** ✓

### 3. Invite the Bot to Your Server

1. Go to **OAuth2 → URL Generator**
2. Under **Scopes**, select `bot`
3. Under **Bot Permissions**, select:
   - `Send Messages`
   - `Read Message History`
   - `View Channels`
4. Copy the generated URL, open it in a browser, and select your server

### 4. Configure Flo

Add the bot token to your `.env`:

```bash
FLO_DISCORD_TOKEN=your-bot-token-here
```

Optionally restrict the bot to a single channel. To get a channel ID, enable **Developer Mode** in Discord Settings → Advanced, then right-click any channel and choose **Copy ID**:

```bash
FLO_DISCORD_CHANNEL_ID=123456789012345678   # 0 = respond in all channels (default)
```

### 5. Start the Bot

```bash
python -m flo.integrations.discord
```

### 6. Test

- **DM the bot** directly — it will respond to any message
- **@mention the bot** in a server channel — it will respond to mentions

---

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
