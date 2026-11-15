# Jarvis Agent Collaboration Protocol
- Manager owns the user request and final synthesis.
- Specialist agents only work within their specialty and return explicit results/limitations.
- Handoffs are logged as agent_handoff events; completed outputs are logged as agent_message events.
- Use shared context passed by manager; do not assume private memory of other agents.
- Browser and Computer agents must not claim to have executed actions in this MVP.
- Any future machine-action tool must require user approval for destructive, financial, credential, or external-send actions.
- Validate outputs and report uncertainty; never fabricate web citations or execution evidence.
