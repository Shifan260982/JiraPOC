# Jira Reporting Assistant (POC)

Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Backend (Python 3.12+)

```powershell
cd backend
py -3 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

No authentication yet: keep it bound to `127.0.0.1`.

### Chat model

Default: **NVIDIA API free tier** (build.nvidia.com, 40 requests/minute). Put `NVIDIA_API_KEY=...` in the
project-root `.env`; the backend reads it at start-up and the chat switches from demo mode automatically.
Code picks the data for each question; a plain text model only writes the one- or two-sentence summary,
and the detail rows under it are rendered by code, so their figures cannot be misstated.

- Models are tried in order; the next is used when one fails, is retired or is rate limited. Override with
  `LLM_MODELS` (comma-separated). Default:
  `nvidia/nemotron-3.5-bolt-e4b,nvidia/nemotron-3.5-lightning-30b-a3b,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`.
- Another OpenAI-compatible provider: set `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODELS`.
- If every model fails, the chat answers in demo mode and says so.

Alternative: local tool-calling model via Ollama (slow on CPU-only machines, 10–30 s per answer;
`llama3.2:3b` is the tested choice):

```powershell
ollama pull llama3.2:3b
.venv\Scripts\python -m pip install "langchain-ollama>=0.3,<2"
$env:LLM_PROVIDER = "ollama"; $env:LLM_MODEL = "llama3.2:3b"
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Port 8001 is the default because 8000 is often taken by other local services; the extension's
"Assistant server" setting must match.

## Extension (Chrome or Edge 116+)

```powershell
cd extension
npm install
npm test
npm run build
```

Load it: `chrome://extensions` (or `edge://extensions`) → Developer mode → **Load unpacked** → select `extension/dist`.

Use it:
1. Sign in to the Foresight tool in the browser.
2. Click the extension icon to open the side panel, paste the Foresight address, and click **Read the tool**.
   The browser asks once for access to the tool and the assistant server.
3. Open a Foresight page and click **Open chat on this page** (or the **Ask** button at the bottom right).

Only read the tool with the client's authorisation.

## Demo with synthetic data (safe to show the client)

`samples/` holds invented data with the same structure as the client's exports (Doe surnames, made-up keys).
Regenerate it with `backend\.venv\Scripts\python samples\generate_samples.py`.

```powershell
backend\.venv\Scripts\python -m http.server 5500 --bind 127.0.0.1 --directory samples\mock-tool
```

Then point the extension at `http://localhost:5500/`. The mock tool has a home page, the Foresight board and a Jira issues page.

UI preview without loading the extension (stubs the browser APIs, replays a recorded scan, uses the live backend on 8001):

```powershell
cd extension
npm run preview:ui
```

After changing the page reader or the mock tool, refresh the backend's end-to-end fixture with `npm run fixture`.
