"""Jira context gathering module."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .jira_client import JiraClient
from .models import JiraContext, UserInput

ISSUE_KEY_PATTERN = re.compile(r"\b[A-Z]{2,10}-\d+\b")


@dataclass(slots=True)
class ContextBuilder:
    """Builds contextual information for LLM grounding."""

    jira_client: JiraClient

    def build(self, user_input: UserInput) -> JiraContext:
        """Collect issue details, workload summary, and recent activity."""
        issue_details: dict[str, dict] = {}
        for issue_key in set(ISSUE_KEY_PATTERN.findall(user_input.text)):
            issue = self.jira_client.get_issue(issue_key)
            if issue:
                issue_details[issue_key] = issue

        return JiraContext(
            issue_details=issue_details,
            workload_summary=self.jira_client.get_workload_summary(),
            recent_activity=self.jira_client.get_recent_activity(),
        )
