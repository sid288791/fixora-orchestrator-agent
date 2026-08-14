"""
Temporal worker for the Fixora Orchestrator Agent.

Runs the IncidentWorkflow and its activities. Start this alongside server.py
so that workflows triggered by the API can be executed.

Usage:
    python worker.py
"""

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from temporalio.client import Client as TemporalClient
from temporalio.worker import Worker

from workflows.incident_workflow import IncidentWorkflow
from workflows.activities import (
    build_context,
    investigation_planning,
    collect_evidence,
    rca_and_impact_analysis,
    remediation_planning,
    approval_gate,
    execute_actions,
    validate_outcomes,
    close_rollback_or_escalate,
)

APP_DIR = Path(__file__).parent
load_dotenv(APP_DIR / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")
TEMPORAL_TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "fixora-orchestrator-task-queue")


async def main():
    """Start the Temporal worker."""
    logger.info(f"Connecting to Temporal at {TEMPORAL_HOST}...")
    client = await TemporalClient.connect(TEMPORAL_HOST, namespace=TEMPORAL_NAMESPACE)

    worker = Worker(
        client,
        task_queue=TEMPORAL_TASK_QUEUE,
        workflows=[IncidentWorkflow],
        activities=[
            build_context,
            investigation_planning,
            collect_evidence,
            rca_and_impact_analysis,
            remediation_planning,
            approval_gate,
            execute_actions,
            validate_outcomes,
            close_rollback_or_escalate,
        ],
    )

    logger.info(f"Worker started on task queue: {TEMPORAL_TASK_QUEUE}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
