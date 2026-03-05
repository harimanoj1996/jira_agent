# Life OS Agent (v1 Skeleton)

Life OS Agent is a **bounded, human-in-the-loop, voice-enabled Jira decision-support agent**.

The architecture prioritizes:

- safety over autonomy
- explainability over cleverness
- deterministic control over LLM freedom
- modular design for enterprise scaling

## Architecture

```text
Input Adapter -> Context Builder -> LLM Reasoner -> Validation Engine
                                                    |
                                                    v
                                        Human-in-the-Loop Confirmation
                                                    |
                                                    v
                                             Jira Execution Layer
                                                    |
                                                    v
                                             Audit Logging Store
```

## Module Layout

- `life_os_agent/input_layer.py`: text and voice-ready input abstraction.
- `life_os_agent/context_builder.py`: Jira context retrieval (issue references, workload, activity).
- `life_os_agent/llm_module.py`: LLM intent/summarization/action proposal interface with mock and active OpenAI-compatible gateway support.
- `life_os_agent/models.py`: strict typed schema models for system messages.
- `life_os_agent/validation.py`: deterministic validation and risk policy enforcement.
- `life_os_agent/hitl.py`: confirmation flow with YES / NO / EDIT support.
- `life_os_agent/jira_client.py`: deterministic Jira wrapper with retries and structured logging.
- `life_os_agent/execution.py`: action execution dispatcher independent of LLM.
- `life_os_agent/audit.py`: structured event logging and memory.
- `life_os_agent/orchestrator.py`: single-agent orchestration loop.
- `main.py`: runnable CLI demo.

## Safety Model

1. LLM can only classify and propose; it never executes Jira operations.
2. Validation engine is authoritative and deterministic.
3. Human confirmation gates medium/high-risk actions.
4. All critical events are logged for auditability.

## v1 Scope Supported

- create Jira tasks/stories
- update issue status
- detect overload/deadline risk flags
- generate daily summaries
- force confirmation for create/transition and high-risk flags

## Run Demo

```bash
python main.py
```

## Demo Output Notes

- You should see one or more `- action=...` lines as final output.
- Repeated `INFO:life_os_agent.audit:audit_event` lines from older builds are audit logs, not runtime failures.
- Current demo defaults to warning-level logging to keep the CLI output clean.

## Active LLM Setup

By default, the demo uses a deterministic mock model and now configures LLM access via **Python variables** in `main.py`.

```python
LLM_CONFIG = LLMRuntimeConfig(
    mode="mock",      # or "active"
    api_key="",       # required when mode="active"
    model="gpt-4o-mini",
    base_url="https://api.openai.com",
)
```

To use a live model, set `mode="active"` and provide `api_key` directly in `LLM_CONFIG`.

## Run Tests

```bash
python -m pytest
```

## Future Extensions

- replace `MockLLMGateway` with production provider adapter
- plug phone/SMS confirmation backend into `HumanApprovalGateway`
- swap in real Jira REST requests in `JiraClient`
- persist audit events into warehouse/SIEM
