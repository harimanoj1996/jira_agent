"""LLM reasoning abstraction and strict output parsing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import error, request

from .models import ActionType, JiraContext, LLMDecision, ProposedAction, UserInput


class LLMGateway(Protocol):
    """Protocol for pluggable model providers."""

    def complete(self, prompt: str) -> str:
        """Return raw model output text."""


@dataclass(slots=True)
class LLMRuntimeConfig:
    """Python-native runtime settings for LLM gateway selection."""

    mode: str = "mock"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com"


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
class OpenAICompatibleGateway:
    """OpenAI-compatible HTTP gateway for active model integration."""

    api_key: str
    model: str
    base_url: str = "https://api.openai.com"
    timeout_seconds: int = 30

    def complete(self, prompt: str) -> str:
        """Call an active LLM endpoint and return assistant content."""
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": "Return only JSON that matches the requested schema.",
                },
                {"role": "user", "content": prompt},
            ],
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url.rstrip('/')}/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"LLM HTTP error {exc.code}: {details}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"LLM connection failed: {exc}") from exc

        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("LLM response missing choices")
        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM response missing assistant content")
        return content.strip()


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
        schema = {
            "intent": "string",
            "summary": "string",
            "proposed_actions": [
                {
                    "type": "create_issue | update_issue | transition_issue | summarize | flag_risk",
                    "issue_key": "string or null",
                    "fields": {},
                    "reason": "string",
                    "confidence": 0.0,
                    "risk_flags": [],
                }
            ],
            "requires_confirmation": True,
            "confidence": 0.0,
        }
        return (
            "You are a bounded Jira decision-support reasoner. "
            "Never execute tools or APIs. "
            "Return ONLY valid JSON, no markdown, no prose.\n"
            f"Required schema: {json.dumps(schema)}\n"
            f"User input: {user_input.text}\n"
            f"Input source: {user_input.source.value}, confidence={user_input.confidence}\n"
            f"Issue details: {context.issue_details}\n"
            f"Workload summary: {context.workload_summary}\n"
            f"Recent activity: {context.recent_activity}"
        )

    def _parse_decision(self, raw_output: str) -> LLMDecision:
        payload = json.loads(raw_output)
        self._validate_payload_keys(payload)

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

    @staticmethod
    def _validate_payload_keys(payload: dict[str, Any]) -> None:
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


def build_gateway(config: LLMRuntimeConfig | None = None) -> LLMGateway:
    """Build gateway from Python runtime config, no environment variables required."""
    cfg = config or LLMRuntimeConfig()
    mode = cfg.mode.strip().lower()
    if mode != "active":
        return MockLLMGateway()
    if not cfg.api_key.strip():
        raise RuntimeError("LLMRuntimeConfig.api_key is required when mode='active'")
    return OpenAICompatibleGateway(
        api_key=cfg.api_key.strip(),
        model=cfg.model.strip() or "gpt-4o-mini",
        base_url=cfg.base_url.strip() or "https://api.openai.com",
    )
