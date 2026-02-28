"""Demo entrypoint for Life OS Agent v1."""

from __future__ import annotations

import logging

from life_os_agent.audit import AuditStore
from life_os_agent.context_builder import ContextBuilder
from life_os_agent.execution import JiraExecutor
from life_os_agent.hitl import HumanApprovalGateway, HumanInTheLoop
from life_os_agent.input_layer import InputAdapter
from life_os_agent.jira_client import JiraClient, JiraClientConfig
from life_os_agent.llm_module import LLMReasoner, MockLLMGateway
from life_os_agent.orchestrator import LifeOSOrchestrator
from life_os_agent.validation import PolicyConfig, ValidationEngine


def build_orchestrator() -> LifeOSOrchestrator:
    """Wire all modules with deterministic defaults."""
    jira_client = JiraClient(config=JiraClientConfig())
    return LifeOSOrchestrator(
        context_builder=ContextBuilder(jira_client=jira_client),
        llm_reasoner=LLMReasoner(gateway=MockLLMGateway()),
        validation_engine=ValidationEngine(config=PolicyConfig()),
        human_loop=HumanInTheLoop(gateway=HumanApprovalGateway()),
        executor=JiraExecutor(jira_client=jira_client),
        audit_store=AuditStore(),
    )


def main() -> None:
    """Run a simple CLI demonstration cycle."""
    logging.basicConfig(level=logging.INFO)
    orchestrator = build_orchestrator()
    input_adapter = InputAdapter()

    user_text = input("Life OS Agent > ")
    user_input = input_adapter.from_text(user_text)
    results = orchestrator.run_once(user_input)
    for result in results:
        print(
            f"- action={result.action_type.value} success={result.success} "
            f"error={result.error} details={result.details}"
        )


if __name__ == "__main__":
    main()
