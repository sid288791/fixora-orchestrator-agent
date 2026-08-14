"""Pydantic models for incident context passed through the workflow."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IncidentContext(BaseModel):
    """Context object that flows through the 9-step Temporal workflow."""

    incident_id: str
    decision: str
    approver_id: str
    approver_email: Optional[str] = None
    ad_grp: Optional[str] = None
    rca_summary: Optional[Dict[str, Any]] = None
    remediation_plan: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None

    # Populated during workflow execution
    context: Optional[Dict[str, Any]] = Field(default=None, description="Step 1: Built context")
    investigation_plan: Optional[Dict[str, Any]] = Field(
        default=None, description="Step 2: Investigation plan"
    )
    evidence: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Step 3: Collected evidence"
    )
    rca_result: Optional[Dict[str, Any]] = Field(
        default=None, description="Step 4: RCA & impact analysis result"
    )
    remediation_result: Optional[Dict[str, Any]] = Field(
        default=None, description="Step 5: Remediation planning result"
    )
    approval_status: Optional[str] = Field(
        default=None, description="Step 6: Approval gate status"
    )
    execution_result: Optional[Dict[str, Any]] = Field(
        default=None, description="Step 7: Execution actions result"
    )
    validation_result: Optional[Dict[str, Any]] = Field(
        default=None, description="Step 8: Validation outcomes result"
    )
    final_status: Optional[str] = Field(
        default=None, description="Step 9: Close/Rollback/Escalate status"
    )
