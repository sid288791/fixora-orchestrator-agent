"""
AICoordinator - decides what to investigate, which diagnostic agents to use,
correlates evidence, and generates RCA & remediation options.

TODO: implement with LangGraph / LLM-driven orchestration.
"""


class AICoordinator:
    """Placeholder for the AI Coordinator implementation."""

    def plan_investigation(self, context: dict) -> dict:
        raise NotImplementedError

    def correlate_evidence(self, evidence: list) -> dict:
        raise NotImplementedError
