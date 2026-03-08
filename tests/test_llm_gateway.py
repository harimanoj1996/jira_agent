import pytest

from life_os_agent.llm_module import (
    LLMRuntimeConfig,
    MockLLMGateway,
    OpenAICompatibleGateway,
    build_gateway,
)


def test_build_gateway_defaults_to_mock() -> None:
    gateway = build_gateway()
    assert isinstance(gateway, MockLLMGateway)


def test_build_gateway_active_requires_api_key() -> None:
    with pytest.raises(RuntimeError, match="api_key"):
        build_gateway(LLMRuntimeConfig(mode="active", api_key=""))


def test_build_gateway_active_uses_openai_compatible() -> None:
    gateway = build_gateway(
        LLMRuntimeConfig(
            mode="active",
            api_key="test-key",
            model="gpt-4o-mini",
            base_url="https://api.openai.com",
        )
    )

    assert isinstance(gateway, OpenAICompatibleGateway)
    assert gateway.model == "gpt-4o-mini"
    assert gateway.base_url == "https://api.openai.com"
