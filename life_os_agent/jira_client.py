"""Deterministic Jira wrapper with optional Atlassian Cloud REST mode."""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib import error, parse, request

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class JiraClientConfig:
    """Configuration for Jira connection and retry behavior."""

    mode: str = "mock"  # `mock` or `active`
    base_url: str = "https://example.atlassian.net"
    email: str = "agent@example.com"
    api_token: str = "dummy-token"
    project_key: str = "LIFE"
    account_id: str = ""
    max_retries: int = 3
    backoff_seconds: float = 0.2


@dataclass(slots=True)
class JiraClient:
    """Jira client with in-memory mock mode and active REST mode."""

    config: JiraClientConfig
    _issues: dict[str, dict[str, Any]] = field(default_factory=dict)
    _activity: list[dict[str, Any]] = field(default_factory=list)

    def get_issue(self, issue_key: str) -> dict[str, Any] | None:
        """Fetch issue details by key."""
        if self._is_active:
            try:
                return self._with_retry(
                    "get_issue",
                    lambda: self._request_json("GET", f"/rest/api/3/issue/{issue_key}"),
                )
            except RuntimeError:
                return None
        return self._issues.get(issue_key)

    def get_workload_summary(self) -> dict[str, Any]:
        """Return workload snapshot from Jira or local mock."""
        if self._is_active:
            query = parse.urlencode(
                {
                    "jql": f"assignee = currentUser() AND project = {self.config.project_key} ORDER BY updated DESC",
                    "maxResults": 50,
                    "fields": "status,priority,duedate,updated,summary",
                }
            )
            data = self._with_retry(
                "get_workload_summary",
                lambda: self._request_json("GET", f"/rest/api/3/search/jql?{query}"),
            )
            issues = data.get("issues", [])
            return self._summarize_issues(issues=issues, source="atlassian_cloud")

        issues = [
            {
                "key": key,
                "fields": {
                    "status": {"name": value.get("status", "To Do")},
                    "priority": {"name": value.get("priority", "Medium")},
                    "duedate": value.get("duedate"),
                    "updated": value.get("updated"),
                    "summary": value.get("summary", ""),
                },
            }
            for key, value in self._issues.items()
        ]
        return self._summarize_issues(issues=issues, source="mock")

    def get_recent_activity(self) -> list[dict[str, Any]]:
        """Return recent activity events."""
        if self._is_active:
            query = parse.urlencode(
                {
                    "jql": f"project = {self.config.project_key} ORDER BY updated DESC",
                    "maxResults": 5,
                    "fields": "status,updated,summary",
                }
            )
            data = self._with_retry(
                "get_recent_activity",
                lambda: self._request_json("GET", f"/rest/api/3/search/jql?{query}"),
            )
            return [
                {
                    "event": "issue_recently_updated",
                    "issue_key": issue.get("key"),
                    "summary": issue.get("fields", {}).get("summary"),
                    "status": issue.get("fields", {}).get("status", {}).get("name"),
                    "updated": issue.get("fields", {}).get("updated"),
                }
                for issue in data.get("issues", [])
            ]
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

    def check_connection(self) -> dict[str, Any]:
        """Validate Jira connectivity and authentication."""
        if not self._is_active:
            return {"ok": True, "mode": "mock", "message": "Mock mode active"}
        user = self._with_retry("check_connection", lambda: self._request_json("GET", "/rest/api/3/myself"))
        return {
            "ok": True,
            "mode": "active",
            "site": self.config.base_url,
            "accountId": user.get("accountId"),
            "displayName": user.get("displayName"),
        }

    @property
    def _is_active(self) -> bool:
        return self.config.mode.strip().lower() == "active"

    def _with_retry(self, op_name: str, operation: Any) -> Any:
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

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.config.email or not self.config.api_token:
            raise RuntimeError("Active Jira mode requires email and api_token in JiraClientConfig")

        token = f"{self.config.email}:{self.config.api_token}".encode("utf-8")
        auth = base64.b64encode(token).decode("ascii")

        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        req = request.Request(
            url=f"{self.config.base_url.rstrip('/')}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Basic {auth}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Jira HTTP error {exc.code}: {details}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Jira connection failed: {exc}") from exc

    def _create_issue_impl(self, fields: dict[str, Any]) -> dict[str, Any]:
        if self._is_active:
            payload = {
                "fields": {
                    "project": {"key": self.config.project_key},
                    **fields,
                }
            }
            return self._request_json("POST", "/rest/api/3/issue", payload=payload)

        key = f"LIFE-{len(self._issues) + 1}"
        issue = {"key": key, "status": "To Do", **fields}
        self._issues[key] = issue
        self._activity.append({"event": "create", "issue_key": key})
        return issue

    def _update_issue_impl(self, issue_key: str, fields: dict[str, Any]) -> dict[str, Any]:
        if self._is_active:
            self._request_json("PUT", f"/rest/api/3/issue/{issue_key}", payload={"fields": fields})
            refreshed = self._request_json("GET", f"/rest/api/3/issue/{issue_key}")
            return refreshed

        if issue_key not in self._issues:
            raise KeyError(f"Issue not found: {issue_key}")
        self._issues[issue_key].update(fields)
        self._activity.append({"event": "update", "issue_key": issue_key, "fields": fields})
        return self._issues[issue_key]

    def _transition_issue_impl(self, issue_key: str, status: str) -> dict[str, Any]:
        if self._is_active:
            transitions = self._request_json("GET", f"/rest/api/3/issue/{issue_key}/transitions")
            transition_id = None
            for transition in transitions.get("transitions", []):
                if transition.get("name", "").lower() == status.lower():
                    transition_id = transition.get("id")
                    break
            if not transition_id:
                available = [t.get("name") for t in transitions.get("transitions", [])]
                raise RuntimeError(
                    f"Transition '{status}' not found for {issue_key}. Available: {available}"
                )
            self._request_json(
                "POST",
                f"/rest/api/3/issue/{issue_key}/transitions",
                payload={"transition": {"id": transition_id}},
            )
            return self._request_json("GET", f"/rest/api/3/issue/{issue_key}")

        if issue_key not in self._issues:
            raise KeyError(f"Issue not found: {issue_key}")
        self._issues[issue_key]["status"] = status
        self._activity.append({"event": "transition", "issue_key": issue_key, "status": status})
        return self._issues[issue_key]

    def _summarize_issues(self, issues: list[dict[str, Any]], source: str) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        priority_counts: dict[str, int] = {}
        overdue_issues: list[str] = []
        high_priority_open: list[str] = []

        today = date.today()
        for issue in issues:
            key = issue.get("key", "UNKNOWN")
            fields = issue.get("fields", {})

            status = fields.get("status", {}).get("name", "Unknown")
            priority = fields.get("priority", {}).get("name", "Unknown")
            due_date = fields.get("duedate")

            status_counts[status] = status_counts.get(status, 0) + 1
            priority_counts[priority] = priority_counts.get(priority, 0) + 1

            is_open = status not in {"Done", "Closed"}
            if is_open and priority in {"Highest", "High", "Critical", "Blocker"}:
                high_priority_open.append(key)

            if due_date and is_open:
                try:
                    if date.fromisoformat(due_date) < today:
                        overdue_issues.append(key)
                except ValueError:
                    pass

        total_issues = len(issues)
        open_issues = total_issues - status_counts.get("Done", 0) - status_counts.get("Closed", 0)

        return {
            "open_issues": open_issues,
            "total_issues": total_issues,
            "source": source,
            "status_counts": status_counts,
            "priority_counts": priority_counts,
            "overdue_count": len(overdue_issues),
            "overdue_issue_keys": overdue_issues[:5],
            "high_priority_open_count": len(high_priority_open),
            "high_priority_open_keys": high_priority_open[:5],
        }
