import pytest

from life_os_agent.jira_client import JiraClient, JiraClientConfig


def test_check_connection_mock_mode() -> None:
    client = JiraClient(config=JiraClientConfig(mode="mock"))
    result = client.check_connection()
    assert result["ok"] is True
    assert result["mode"] == "mock"


def test_active_mode_requires_credentials() -> None:
    client = JiraClient(
        config=JiraClientConfig(mode="active", base_url="https://x.atlassian.net", email="", api_token="")
    )

    with pytest.raises(RuntimeError, match="requires email and api_token"):
        client._request_json("GET", "/rest/api/3/myself")


def test_get_workload_summary_active_uses_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    client = JiraClient(
        config=JiraClientConfig(
            mode="active",
            base_url="https://x.atlassian.net",
            email="a@b.com",
            api_token="token",
            project_key="ABC",
        )
    )

    def fake_request(method: str, path: str, payload=None):
        del method, payload
        if path.startswith("/rest/api/3/search?"):
            return {
                "issues": [
                    {"fields": {"status": {"name": "In Progress"}}},
                    {"fields": {"status": {"name": "Done"}}},
                ]
            }
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(JiraClient, "_request_json", lambda self, method, path, payload=None: fake_request(method, path, payload))
    result = client.get_workload_summary()

    assert result["source"] == "atlassian_cloud"
    assert result["open_issues"] == 1
    assert result["total_issues"] == 2
