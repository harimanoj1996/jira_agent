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
        if path.startswith("/rest/api/3/search/jql?"):
            return {
                "issues": [
                    {
                        "key": "ABC-1",
                        "fields": {
                            "status": {"name": "In Progress"},
                            "priority": {"name": "High"},
                            "duedate": "2000-01-01",
                        },
                    },
                    {
                        "key": "ABC-2",
                        "fields": {
                            "status": {"name": "Done"},
                            "priority": {"name": "Low"},
                            "duedate": None,
                        },
                    },
                ]
            }
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(
        JiraClient,
        "_request_json",
        lambda self, method, path, payload=None: fake_request(method, path, payload),
    )
    result = client.get_workload_summary()

    assert result["source"] == "atlassian_cloud"
    assert result["open_issues"] == 1
    assert result["total_issues"] == 2
    assert result["status_counts"]["In Progress"] == 1
    assert result["overdue_count"] == 1
    assert result["high_priority_open_count"] == 1


def test_get_recent_activity_active_uses_issue_updates(monkeypatch: pytest.MonkeyPatch) -> None:
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
        if path.startswith("/rest/api/3/search/jql?"):
            return {
                "issues": [
                    {
                        "key": "ABC-1",
                        "fields": {
                            "summary": "Fix login bug",
                            "status": {"name": "In Progress"},
                            "updated": "2026-03-06T00:00:00.000+0000",
                        },
                    }
                ]
            }
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(
        JiraClient,
        "_request_json",
        lambda self, method, path, payload=None: fake_request(method, path, payload),
    )

    activity = client.get_recent_activity()

    assert len(activity) == 1
    assert activity[0]["event"] == "issue_recently_updated"
    assert activity[0]["issue_key"] == "ABC-1"
