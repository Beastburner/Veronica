
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
