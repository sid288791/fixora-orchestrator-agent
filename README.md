# fixora-orchestrator-agent

Main Temporal workflow orchestrator for the Fixora incident lifecycle. Coordinates the
end-to-end flow: Build Context -> Investigation Planning -> Collect Evidence -> RCA &
Impact Analysis -> Remediation Planning -> Approval Gate (Wait) -> Execute Actions ->
Validate Outcomes -> Close / Rollback / Escalate.

Delegates diagnostics, execution, and validation to the sibling orchestrator agents:

- `fixora-diagnostic-orchestrator-agent`
- `fixora-execution-orchestrator-agent`
- `fixora-validation-orchestrator-agent`

This is currently a basic project skeleton - workflow/activity logic and AI
coordinator behavior will be added later.

## Layout

```
server.py                              # FastAPI app entrypoint (healthcheck for now)
workflows/incident_workflow.py         # Temporal workflow step placeholders
ai_coordinator/coordinator.py          # AI Coordinator (LangGraph/LLM) placeholder
ai_coordinator/rca_synthesis_agent.py  # RCA Synthesis Agent placeholder
ai_coordinator/remediation_planner_agent.py  # Remediation Planner Agent placeholder
```

## Setup

```bash
cd fixora-orchestrator-agent
python -m venv .venv

# Windows (Git Bash)
./.venv/Scripts/python.exe -m pip install -r requirements.txt
# macOS/Linux
source .venv/bin/activate && pip install -r requirements.txt

cp .env.example .env
# edit .env with real values (Temporal host, downstream orchestrator URLs, LLM key)
```

## Run

```bash
python -m uvicorn server:app --host 0.0.0.0 --port 8091
```

Verify: `curl http://localhost:8091/healthcheck` -> `{"status":"ok"}`
