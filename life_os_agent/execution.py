"""Deterministic action execution against Jira client."""

from __future__ import annotations

from dataclasses import dataclass

from .jira_client import JiraClient
from .models import ActionType, ExecutionResult, ProposedAction


@dataclass(slots=True)
class JiraExecutor:
    """Executes approved action proposals."""

    jira_client: JiraClient

    def execute(self, actions: list[ProposedAction]) -> list[ExecutionResult]:
        """Execute supported actions in order and return structured outcomes."""
        results: list[ExecutionResult] = []
        for action in actions:
            try:
                details = self._execute_single(action)
                results.append(ExecutionResult(action_type=action.type, success=True, details=details))
            except Exception as exc:  # noqa: BLE001
                results.append(
                    ExecutionResult(action_type=action.type, success=False, error=str(exc), details={})
                )
        return results

    def _execute_single(self, action: ProposedAction) -> dict:
        if action.type == ActionType.CREATE_ISSUE:
            return self.jira_client.create_issue(action.fields)
        if action.type == ActionType.UPDATE_ISSUE:
            if not action.issue_key:
                raise ValueError("update_issue requires issue_key")
            return self.jira_client.update_issue(action.issue_key, action.fields)
        if action.type == ActionType.TRANSITION_ISSUE:
            if not action.issue_key:
                raise ValueError("transition_issue requires issue_key")
            status = str(action.fields.get("status", "To Do"))
            return self.jira_client.transition_issue(action.issue_key, status)
        if action.type in {ActionType.SUMMARIZE, ActionType.FLAG_RISK}:
            return {"message": action.reason, "risk_flags": action.risk_flags}
        raise ValueError(f"Unsupported action type: {action.type}")
