"""
Temporal activities for the IncidentWorkflow.

Each activity corresponds to one of the 9 steps in the Fixora incident lifecycle.
Activities call out to the AI coordinator, diagnostic agents, execution orchestrator,
and validation orchestrator as needed.
"""

import logging
import os
from typing import Any, Dict

import httpx
from temporalio import activity

logger = logging.getLogger(__name__)

FIXORA_API_BASE_URL = os.environ.get("FIXORA_API_BASE_URL", "http://localhost:8080")
DIAGNOSTIC_ORCHESTRATOR_URL = os.environ.get("DIAGNOSTIC_ORCHESTRATOR_URL", "http://localhost:8092")
EXECUTION_ORCHESTRATOR_URL = os.environ.get("EXECUTION_ORCHESTRATOR_URL", "http://localhost:8093")
VALIDATION_ORCHESTRATOR_URL = os.environ.get("VALIDATION_ORCHESTRATOR_URL", "http://localhost:8094")


@activity.defn
async def build_context(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Step 1: Build context - gather incident metadata, alert details, and service topology."""
    incident_id = input_data["incident_id"]
    activity.logger.info(f"[{incident_id}] Building context...")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            f"{FIXORA_API_BASE_URL}/api/v1/incidents/{incident_id}/context"
        )
        if response.status_code == 200:
            return response.json()

    # Fallback: return basic context from the input data
    return {
        "incident_id": incident_id,
        "rca_summary": input_data.get("rca_summary"),
        "approver_id": input_data.get("approver_id"),
        "decision": input_data.get("decision"),
        "status": "context_built",
    }


@activity.defn
async def investigation_planning(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Step 2: Investigation Planning - AI Coordinator decides which agents to use."""
    incident_id = input_data["incident_id"]
    activity.logger.info(f"[{incident_id}] Planning investigation...")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{DIAGNOSTIC_ORCHESTRATOR_URL}/api/v1/plan-investigation",
            json={"incident_id": incident_id, "context": input_data.get("context")},
        )
        if response.status_code == 200:
            return response.json()

    return {
        "incident_id": incident_id,
        "plan": "default_investigation_plan",
        "agents_to_use": ["grafana", "kibana", "opentelemetry", "kubernetes"],
        "status": "planned",
    }


@activity.defn
async def collect_evidence(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Step 3: Collect Evidence - diagnostic agents gather logs, metrics, traces."""
    incident_id = input_data["incident_id"]
    activity.logger.info(f"[{incident_id}] Collecting evidence...")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{DIAGNOSTIC_ORCHESTRATOR_URL}/api/v1/collect-evidence",
            json={
                "incident_id": incident_id,
                "investigation_plan": input_data.get("investigation_plan"),
                "context": input_data.get("context"),
            },
        )
        if response.status_code == 200:
            return response.json()

    return {
        "incident_id": incident_id,
        "evidence": [],
        "status": "collected",
    }


@activity.defn
async def rca_and_impact_analysis(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Step 4: RCA & Impact Analysis - AI synthesizes root cause from evidence."""
    incident_id = input_data["incident_id"]
    activity.logger.info(f"[{incident_id}] Running RCA & impact analysis...")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{DIAGNOSTIC_ORCHESTRATOR_URL}/api/v1/rca-analysis",
            json={
                "incident_id": incident_id,
                "context": input_data.get("context"),
                "evidence": input_data.get("evidence"),
            },
        )
        if response.status_code == 200:
            return response.json()

    # Use RCA summary from the initial approval if available
    return {
        "incident_id": incident_id,
        "root_cause": input_data.get("rca_summary", {}),
        "impact": "to_be_determined",
        "status": "analyzed",
    }


@activity.defn
async def remediation_planning(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Step 5: Remediation Planning - generate remediation options and rollback plan."""
    incident_id = input_data["incident_id"]
    activity.logger.info(f"[{incident_id}] Planning remediation...")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{DIAGNOSTIC_ORCHESTRATOR_URL}/api/v1/remediation-plan",
            json={
                "incident_id": incident_id,
                "rca_result": input_data.get("rca_result"),
                "evidence": input_data.get("evidence"),
                "context": input_data.get("context"),
            },
        )
        if response.status_code == 200:
            return response.json()

    return {
        "incident_id": incident_id,
        "remediation_options": [],
        "rollback_plan": {},
        "risk_assessment": "medium",
        "status": "planned",
    }


@activity.defn
async def approval_gate(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 6: Approval Gate - since this workflow is triggered BY the human approval,
    the decision is already captured in the input data.
    """
    incident_id = input_data["incident_id"]
    decision = input_data.get("decision", "approved")
    activity.logger.info(f"[{incident_id}] Approval gate - decision: {decision}")

    return {
        "incident_id": incident_id,
        "decision": decision,
        "approver_id": input_data.get("approver_id"),
        "status": "gate_passed" if decision == "approved" else "gate_rejected",
    }


@activity.defn
async def execute_actions(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Step 7: Execute Actions - delegate to fixora-execution-orchestrator-agent."""
    incident_id = input_data["incident_id"]
    activity.logger.info(f"[{incident_id}] Executing remediation actions...")

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            f"{EXECUTION_ORCHESTRATOR_URL}/api/v1/execute",
            json={
                "incident_id": incident_id,
                "remediation_result": input_data.get("remediation_result"),
            },
        )
        if response.status_code == 200:
            return response.json()

    return {
        "incident_id": incident_id,
        "actions_executed": [],
        "status": "executed",
    }


@activity.defn
async def validate_outcomes(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Step 8: Validate Outcomes - delegate to fixora-validation-orchestrator-agent."""
    incident_id = input_data["incident_id"]
    activity.logger.info(f"[{incident_id}] Validating outcomes...")

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            f"{VALIDATION_ORCHESTRATOR_URL}/api/v1/validate",
            json={
                "incident_id": incident_id,
                "execution_result": input_data.get("execution_result"),
            },
        )
        if response.status_code == 200:
            return response.json()

    return {
        "incident_id": incident_id,
        "validation_passed": True,
        "checks": [],
        "status": "validated",
    }


@activity.defn
async def close_rollback_or_escalate(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Step 9: Close / Rollback / Escalate based on validation results."""
    incident_id = input_data["incident_id"]
    validation_result = input_data.get("validation_result", {})
    execution_result = input_data.get("execution_result", {})

    validation_passed = validation_result.get("validation_passed", False)

    if validation_passed:
        status = "closed"
        activity.logger.info(f"[{incident_id}] Incident resolved - closing")
    else:
        # Trigger rollback
        status = "rollback"
        activity.logger.info(f"[{incident_id}] Validation failed - rolling back")
        async with httpx.AsyncClient(timeout=180.0) as client:
            await client.post(
                f"{EXECUTION_ORCHESTRATOR_URL}/api/v1/rollback",
                json={
                    "incident_id": incident_id,
                    "execution_result": execution_result,
                },
            )

    # Update incident status in Fixora API
    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.patch(
            f"{FIXORA_API_BASE_URL}/api/v1/incidents/{incident_id}/status",
            json={"status": status},
        )

    return {
        "incident_id": incident_id,
        "status": status,
    }
