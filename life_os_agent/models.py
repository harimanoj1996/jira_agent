"""Core data models for the Life OS Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InputSource(str, Enum):
    """Supported user input origins."""

    TEXT = "text"
    VOICE = "voice"


class ActionType(str, Enum):
    """Supported Jira decision-support action types."""

    CREATE_ISSUE = "create_issue"
    UPDATE_ISSUE = "update_issue"
    TRANSITION_ISSUE = "transition_issue"
    SUMMARIZE = "summarize"
    FLAG_RISK = "flag_risk"


@dataclass(slots=True)
class UserInput:
    """Normalized input payload from any channel."""

    text: str
    source: InputSource
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class JiraContext:
    """Context used to ground LLM reasoning."""

    issue_details: dict[str, Any] = field(default_factory=dict)
    workload_summary: dict[str, Any] = field(default_factory=dict)
    recent_activity: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ProposedAction:
    """Strict action proposal produced by the LLM module."""

    type: ActionType
    issue_key: str | None
    fields: dict[str, Any]
    reason: str
    confidence: float
    risk_flags: list[str]


@dataclass(slots=True)
class LLMDecision:
    """Strict LLM output envelope."""

    intent: str
    summary: str
    proposed_actions: list[ProposedAction]
    requires_confirmation: bool
    confidence: float


@dataclass(slots=True)
class ValidationDecision:
    """Result of deterministic safety and policy checks."""

    is_valid: bool
    requires_confirmation: bool
    blocked_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConfirmationResult:
    """Human confirmation response."""

    approved: bool
    edited_actions: list[ProposedAction] | None = None
    reviewer_note: str | None = None


@dataclass(slots=True)
class ExecutionResult:
    """Execution outcome for a single action."""

    action_type: ActionType
    success: bool
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
