import json

import httpx
import respx

from cm_agents.data.batch import batch_create
from cm_agents.servicenow.client import ServiceNowError

BASE = "https://dev123.service-now.com"


def _client():
    from cm_agents.servicenow.client import ServiceNowClient

    return ServiceNowClient(BASE, "admin", "pw-value", sleep=lambda _seconds: None)


@respx.mock
def test_batch_create_reads_string_and_object_bodies() -> None:
    respx.post(url__regex=r".*/api/now/v1/batch").mock(
        return_value=httpx.Response(
            200,
            json={
                "serviced_requests": [
                    {
                        "id": "0",
                        "status_code": 201,
                        "body": json.dumps({"result": {"sys_id": "aaa"}}),
                    },
                    {"id": "1", "status_code": 201, "body": {"result": {"sys_id": "bbb"}}},
                ]
            },
        )
    )
    assert batch_create(_client(), "task_ci", [{"task": "1"}, {"task": "2"}]) == ["aaa", "bbb"]


@respx.mock
def test_batch_create_falls_back_when_the_batch_call_is_rejected() -> None:
    respx.post(url__regex=r".*/api/now/v1/batch").mock(
        return_value=httpx.Response(400, json={"error": {"message": "no batch"}})
    )
    respx.post(url__regex=r".*/api/now/table/task_ci").mock(
        return_value=httpx.Response(201, json={"result": {"sys_id": "aaa"}})
    )
    assert batch_create(_client(), "task_ci", [{"task": "1"}]) == ["aaa"]


@respx.mock
def test_batch_create_reports_an_item_error() -> None:
    respx.post(url__regex=r".*/api/now/v1/batch").mock(
        return_value=httpx.Response(
            200,
            json={"serviced_requests": [{"id": "0", "status_code": 403, "body": "{}"}]},
        )
    )
    try:
        batch_create(_client(), "task_ci", [{"task": "1"}])
    except Exception as exc:
        assert type(exc).__name__ == "BatchError"
        assert not isinstance(exc, ServiceNowError)
    else:
        raise AssertionError("batch item error was ignored")
