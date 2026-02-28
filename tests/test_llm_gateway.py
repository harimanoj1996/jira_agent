import pytest

from life_os_agent.llm_module import MockLLMGateway, OpenAICompatibleGateway, build_gateway_from_env


def test_build_gateway_defaults_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIFE_OS_LLM_MODE", raising=False)
    gateway = build_gateway_from_env()
    assert isinstance(gateway, MockLLMGateway)


def test_build_gateway_active_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIFE_OS_LLM_MODE", "active")
    monkeypatch.delenv("LIFE_OS_LLM_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="LIFE_OS_LLM_API_KEY"):
        build_gateway_from_env()


def test_build_gateway_active_uses_openai_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIFE_OS_LLM_MODE", "active")
    monkeypatch.setenv("LIFE_OS_LLM_API_KEY", "test-key")
    monkeypatch.setenv("LIFE_OS_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LIFE_OS_LLM_BASE_URL", "https://api.openai.com")

    gateway = build_gateway_from_env()

    assert isinstance(gateway, OpenAICompatibleGateway)
    assert gateway.model == "gpt-4o-mini"
    assert gateway.base_url == "https://api.openai.com"
