"""Main bounded orchestrator for Life OS Agent."""

from __future__ import annotations

from dataclasses import dataclass

from .audit import AuditStore
from .context_builder import ContextBuilder
from .execution import JiraExecutor
from .hitl import HumanInTheLoop
from .llm_module import LLMReasoner
from .models import ExecutionResult, UserInput
from .validation import ValidationEngine


@dataclass(slots=True)
class LifeOSOrchestrator:
    """Single-agent orchestration with deterministic policy enforcement."""

    context_builder: ContextBuilder
    llm_reasoner: LLMReasoner
    validation_engine: ValidationEngine
    human_loop: HumanInTheLoop
    executor: JiraExecutor
    audit_store: AuditStore

    def run_once(self, user_input: UserInput) -> list[ExecutionResult]:
        """Execute one bounded decision-support cycle."""
        self.audit_store.log_event(
            "user_input",
            {
                "text": user_input.text,
                "source": user_input.source.value,
                "confidence": user_input.confidence,
                "metadata": user_input.metadata,
            },
        )

        context = self.context_builder.build(user_input)
        decision = self.llm_reasoner.reason(user_input, context)
        self.audit_store.log_event("llm_output", {"intent": decision.intent, "summary": decision.summary})

        validation = self.validation_engine.validate(user_input, decision)
        self.audit_store.log_event(
            "validation_decision",
            {
                "is_valid": validation.is_valid,
                "requires_confirmation": validation.requires_confirmation,
                "blocked_reasons": validation.blocked_reasons,
                "warnings": validation.warnings,
            },
        )

        if not validation.is_valid:
            return [
                ExecutionResult(
                    action_type=action.type,
                    success=False,
                    error="Blocked by validation",
                    details={"blocked_reasons": validation.blocked_reasons},
                )
                for action in decision.proposed_actions
            ]

        actions = decision.proposed_actions
        if validation.requires_confirmation:
            confirmation = self.human_loop.request_confirmation(decision)
            self.audit_store.log_event(
                "human_confirmation",
                {
                    "approved": confirmation.approved,
                    "reviewer_note": confirmation.reviewer_note,
                },
            )
            if not confirmation.approved:
                return [
                    ExecutionResult(
                        action_type=action.type,
                        success=False,
                        error="Rejected by human reviewer",
                    )
                    for action in actions
                ]
            if confirmation.edited_actions:
                actions = confirmation.edited_actions

        results = self.executor.execute(actions)
        self.audit_store.log_event(
            "execution_results",
            {
                "results": [
                    {
                        "action_type": result.action_type.value,
                        "success": result.success,
                        "error": result.error,
                    }
                    for result in results
                ]
            },
        )
        return results
