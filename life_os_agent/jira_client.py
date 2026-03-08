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
    board_id: int = 1
    sprint_limit: int = 10
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
        """Return sprint-oriented workload snapshot for LLM grounding."""
        if self._is_active:
            return self._build_sprint_summary_active()
        return self._build_sprint_summary_mock()

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

    def _build_sprint_summary_active(self) -> dict[str, Any]:
        sprints = self._paginate(
            path=f"/rest/agile/1.0/board/{self.config.board_id}/sprint?state=active,closed,future",
            items_key="values",
        )
        selected_sprints = sprints[: self.config.sprint_limit]

        sprint_payload: dict[str, dict[str, dict[str, Any]]] = {}
        sprint_metrics: dict[str, dict[str, Any]] = {}
        all_blockers: list[dict[str, Any]] = []
        alerts: list[str] = []

        for sprint in selected_sprints:
            sprint_id = sprint.get("id")
            sprint_name = sprint.get("name", f"Sprint-{sprint_id}")
            issues = self._paginate(
                path=(
                    f"/rest/agile/1.0/sprint/{sprint_id}/issue?"
                    "fields=summary,status,priority,assignee,duedate"
                ),
                items_key="issues",
            )

            sprint_tasks: dict[str, dict[str, Any]] = {}
            done_count = 0
            backlog_count = 0
            in_progress_count = 0
            blocked_count = 0

            for issue in issues:
                key = issue.get("key", "UNKNOWN")
                fields = issue.get("fields", {})
                status_name = fields.get("status", {}).get("name", "Unknown")
                priority_name = (fields.get("priority") or {}).get("name")
                assignee_name = (fields.get("assignee") or {}).get("displayName")
                due_date = fields.get("duedate")

                sprint_tasks[key] = {
                    "summary": fields.get("summary"),
                    "status": status_name,
                    "priority": priority_name,
                    "assignee": assignee_name,
                    "duedate": due_date,
                }

                status_lower = status_name.lower()
                if status_lower in {"done", "closed"}:
                    done_count += 1
                elif status_lower in {"to do", "backlog", "selected for development", "open"}:
                    backlog_count += 1
                else:
                    in_progress_count += 1

                is_blocked = status_lower in {"blocked", "impediment"}
                if is_blocked:
                    blocked_count += 1
                    all_blockers.append({"sprint": sprint_name, "issue_key": key, "status": status_name})

                is_open = status_lower not in {"done", "closed"}
                if due_date and is_open:
                    try:
                        if date.fromisoformat(due_date) < date.today():
                            alerts.append(f"Overdue issue in {sprint_name}: {key}")
                    except ValueError:
                        pass
                if is_open and priority_name in {"Highest", "High", "Critical", "Blocker"} and not assignee_name:
                    alerts.append(f"Unassigned high-priority issue in {sprint_name}: {key}")

            total = len(issues)
            completion_rate = round((done_count / total), 3) if total else 0.0
            sprint_metrics[sprint_name] = {
                "total_issues": total,
                "done": done_count,
                "backlog": backlog_count,
                "in_progress": in_progress_count,
                "blocked": blocked_count,
                "completion_rate": completion_rate,
                "state": sprint.get("state"),
                "startDate": sprint.get("startDate"),
                "endDate": sprint.get("endDate"),
            }
            sprint_payload[sprint_name] = sprint_tasks

        closed_velocities = [
            item["done"]
            for item in sprint_metrics.values()
            if str(item.get("state", "")).lower() == "closed"
        ]
        average_velocity = round(sum(closed_velocities) / len(closed_velocities), 2) if closed_velocities else 0.0

        return {
            "source": "atlassian_cloud",
            "board_id": self.config.board_id,
            "sprints": sprint_payload,
            "sprint_metrics": sprint_metrics,
            "velocity": {
                "closed_sprint_count": len(closed_velocities),
                "average_done_per_closed_sprint": average_velocity,
                "last_closed_sprint_done": closed_velocities[-1] if closed_velocities else 0,
            },
            "blockers": all_blockers,
            "alerts": alerts[:20],
        }

    def _build_sprint_summary_mock(self) -> dict[str, Any]:
        sprint_name = "Sprint Mock"
        sprint_tasks: dict[str, dict[str, Any]] = {}
        done_count = 0

        for key, value in self._issues.items():
            status = value.get("status", "To Do")
            sprint_tasks[key] = {
                "summary": value.get("summary"),
                "status": status,
                "priority": value.get("priority"),
                "assignee": value.get("assignee"),
                "duedate": value.get("duedate"),
            }
            if str(status).lower() in {"done", "closed"}:
                done_count += 1

        total = len(sprint_tasks)
        backlog = sum(
            1
            for item in sprint_tasks.values()
            if str(item.get("status", "")).lower() in {"to do", "backlog", "open"}
        )
        in_progress = max(total - done_count - backlog, 0)

        return {
            "source": "mock",
            "board_id": self.config.board_id,
            "sprints": {sprint_name: sprint_tasks},
            "sprint_metrics": {
                sprint_name: {
                    "total_issues": total,
                    "done": done_count,
                    "backlog": backlog,
                    "in_progress": in_progress,
                    "blocked": 0,
                    "completion_rate": round((done_count / total), 3) if total else 0.0,
                    "state": "active",
                }
            },
            "velocity": {
                "closed_sprint_count": 0,
                "average_done_per_closed_sprint": 0.0,
                "last_closed_sprint_done": 0,
            },
            "blockers": [],
            "alerts": [],
        }

    def _paginate(self, path: str, items_key: str) -> list[dict[str, Any]]:
        """Fetch paginated Jira endpoints that use startAt/maxResults/total."""
        items: list[dict[str, Any]] = []
        start_at = 0

        while True:
            separator = "&" if "?" in path else "?"
            page = self._request_json("GET", f"{path}{separator}startAt={start_at}&maxResults=50")
            batch = page.get(items_key, [])
            if not isinstance(batch, list):
                break
            items.extend(batch)

            returned = len(batch)
            total = int(page.get("total", returned))
            if returned == 0:
                break
            start_at += returned
            if start_at >= total:
                break
        return items

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
