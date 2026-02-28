"""Human-in-the-loop confirmation module."""

from __future__ import annotations

from dataclasses import dataclass

from .models import ConfirmationResult, LLMDecision, ProposedAction


@dataclass(slots=True)
class HumanApprovalGateway:
    """Simple synchronous review interface (CLI now; phone/SMS later)."""

    def request(self, prompt: str) -> str:
        """Request reviewer input from operator."""
        return input(prompt)


@dataclass(slots=True)
class HumanInTheLoop:
    """Builds review summaries and collects explicit operator approval."""

    gateway: HumanApprovalGateway

    def build_summary(self, decision: LLMDecision) -> str:
        """Generate readable action summary for review."""
        lines = [f"Intent: {decision.intent}", f"Summary: {decision.summary}"]
        for idx, action in enumerate(decision.proposed_actions, start=1):
            lines.append(
                f"{idx}. {action.type.value} issue={action.issue_key} confidence={action.confidence:.2f} "
                f"risk_flags={action.risk_flags} reason={action.reason} fields={action.fields}"
            )
        return "\n".join(lines)

    def request_confirmation(self, decision: LLMDecision) -> ConfirmationResult:
        """Capture YES / NO / EDIT human response and convert to typed decision."""
        summary = self.build_summary(decision)
        response = self.gateway.request(
            f"Review proposed actions:\n{summary}\nRespond YES, NO, or EDIT:<index> <field>=<value>\n> "
        ).strip()

        normalized = response.upper()
        if normalized == "YES":
            return ConfirmationResult(approved=True, reviewer_note="Approved")
        if normalized == "NO":
            return ConfirmationResult(approved=False, reviewer_note="Rejected")

        if response.startswith("EDIT:"):
            edited_actions = self._apply_edit(response, decision.proposed_actions)
            return ConfirmationResult(
                approved=True,
                edited_actions=edited_actions,
                reviewer_note=f"Edited via response: {response}",
            )

        return ConfirmationResult(approved=False, reviewer_note=f"Invalid response: {response}")

    def _apply_edit(self, edit_response: str, actions: list[ProposedAction]) -> list[ProposedAction]:
        """Apply minimal field edit grammar: EDIT:<index> key=value."""
        try:
            payload = edit_response.replace("EDIT:", "", 1).strip()
            index_str, assignment = payload.split(" ", 1)
            key, value = assignment.split("=", 1)
            index = int(index_str) - 1
            editable = list(actions)
            updated_fields = dict(editable[index].fields)
            updated_fields[key.strip()] = value.strip()
            editable[index] = ProposedAction(
                type=editable[index].type,
                issue_key=editable[index].issue_key,
                fields=updated_fields,
                reason=editable[index].reason,
                confidence=editable[index].confidence,
                risk_flags=editable[index].risk_flags,
            )
            return editable
        except (IndexError, ValueError):
            return actions
