"""
IncidentWorkflow - Temporal workflow definition for the Fixora incident lifecycle.

Steps (per the Fixora architecture diagram):
1. Build Context
2. Investigation Planning
3. Collect Evidence
4. RCA & Impact Analysis
5. Remediation Planning
6. Approval Gate (Wait)
7. Execute Actions
8. Validate Outcomes
9. Close / Rollback / Escalate

Triggered when human clicks Approve in the Fixora UI after fixora-rca-ai / OpenSRE
generates the initial RCA. The approval callback hits the orchestrator API which
starts this workflow.
"""

import logging
from datetime import timedelta
from typing import Any, Dict

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
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

logger = logging.getLogger(__name__)

ACTIVITY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=3,
)


@workflow.defn(name="IncidentWorkflow")
class IncidentWorkflow:
    """
    Temporal workflow that orchestrates the full 9-step incident lifecycle.
    Triggered by the human approval callback from the Fixora UI.
    """

    @workflow.run
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the 9-step incident lifecycle workflow."""
        incident_id = input_data["incident_id"]
        workflow.logger.info(f"Starting IncidentWorkflow for incident={incident_id}")

        result: Dict[str, Any] = {"incident_id": incident_id, "steps_completed": []}

        # Step 1: Build Context
        workflow.logger.info(f"[{incident_id}] Step 1: Build Context")
        context = await workflow.execute_activity(
            build_context,
            input_data,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        result["context"] = context
        result["steps_completed"].append("build_context")

        # Step 2: Investigation Planning
        workflow.logger.info(f"[{incident_id}] Step 2: Investigation Planning")
        investigation_plan = await workflow.execute_activity(
            investigation_planning,
            {**input_data, "context": context},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        result["investigation_plan"] = investigation_plan
        result["steps_completed"].append("investigation_planning")

        # Step 3: Collect Evidence
        workflow.logger.info(f"[{incident_id}] Step 3: Collect Evidence")
        evidence = await workflow.execute_activity(
            collect_evidence,
            {**input_data, "context": context, "investigation_plan": investigation_plan},
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        result["evidence"] = evidence
        result["steps_completed"].append("collect_evidence")

        # Step 4: RCA & Impact Analysis
        workflow.logger.info(f"[{incident_id}] Step 4: RCA & Impact Analysis")
        rca_result = await workflow.execute_activity(
            rca_and_impact_analysis,
            {**input_data, "context": context, "evidence": evidence},
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        result["rca_result"] = rca_result
        result["steps_completed"].append("rca_and_impact_analysis")

        # Step 5: Remediation Planning
        workflow.logger.info(f"[{incident_id}] Step 5: Remediation Planning")
        remediation_result = await workflow.execute_activity(
            remediation_planning,
            {**input_data, "context": context, "evidence": evidence, "rca_result": rca_result},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        result["remediation_result"] = remediation_result
        result["steps_completed"].append("remediation_planning")

        # Step 6: Approval Gate (Wait)
        workflow.logger.info(f"[{incident_id}] Step 6: Approval Gate")
        approval_status = await workflow.execute_activity(
            approval_gate,
            {**input_data, "remediation_result": remediation_result},
            start_to_close_timeout=timedelta(hours=24),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        result["approval_status"] = approval_status
        result["steps_completed"].append("approval_gate")

        # If rejected at the gate, escalate and close
        if approval_status.get("decision") == "rejected":
            workflow.logger.info(f"[{incident_id}] Approval rejected - escalating")
            result["final_status"] = "escalated"
            result["steps_completed"].append("close_rollback_or_escalate")
            return result

        # Step 7: Execute Actions (delegate to fixora-execution-orchestrator-agent)
        workflow.logger.info(f"[{incident_id}] Step 7: Execute Actions")
        execution_result = await workflow.execute_activity(
            execute_actions,
            {**input_data, "remediation_result": remediation_result},
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        result["execution_result"] = execution_result
        result["steps_completed"].append("execute_actions")

        # Step 8: Validate Outcomes (delegate to fixora-validation-orchestrator-agent)
        workflow.logger.info(f"[{incident_id}] Step 8: Validate Outcomes")
        validation_result = await workflow.execute_activity(
            validate_outcomes,
            {**input_data, "execution_result": execution_result},
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        result["validation_result"] = validation_result
        result["steps_completed"].append("validate_outcomes")

        # Step 9: Close / Rollback / Escalate
        workflow.logger.info(f"[{incident_id}] Step 9: Close / Rollback / Escalate")
        final_result = await workflow.execute_activity(
            close_rollback_or_escalate,
            {**input_data, "execution_result": execution_result, "validation_result": validation_result},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        result["final_status"] = final_result.get("status", "closed")
        result["steps_completed"].append("close_rollback_or_escalate")

        workflow.logger.info(f"[{incident_id}] Workflow completed with status={result['final_status']}")
        return result
