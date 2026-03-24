# Tools & Skills Setup

Flo uses a skill-based tool system. Each skill provides tools for a specific domain (Calendar, Gmail, Search). Skills are optional — Flo works without them, just with reduced capabilities.

## Available Skills

| Skill | Tools | Requirements |
|-------|-------|--------------|
| **Calendar** | List, create, update, delete events | Google OAuth credentials |
| **Gmail** | List, read, search, send emails | Google OAuth credentials |
| **Search** | Web search | Tavily or SerpAPI key |

---

## Google OAuth Setup (Calendar & Gmail)

Both Calendar and Gmail skills require Google OAuth 2.0 credentials. This is a one-time setup.

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown (top left) → **New Project**
3. Name it (e.g., "Flo Assistant") → **Create**
4. Wait for project creation, then select it

### Step 2: Enable APIs

1. Go to **APIs & Services** → **Library**
2. Search for and enable:
   - **Google Calendar API**
   - **Gmail API**
3. Click each one → **Enable**

### Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** (unless you have a Google Workspace org) → **Create**
3. Fill in required fields:
   - **App name:** Flo Assistant
   - **User support email:** Your email
   - **Developer contact:** Your email
4. Click **Save and Continue**
5. **Scopes:** Click **Add or Remove Scopes**, add:
   - `https://www.googleapis.com/auth/calendar`
   - `https://www.googleapis.com/auth/gmail.modify`
6. Click **Save and Continue**
7. **Test users:** Add your Google account email
8. Click **Save and Continue** → **Back to Dashboard**

### Step 4: Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **OAuth client ID**
3. Application type: **Desktop app**
4. Name: "Flo CLI" (or anything)
5. Click **Create**
6. Click **Download JSON** on the popup
7. Save the file as `credentials.json` in your Flo project root

### Step 5: First Run Authentication

1. Start Flo: `make run`
2. Send any message that uses Calendar or Gmail
3. A browser window opens for Google sign-in
4. Sign in with the account you added as a test user
5. Click **Continue** through the "unverified app" warning (this is your own app)
6. Grant the requested permissions
7. Authentication completes — a `token.json` file is created

The token refreshes automatically. You only need to re-authenticate if you revoke access or the token expires (rare).

### Troubleshooting

| Issue | Solution |
|-------|----------|
| "Access blocked: This app's request is invalid" | Ensure your email is in the test users list |
| "redirect_uri_mismatch" | Use **Desktop app** type, not Web application |
| "Token has been expired or revoked" | Delete `token.json` and re-authenticate |
| "The caller does not have permission" | Check that both APIs are enabled |
| Browser doesn't open | Ensure you're running on a machine with a browser, or use `--no-browser` flow |

### Security Notes

- `credentials.json` contains your OAuth client ID/secret — don't commit it to git
- `token.json` contains your access token — also keep it private
- Both files are in `.gitignore` by default
- For production, consider using a service account instead of OAuth

---

## Search Setup

Flo supports two search providers. You only need one.

### Option A: Tavily (Recommended)

[Tavily](https://tavily.com/) is optimized for AI agents with clean, structured results.

1. Sign up at [tavily.com](https://tavily.com/)
2. Get your API key from the dashboard
3. Add to `.env`:
   ```bash
   FLO_SEARCH_PROVIDER=tavily
   FLO_SEARCH_API_KEY=tvly-...
   ```

**Pricing:** Free tier includes 1,000 searches/month.

### Option B: SerpAPI

[SerpAPI](https://serpapi.com/) provides Google search results.

1. Sign up at [serpapi.com](https://serpapi.com/)
2. Get your API key from the dashboard
3. Add to `.env`:
   ```bash
   FLO_SEARCH_PROVIDER=serpapi
   FLO_SEARCH_API_KEY=...
   ```

**Pricing:** Free tier includes 100 searches/month.

---

## Verifying Skill Registration

Check which skills are active in the startup logs:

```
# All skills registered
skills.google.registered  skills=["calendar", "gmail"]
skills.search.registered  provider="tavily"

# Skills skipped (credentials missing)
skills.google.skipped  reason="credentials.json not found"
skills.search.skipped  reason="FLO_SEARCH_API_KEY not set"
```

Or query the health endpoint:

```bash
curl http://localhost:8000/health
```

---

## Adding Custom Skills

Skills are modular. To add a new skill:

1. Create a module in `src/flo/tools/myskill/`
2. Define tools using `@tool` decorator from `langchain_core.tools`
3. Create a `Skill` dataclass with name, description, tools list
4. Register in `register_skills()` in `src/flo/tools/__init__.py`

Example structure:

```python
# src/flo/tools/myskill/tools.py
from langchain_core.tools import tool

def create_myskill_tools(api_client):
    @tool
    def my_action(param: str) -> str:
        """Do something useful."""
        return api_client.do_thing(param)
    
    return [my_action]

# src/flo/tools/myskill/__init__.py
from flo.tools.base import Skill
from flo.tools.myskill.tools import create_myskill_tools

def create_myskill(client) -> Skill:
    return Skill(
        name="myskill",
        description="Does useful things",
        tools=create_myskill_tools(client),
    )
```

The factory pattern (`create_*_tools(service)`) keeps credentials out of module scope and enables testing with mocks.
