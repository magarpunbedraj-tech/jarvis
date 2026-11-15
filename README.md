# Jarvis Multi-Agent (Local-first)
A personal multi-agent AI dashboard with specialist agents, shared task/event memory, Ollama local inference, optional OpenAI-compatible API, and task queue.

## Current MVP
- Manager orchestrates 1–3 specialist agents sequentially and synthesizes results.
- Specialist roles: Coding, Browser, Computer, Research, Voice, Memory.
- Shared task/event log records agent starts, completions, manager-to-agent handoffs and agent-to-manager messages.
- Web dashboard with agent selector, chat, task queue, run buttons and activity stream.
- Ollama local inference or OpenAI-compatible cloud API. API key remains in local .env.
- Persistent tasks/events in ./data.

**Important capability boundary:** This version is a working multi-agent chat/task MVP, not yet a fully autonomous computer operator. Browser/desktop agents currently plan and explain actions; actual local mouse/keyboard/browser execution requires a separate local worker and explicit permissions. Never expose this app publicly without authentication.

## Windows quick start
1. Install Python 3.11+ and Ollama: https://ollama.com/download
2. In PowerShell: `ollama pull qwen2.5:7b` (recommended first model for 16GB VRAM; try 14B if it fits)
3. Copy `.env.example` to `.env`; choose model/API settings.
4. Run `start-windows.bat` (creates venv, installs dependencies, starts server).
5. Open http://127.0.0.1:8787

Manual:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8787
```

## API provider
Local Ollama default:
- OLLAMA_BASE_URL=http://localhost:11434
- OLLAMA_MODEL=qwen2.5:7b

Optional cloud OpenAI-compatible:
- AI_BASE_URL (base URL, e.g. provider's OpenAI-compatible endpoint)
- AI_API_KEY
- AI_MODEL

Cloud mode is selected only when all three are configured.

## Endpoints
- GET /api/health, /api/agents, /api/tasks, /api/events, /api/config
- POST /api/chat {message, agent} (manager automatically delegates)
- POST /api/orchestrate {message}
- POST /api/tasks {title, description, agent, priority}
- POST /api/tasks/{id}/run
- POST /api/agent-message {from_agent,to_agent,content,task_id}

## Safety
No arbitrary shell commands, file deletion, purchases, credential access, or desktop clicks are executed by this MVP. Add audited local tools and human approval gates before enabling real computer control. Keep host bound to 127.0.0.1.
