"""LLM reasoning abstraction and strict output parsing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from .models import ActionType, JiraContext, LLMDecision, ProposedAction, UserInput


class LLMGateway(Protocol):
    """Protocol for pluggable model providers."""

    def complete(self, prompt: str) -> str:
        """Return raw model output text."""


@dataclass(slots=True)
class MockLLMGateway:
    """Deterministic mock used for local development and tests."""

    def complete(self, prompt: str) -> str:
        """Return a fixed schema-compliant JSON payload."""
        del prompt
        return json.dumps(
            {
                "intent": "daily_summary",
                "summary": "User requested a planning summary.",
                "proposed_actions": [
                    {
                        "type": "summarize",
                        "issue_key": None,
                        "fields": {},
                        "reason": "Provide concise workload status.",
                        "confidence": 0.95,
                        "risk_flags": [],
                    }
                ],
                "requires_confirmation": False,
                "confidence": 0.95,
            }
        )


@dataclass(slots=True)
class LLMReasoner:
    """Produces structured suggestions while delegating control to policy layers."""

    gateway: LLMGateway

    def reason(self, user_input: UserInput, context: JiraContext) -> LLMDecision:
        """Generate and parse strict schema output from the LLM."""
        prompt = self._build_prompt(user_input, context)
        raw_output = self.gateway.complete(prompt)
        return self._parse_decision(raw_output)

    def _build_prompt(self, user_input: UserInput, context: JiraContext) -> str:
        return (
            "You are a Jira decision-support model. Output ONLY JSON matching schema."
            f"\nUser input: {user_input.text}"
            f"\nInput source: {user_input.source.value}, confidence={user_input.confidence}"
            f"\nIssue details: {context.issue_details}"
            f"\nWorkload summary: {context.workload_summary}"
            f"\nRecent activity: {context.recent_activity}"
        )

    def _parse_decision(self, raw_output: str) -> LLMDecision:
        payload = json.loads(raw_output)
        required_keys = {
            "intent",
            "summary",
            "proposed_actions",
            "requires_confirmation",
            "confidence",
        }
        missing = required_keys.difference(payload)
        if missing:
            raise ValueError(f"LLM output missing required fields: {sorted(missing)}")

        actions: list[ProposedAction] = []
        for action in payload["proposed_actions"]:
            actions.append(
                ProposedAction(
                    type=ActionType(action["type"]),
                    issue_key=action.get("issue_key"),
                    fields=action.get("fields", {}),
                    reason=action["reason"],
                    confidence=float(action["confidence"]),
                    risk_flags=list(action.get("risk_flags", [])),
                )
            )

        return LLMDecision(
            intent=str(payload["intent"]),
            summary=str(payload["summary"]),
            proposed_actions=actions,
            requires_confirmation=bool(payload["requires_confirmation"]),
            confidence=float(payload["confidence"]),
        )
