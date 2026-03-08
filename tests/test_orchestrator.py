from life_os_agent.audit import AuditStore
from life_os_agent.context_builder import ContextBuilder
from life_os_agent.execution import JiraExecutor
from life_os_agent.hitl import HumanInTheLoop
from life_os_agent.jira_client import JiraClient, JiraClientConfig
from life_os_agent.llm_module import LLMReasoner, MockLLMGateway
from life_os_agent.models import InputSource, UserInput
from life_os_agent.orchestrator import LifeOSOrchestrator
from life_os_agent.validation import PolicyConfig, ValidationEngine


class StaticApprovalGateway:
    def __init__(self, response: str) -> None:
        self.response = response

    def request(self, prompt: str) -> str:
        del prompt
        return self.response


def test_orchestrator_executes_summary_without_confirmation() -> None:
    jira = JiraClient(config=JiraClientConfig())
    orchestrator = LifeOSOrchestrator(
        context_builder=ContextBuilder(jira_client=jira),
        llm_reasoner=LLMReasoner(gateway=MockLLMGateway()),
        validation_engine=ValidationEngine(config=PolicyConfig()),
        human_loop=HumanInTheLoop(gateway=StaticApprovalGateway("YES")),
        executor=JiraExecutor(jira_client=jira),
        audit_store=AuditStore(),
    )

    results = orchestrator.run_once(UserInput(text="Summarize my day", source=InputSource.TEXT))

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].action_type.value == "summarize"
