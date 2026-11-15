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
- GET/POST/PATCH/DELETE /api/schedules (daily Nepal-time jobs)
- POST /api/worker/action (local approval-gated Windows/browser relay; worker must be running)

## Local real-world browser / Windows actions (approval-gated)
1. In .env, set WORKER_TOKEN to a long random secret (same value is used by API and worker; never share it).
2. Run start-windows.bat in terminal 1 (API/dashboard).
3. Run worker-start.bat in terminal 2 (local Windows worker).
4. In dashboard → Real-world browser & Windows actions, choose Start browser, then navigate. Fill/click/read require a CSS selector and a confirmation prompt for each action.
5. Install Chromium once: python -m playwright install chromium (inside activated .venv).

Worker is bound to 127.0.0.1 by default and only accepts an allowlisted action with the secret token and explicit approval. File operations are confined to this repository folder; app launches are limited to Notepad/Calculator/Paint. Browser interaction can affect real websites: verify URL, selector, and data before approving. Never approve payment, account deletion, sending messages, purchases, or other irreversible actions without carefully reviewing the exact operation. This is not a fully autonomous desktop agent and does not bypass logins, CAPTCHA, MFA, or website protections.

## Full-PC automation (v0.4)
- pyautogui desktop screenshot, coordinate click, keyboard typing/hotkeys, and scroll operate across the active Windows desktop, not only a built-in app.
- list_apps / launch_app scan Start Menu shortcuts for installed app launchers. Apps installed without shortcuts may not appear.
- AI Computer Agent proposes workflows; dashboard displays proposal and asks for confirmation before allowlisted execution. It is not autonomous visual reasoning: screenshot is shown to the operator, who chooses coordinates.
- Visible Chromium supports navigation, CSS-selector fill/click/read; each browser or desktop interaction requires approval.

## Honest capability boundaries
Multi-agent planning still uses LLM-generated plans and can make mistakes. Scheduled jobs run locally only while the API process is open and need a configured provider; provider quotas and availability are external. The worker/dashboard are not publicly hosted and the laptop must remain awake and connected for local actions.