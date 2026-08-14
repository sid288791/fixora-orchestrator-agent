"""Pydantic models for the Human Approval API."""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class HumanApprovalRequest(BaseModel):
    """Payload received when a human clicks the Approve/Reject button in the Fixora UI."""

    incident_id: str = Field(..., description="Unique incident identifier")
    decision: ApprovalDecision = Field(..., description="Human decision: approved or rejected")
    approver_id: str = Field(..., description="ID of the human approver")
    approver_email: Optional[str] = Field(None, description="Email of the approver")
    ad_grp: Optional[str] = Field(None, description="AD group of the approver for RBAC")
    rca_summary: Optional[Dict[str, Any]] = Field(
        None, description="RCA summary from fixora-rca-ai / OpenSRE"
    )
    remediation_plan: Optional[Dict[str, Any]] = Field(
        None, description="Proposed remediation plan to approve/reject"
    )
    notes: Optional[str] = Field(None, description="Optional notes from the approver")


class HumanApprovalResponse(BaseModel):
    """Response returned after the approval is processed."""

    incident_id: str
    workflow_run_id: str = Field(..., description="Temporal workflow run ID")
    status: str = Field(..., description="Current status of the workflow")
    message: str
