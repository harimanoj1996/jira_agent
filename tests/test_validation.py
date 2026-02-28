from life_os_agent.models import ActionType, InputSource, LLMDecision, ProposedAction, UserInput
from life_os_agent.validation import PolicyConfig, ValidationEngine


def test_create_issue_requires_summary_field() -> None:
    engine = ValidationEngine(config=PolicyConfig())
    user_input = UserInput(text="Create a task", source=InputSource.TEXT, confidence=1.0)
    decision = LLMDecision(
        intent="create_task",
        summary="Create task",
        proposed_actions=[
            ProposedAction(
                type=ActionType.CREATE_ISSUE,
                issue_key=None,
                fields={"description": "Missing summary"},
                reason="User asked",
                confidence=0.95,
                risk_flags=[],
            )
        ],
        requires_confirmation=True,
        confidence=0.95,
    )

    result = engine.validate(user_input, decision)

    assert not result.is_valid
    assert "create_issue action missing required field: summary" in result.blocked_reasons


def test_voice_input_uses_stricter_threshold() -> None:
    engine = ValidationEngine(config=PolicyConfig(min_confidence_text=0.7, min_confidence_voice=0.9))
    user_input = UserInput(text="Summarize", source=InputSource.VOICE, confidence=0.9)
    decision = LLMDecision(
        intent="summarize",
        summary="Summarize",
        proposed_actions=[
            ProposedAction(
                type=ActionType.SUMMARIZE,
                issue_key=None,
                fields={},
                reason="Daily report",
                confidence=0.85,
                risk_flags=[],
            )
        ],
        requires_confirmation=False,
        confidence=0.85,
    )

    result = engine.validate(user_input, decision)

    assert not result.is_valid
    assert any("below threshold" in item for item in result.blocked_reasons)
