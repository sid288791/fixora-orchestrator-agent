"""
Fixora Orchestrator Agent - main Temporal workflow orchestrator.

Owns the end-to-end incident lifecycle as a Temporal workflow: build context,
plan investigation, collect evidence, run RCA & impact analysis, plan
remediation, wait for the human approval gate, execute actions (delegating to
fixora-execution-orchestrator-agent), validate outcomes (delegating to
fixora-validation-orchestrator-agent), then close/rollback/escalate.

This is a skeleton only - workflow/activity logic to be added later.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

APP_DIR = Path(__file__).parent
load_dotenv(APP_DIR / ".env")

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8091"))

SERVICE_NAME = "fixora-orchestrator-agent"

app = FastAPI(title=SERVICE_NAME, version="0.1.0")


@app.get("/healthcheck")
def healthcheck():
    return {"status": "ok", "service": SERVICE_NAME, "version": "0.1.0"}


@app.get("/")
def root():
    return {
        "service": SERVICE_NAME,
        "version": "0.1.0",
        "description": "Main Temporal workflow orchestrator for the Fixora incident lifecycle",
        "endpoints": ["/healthcheck"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
