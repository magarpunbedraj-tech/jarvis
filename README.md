# Jarvis AI Agency — Multi-Agent MVP

Personal AI agency dashboard with a manager, specialist agents, shared peer context, event history, task queue and API fallback routing.

## Architecture
- Agency Manager plans work and delegates to specialist agents (Research, Coding, Browser, Business, Computer, QA, Memory, Voice).
- Each specialist gets its own role/system prompt.
- Agent outputs are posted into shared agency context; later agents can read peer messages and build on them.
- Manager synthesizes, checks contradictions and reports unverified actions.
- API router tries configured cloud providers in order, logs provider failures, then optionally falls back to Ollama.
- Task and event logs persist in ./data.

## Free API setup (no local GPU required)
1. Get keys from:
   - Gemini AI Studio: https://aistudio.google.com/apikey
   - Groq: https://console.groq.com/keys
   - OpenRouter: https://openrouter.ai/settings/keys
2. Copy `.env.example` to `.env`; paste keys locally. Never commit .env or expose it in screenshots.
3. Set a model ID available to your account. Free availability and quotas change; check each provider dashboard.
4. Run `start-windows.bat`; open http://127.0.0.1:8787.

Provider routing order:
1. AI_BASE_URL + AI_API_KEY + AI_MODEL (custom OpenAI-compatible)
2. GROQ_API_KEY + GROQ_MODEL
3. OPENROUTER_API_KEY + OPENROUTER_MODEL
4. GEMINI_API_KEY + GEMINI_MODEL (native Gemini REST)
5. Ollama (optional local fallback)

Example values are placeholders in .env.example. Don't assume a model is free just because the provider has a free tier. Gemini Free tier has per-model rate limits; free quotas may change. Check official pricing/limits: https://ai.google.dev/gemini-api/docs/pricing and https://ai.google.dev/gemini-api/docs/rate-limits.

## Windows quick start
- Python 3.11+: https://python.org
- Copy .env.example to .env
- Run start-windows.bat
- Dashboard: http://127.0.0.1:8787

## API
- GET /api/health, /api/agents, /api/providers, /api/tasks, /api/events, /api/config
- POST /api/chat {message, agent}
- POST /api/orchestrate {message}
- POST /api/tasks {title, description, agent, priority}
- POST /api/tasks/{id}/run
- POST /api/agent-message {from_agent,to_agent,content,task_id}

## Honest capability boundaries
This is a multi-agent orchestration and chat MVP. Browser/computer agents currently reason and prepare workflows; they do not actually click, navigate authenticated websites, or run arbitrary commands. Scheduled recurring tasks, real local browser/computer workers, approvals, and voice I/O are subsequent modules. Do not expose the server publicly without authentication. Keep it bound to 127.0.0.1.
