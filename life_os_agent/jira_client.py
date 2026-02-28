"""Deterministic Jira REST wrapper with retry logic."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class JiraClientConfig:
    """Configuration for Jira connection and retry behavior."""

    base_url: str = "https://example.atlassian.net"
    email: str = "agent@example.com"
    api_token: str = "dummy-token"
    max_retries: int = 3
    backoff_seconds: float = 0.2


@dataclass(slots=True)
class JiraClient:
    """API wrapper. v1 uses in-memory store; swap _request for real REST in production."""

    config: JiraClientConfig
    _issues: dict[str, dict[str, Any]] = field(default_factory=dict)
    _activity: list[dict[str, Any]] = field(default_factory=list)

    def get_issue(self, issue_key: str) -> dict[str, Any] | None:
        """Fetch issue details by key."""
        return self._issues.get(issue_key)

    def get_workload_summary(self) -> dict[str, Any]:
        """Return simple workload snapshot."""
        open_count = sum(1 for issue in self._issues.values() if issue.get("status") != "Done")
        return {"open_issues": open_count, "total_issues": len(self._issues)}

    def get_recent_activity(self) -> list[dict[str, Any]]:
        """Return latest activity events."""
        return self._activity[-10:]

    def create_issue(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Create issue via deterministic retry wrapper."""
        return self._with_retry("create_issue", lambda: self._create_issue_impl(fields))

    def update_issue(self, issue_key: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Update issue fields."""
        return self._with_retry(
            "update_issue", lambda: self._update_issue_impl(issue_key=issue_key, fields=fields)
        )

    def transition_issue(self, issue_key: str, status: str) -> dict[str, Any]:
        """Transition issue status."""
        return self._with_retry(
            "transition_issue",
            lambda: self._transition_issue_impl(issue_key=issue_key, status=status),
        )

    def _with_retry(self, op_name: str, operation: Any) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                result = operation()
                logger.info("jira_op_success", extra={"op": op_name, "attempt": attempt})
                return result
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "jira_op_retry",
                    extra={"op": op_name, "attempt": attempt, "error": str(exc)},
                )
                time.sleep(self.config.backoff_seconds * attempt)
        raise RuntimeError(f"Jira operation failed: {op_name}") from last_exc

    def _create_issue_impl(self, fields: dict[str, Any]) -> dict[str, Any]:
        key = f"LIFE-{len(self._issues) + 1}"
        issue = {"key": key, "status": "To Do", **fields}
        self._issues[key] = issue
        self._activity.append({"event": "create", "issue_key": key})
        return issue

    def _update_issue_impl(self, issue_key: str, fields: dict[str, Any]) -> dict[str, Any]:
        if issue_key not in self._issues:
            raise KeyError(f"Issue not found: {issue_key}")
        self._issues[issue_key].update(fields)
        self._activity.append({"event": "update", "issue_key": issue_key, "fields": fields})
        return self._issues[issue_key]

    def _transition_issue_impl(self, issue_key: str, status: str) -> dict[str, Any]:
        if issue_key not in self._issues:
            raise KeyError(f"Issue not found: {issue_key}")
        self._issues[issue_key]["status"] = status
        self._activity.append({"event": "transition", "issue_key": issue_key, "status": status})
        return self._issues[issue_key]
