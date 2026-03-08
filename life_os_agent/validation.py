"""Deterministic validation and safety policy engine."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import ActionType, InputSource, LLMDecision, UserInput, ValidationDecision


@dataclass(slots=True)
class PolicyConfig:
    """Policy thresholds and operational guardrails."""

    min_confidence_text: float = 0.70
    min_confidence_voice: float = 0.85
    forbidden_action_types: set[ActionType] = field(default_factory=set)
    confirm_action_types: set[ActionType] = field(
        default_factory=lambda: {ActionType.CREATE_ISSUE, ActionType.TRANSITION_ISSUE}
    )
    high_risk_flags: set[str] = field(
        default_factory=lambda: {"deadline_change", "overload_risk", "unclear_intent"}
    )


@dataclass(slots=True)
class ValidationEngine:
    """Applies deterministic checks to LLM proposals."""

    config: PolicyConfig

    def validate(self, user_input: UserInput, decision: LLMDecision) -> ValidationDecision:
        """Validate confidence, schema details, risk flags, and confirmation policy."""
        blocked_reasons: list[str] = []
        warnings: list[str] = []
        requires_confirmation = decision.requires_confirmation

        threshold = (
            self.config.min_confidence_voice
            if user_input.source == InputSource.VOICE
            else self.config.min_confidence_text
        )
        if decision.confidence < threshold:
            blocked_reasons.append(
                f"Decision confidence {decision.confidence:.2f} below threshold {threshold:.2f}."
            )

        for action in decision.proposed_actions:
            if action.type in self.config.forbidden_action_types:
                blocked_reasons.append(f"Forbidden action type: {action.type.value}")

            if action.confidence < threshold:
                blocked_reasons.append(
                    f"Action confidence for {action.type.value} below threshold {threshold:.2f}."
                )

            if action.type == ActionType.CREATE_ISSUE:
                if "summary" not in action.fields:
                    blocked_reasons.append("create_issue action missing required field: summary")

            if action.type in self.config.confirm_action_types:
                requires_confirmation = True

            if self.config.high_risk_flags.intersection(action.risk_flags):
                requires_confirmation = True
                warnings.append(
                    f"High risk flags present on {action.type.value}: {action.risk_flags}"
                )

        return ValidationDecision(
            is_valid=not blocked_reasons,
            requires_confirmation=requires_confirmation,
            blocked_reasons=blocked_reasons,
            warnings=warnings,
        )
