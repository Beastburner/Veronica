# VERONICA — Personal AI Operating System

> A JARVIS-level personal AI assistant. Local-first, privacy-respecting, and built to learn how you work.

---

## What is VERONICA?

VERONICA is a fully self-hosted AI assistant that runs entirely on your machine using [Ollama](https://ollama.ai). No cloud API keys, no data sent to third parties. It learns your patterns, manages your life, and acts on your behalf — always with your confirmation first.

---

## Architecture

```
apps/
├── api/          FastAPI backend (Python)
│   └── app/
│       ├── main.py           API routes, session management
│       ├── agent.py          LLM prompt engine, mode system
│       ├── llm_client.py     Ollama client (OpenAI-compatible)
│       ├── intent_router.py  Fast intent classification (regex + LLM)
│       ├── tools.py          Tool registry (web, email, calendar, etc.)
│       ├── behavior.py       Behavioral learning & personalized suggestions
│       ├── gmail.py          Gmail integration
│       ├── gcal.py           Google Calendar integration
│       ├── scheduler.py      Proactive reminders & briefings
│       ├── storage.py        SQLite CRUD helpers
│       └── db.py             Schema & DB management
└── web/          Next.js frontend
    └── components/
        ├── ArcCore.tsx       Main chat interface
        ├── EmailPanel.tsx    Gmail panel
        ├── CalendarPanel.tsx Calendar panel
        ├── ActivityPanel.tsx Life log timeline
        └── OperationsPanels.tsx Tasks, reminders, notes
```

---

## Core Features

### Modes
| Mode | Personality | Best for |
|------|-------------|----------|
| **JARVIS** | Formal, precise, systems-first | Architecture, planning, technical decisions |
| **FRIDAY** | Warm, proactive, productivity | Task management, focus, daily routine |
| **VERONICA** | Sharp, dry wit, brutally concise | Quick answers, triage, ops |
| **SENTINEL** | Terse, threat-aware | Security review, risk assessment |

### Current Capabilities

- **Chat** — Streaming + non-streaming chat with full context management
- **Email (Gmail)** — Read inbox, search, compose, draft, **send with confirmation**
- **Calendar** — List events, create meetings (always asks for confirmation first)
- **Tasks** — Create, update, complete, delete tasks
- **Reminders** — Time-bound reminders with proactive scheduler
- **Notes** — Quick notes and long-term memory
- **Web Search** — DuckDuckGo search with instant answers
- **Web Scraping** — Fetch and extract text from any URL
- **Weather** — Live weather for any city
- **Calculator** — Safe expression evaluation
- **Voice Input** — Whisper transcription (local, `/transcribe`)
- **TTS** — ElevenLabs text-to-speech proxy
- **Daily Briefing** — Morning summary of tasks, reminders, calendar
- **Life Log** — Automatic timeline of all actions
- **Behavioral Learning** — Learns your patterns, gives personalized suggestions
- **GitHub** — View and create issues
- **System Commands** — Safe whitelisted shell commands

---

## Setup

### Prerequisites

1. **[Ollama](https://ollama.ai)** — install and pull your model:
   ```
   ollama pull qwen2.5:7b
   ```

2. **Node.js 20+** and **Python 3.11+**

### Quick Start (Windows)

```powershell
.\start.ps1
```

That's it. The script will:
1. Check for Python and Node.js
2. Create the Python virtual environment and install all packages (first run only)
3. Install frontend and WhatsApp bridge dependencies (first run only)
4. Open all three services in separate terminal windows

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| WhatsApp bridge | http://localhost:3001 |

**Options:**
```powershell
.\start.ps1            # normal launch (auto-installs on first run)
.\start.ps1 -install   # force reinstall all dependencies, then launch
.\start.ps1 -dev       # same as above, but labelled as dev mode
```

### Manual Start (optional)

<details>
<summary>Expand manual instructions</summary>

**Backend:**
```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd apps/web
npm install
npm run dev
```

**WhatsApp bridge:**
```bash
cd apps/whatsapp
npm install
node index.js
```

</details>

Open `http://localhost:3000`

### Configuration (`apps/api/.env`)

```env
# Ollama (local LLM — no API key needed)
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1

# Optional: Google OAuth (Gmail + Calendar)
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret

# Optional: ElevenLabs TTS
ELEVENLABS_API_KEY=your_key

SENDER_NAME=Your Name
```

---

## Behavioral Learning

VERONICA learns from every interaction. Over time it will:

- **Detect patterns** — notices when you're most active, what topics you work on
- **Suggest proactively** — "It's Monday morning, time to plan your week"
- **Surface your priorities** — suggestions based on what you ask about most
- **Time-aware hints** — morning briefing reminders, end-of-day wrap suggestions

View your behavior insights:
```
GET /behavior/insights
```

---

## Web Scraping

Ask VERONICA to fetch and read any webpage:

```
scrape https://example.com/article
fetch content from https://docs.python.org/3/library/asyncio.html
summarize the page at https://news.ycombinator.com
```

VERONICA extracts the readable text, strips ads/scripts, and summarizes it via the LLM.

---

## Confirmation Flow

For irreversible actions, VERONICA **always shows a preview and waits for your go-ahead**:

**Email:**
```
You: send an email to boss@company.com about the project update
VERONICA: Here's the draft:
  To: boss@company.com
  Subject: Project Update
  ...
  Send this?
You: yes / no
```

**Calendar:**
```
You: schedule a meeting with the team tomorrow at 3pm
VERONICA: Here's the meeting:
  Title: Team Meeting
  Time: 2026-05-07T15:00:00
  Schedule this?
You: yes / no
```

---

## Planned Features (Roadmap)

### Phase 2 — Intelligence Layer
- **Semantic memory** — vector embeddings for "do you remember when I said..." queries
- **Multi-step planner** — break complex goals into ordered tasks automatically
- **Smart inbox triage** — auto-label, prioritize, and draft replies to emails
- **Meeting notes** — auto-generate notes from voice transcriptions

### Phase 3 — Integrations
- **WhatsApp** — read message summaries, send replies (via whatsapp-web.py automation)
  - Will scan QR code once to link WhatsApp Web
  - Summarize unread messages per contact/group
  - Draft and send replies with confirmation before sending
  - Keyword alerts: notify when someone mentions important words
- **Notion / Obsidian** — sync notes bidirectionally
- **GitHub** — PR reviews, commit summaries, issue triage
- **Spotify** — music control based on productivity mode (focus = lo-fi, SENTINEL = silence)
- **System monitor** — CPU/RAM/disk alerts when thresholds are crossed

### Phase 4 — Proactive Intelligence
- **News digest** — daily curated summary from RSS feeds of your choice
- **Habit tracker** — daily habit logging with streak tracking and gentle nudges
- **Focus timer (Pomodoro)** — built-in 25/5 timer with automatic life-log entries
- **Auto-journal** — end-of-day summary of everything you did (from life log)
- **Predictive scheduling** — suggest meeting times based on your calendar patterns
- **Smart clipboard** — save and retrieve code snippets, URLs, and text by topic
- **Context carry-over** — resume yesterday's conversations with full context

### Phase 5 — Advanced
- **Browser history analysis** — context from your recent browsing for smarter suggestions
- **Local file assistant** — search, summarize, and ask questions about local documents (PDF, DOCX)
- **Code review** — diff analysis and PR feedback via local LLM
- **Wake phrase** — "Hey Veronica" browser-side detection to activate voice mode without clicking
- **Multi-device sync** — share session context across devices via encrypted relay
- **Email auto-replies** — draft replies to common emails with one-click send

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat` | Non-streaming chat |
| POST | `/chat/stream` | Server-sent event streaming chat |
| GET | `/briefing/today` | Daily briefing |
| GET | `/behavior/insights` | Behavioral patterns and suggestions |
| GET | `/email/inbox` | Gmail inbox |
| POST | `/email/send` | Send email |
| GET | `/calendar/events` | Upcoming events |
| POST | `/calendar/events` | Create event |
| GET | `/tasks` | List tasks |
| POST | `/tasks` | Create task |
| GET | `/reminders` | List reminders |
| POST | `/reminders` | Create reminder |
| GET | `/notes` | List notes |
| POST | `/notes` | Create note |
| GET | `/memory` | Long-term memories |
| GET | `/life-log` | Activity timeline |
| GET | `/health` | API health |
| GET | `/health/model` | Ollama model status |
| GET | `/oauth/status` | Google OAuth status |
| GET | `/oauth/google/start` | Start Google OAuth |

---

## WhatsApp Integration (Planned — Phase 3)

WhatsApp automation will work via `whatsapp-web.py` — a library that automates WhatsApp Web in a headless browser. This requires:

1. Scan a QR code once to link your WhatsApp account
2. VERONICA reads incoming messages and groups them by contact
3. Ask: "summarize my WhatsApp messages" — VERONICA gives you a per-contact digest
4. Ask: "reply to [name] saying I'll be there at 5" — VERONICA drafts and shows the message
5. You confirm → message sent

The confirmation-first pattern means VERONICA will **always show you the message before sending**.

---

## Privacy

- **All LLM inference runs locally** via Ollama — no prompts leave your machine
- **Google data** (Gmail/Calendar) is accessed via your own OAuth credentials
- **SQLite database** is stored locally at `apps/api/veronica.db`
- No telemetry, no analytics, no external services except what you configure

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| LLM | Ollama (local, any model — | TTS | ElevenLabs (optional) |
| WhatsApp | whatsapp-web.js (Puppeteer, local) |
��──────┤
  │ Backfill          │ Scheduler embeds existing records without embeddings (on startup + every 10min) │
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────┤
  │ Unified search    │ semantic_search() searches across memories AND notes by cosine similarity       │
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────┤
  │ Threshold         │ Lowered from 0.4 → 0.2, plus keyword fallback if no hits                        │
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────┤
  │ Context injection │ build_assistant_context() uses semantic search for both memories and notes      │
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────┤
  │ Intent routing    │ "what do I know about X?" → instant semantic answer                             │
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────┤
  │ API routes        │ GET /search?q=, /memory/search?q=, /notes/search?q=                             │
  └───────────────────┴─────────────────────────────────────────────────────────────────────────────────┘


    ollama pull nomic-embed-text