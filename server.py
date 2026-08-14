"""
Fixora Orchestrator Agent - main Temporal workflow orchestrator.

Owns the end-to-end incident lifecycle as a Temporal workflow: build context,
plan investigation, collect evidence, run RCA & impact analysis, plan
remediation, wait for the human approval gate, execute actions (delegating to
fixora-execution-orchestrator-agent), validate outcomes (delegating to
fixora-validation-orchestrator-agent), then close/rollback/escalate.

The workflow is triggered when the human clicks "Approve" in the Fixora UI
after fixora-rca-ai / OpenSRE generates the initial RCA.
"""
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from temporalio.client import Client as TemporalClient

from models import HumanApprovalRequest, HumanApprovalResponse, ApprovalDecision
from workflows.incident_workflow import IncidentWorkflow

APP_DIR = Path(__file__).parent
load_dotenv(APP_DIR / ".env")

logger = logging.getLogger(__name__)

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8091"))

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")
TEMPORAL_TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "fixora-orchestrator-task-queue")

SERVICE_NAME = "fixora-orchestrator-agent"

temporal_client: Optional[TemporalClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to Temporal on startup, disconnect on shutdown."""
    global temporal_client
    try:
        temporal_client = await TemporalClient.connect(
            TEMPORAL_HOST, namespace=TEMPORAL_NAMESPACE
        )
        logger.info(f"Connected to Temporal at {TEMPORAL_HOST}")
    except Exception as e:
        logger.warning(f"Failed to connect to Temporal: {e}. Workflow triggers will fail.")
        temporal_client = None
    yield
    temporal_client = None


app = FastAPI(title=SERVICE_NAME, version="0.1.0", lifespan=lifespan)


@app.get("/healthcheck")
def healthcheck():
    return {"status": "ok", "service": SERVICE_NAME, "version": "0.1.0"}


@app.post("/api/v1/human-approval", response_model=HumanApprovalResponse)
async def human_approval(request: HumanApprovalRequest):
    """
    API endpoint called when the human clicks Approve/Reject in the Fixora UI.

    This triggers the full 9-step Temporal incident lifecycle workflow:
    1. Build Context
    2. Investigation Planning
    3. Collect Evidence
    4. RCA & Impact Analysis
    5. Remediation Planning
    6. Approval Gate (Wait)
    7. Execute Actions
    8. Validate Outcomes
    9. Close / Rollback / Escalate
    """
    if temporal_client is None:
        raise HTTPException(
            status_code=503,
            detail="Temporal client not connected. Cannot start workflow.",
        )

    workflow_id = f"incident-{request.incident_id}-{uuid.uuid4().hex[:8]}"

    input_data = {
        "incident_id": request.incident_id,
        "decision": request.decision.value,
        "approver_id": request.approver_id,
        "approver_email": request.approver_email,
        "ad_grp": request.ad_grp,
        "rca_summary": request.rca_summary,
        "remediation_plan": request.remediation_plan,
        "notes": request.notes,
    }

    try:
        handle = await temporal_client.start_workflow(
            IncidentWorkflow.run,
            input_data,
            id=workflow_id,
            task_queue=TEMPORAL_TASK_QUEUE,
        )
        logger.info(
            f"Started IncidentWorkflow for incident={request.incident_id}, "
            f"workflow_id={workflow_id}, run_id={handle.result_run_id}"
        )
    except Exception as e:
        logger.error(f"Failed to start workflow: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")

    status = "workflow_started"
    if request.decision == ApprovalDecision.REJECTED:
        status = "rejected_escalating"

    return HumanApprovalResponse(
        incident_id=request.incident_id,
        workflow_run_id=handle.result_run_id,
        status=status,
        message=f"Incident lifecycle workflow triggered successfully. Workflow ID: {workflow_id}",
    )


@app.get("/api/v1/workflow-status/{incident_id}")
async def get_workflow_status(incident_id: str):
    """Check the status of a running incident workflow."""
    if temporal_client is None:
        raise HTTPException(status_code=503, detail="Temporal client not connected.")

    try:
        handle = temporal_client.get_workflow_handle(f"incident-{incident_id}")
        desc = await handle.describe()
        return {
            "incident_id": incident_id,
            "workflow_id": desc.id,
            "run_id": desc.run_id,
            "status": desc.status.name if desc.status else "UNKNOWN",
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {str(e)}")


@app.get("/")
def root():
    return {
        "service": SERVICE_NAME,
        "version": "0.1.0",
        "description": "Main Temporal workflow orchestrator for the Fixora incident lifecycle",
        "endpoints": [
            "/healthcheck",
            "/api/v1/human-approval",
            "/api/v1/workflow-status/{incident_id}",
        ],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
