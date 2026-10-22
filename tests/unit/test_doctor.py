import httpx
import respx

from cm_agents.doctor import run_doctor
from cm_agents.settings import Settings

PASSWORD = "admin-secret"


def _settings() -> Settings:
    return Settings(
        sn_instance_url="https://dev123.service-now.com",
        sn_admin_user="admin",
        sn_admin_password=PASSWORD,
        sn_agent_user="syn.svc.change_agents",
        sn_agent_password="agent-secret",
        xai_api_key="xai-secret",
        xai_model="grok-test",
    )


def _ok(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


@respx.mock
def test_doctor_reports_build_plugins_and_missing_agent_user() -> None:
    respx.get(url__regex=r".*/api/now/table/sys_properties").mock(
        return_value=_ok(
            {
                "result": [
                    {"name": "glide.buildname", "value": "Washingtondc"},
                    {"name": "glide.buildtag", "value": "glide-washingtondc-12-18-2024"},
                ]
            }
        )
    )
    respx.get(url__regex=r".*/api/now/table/v_plugin").mock(
        return_value=_ok(
            {
                "result": [
                    {
                        "name": "Change Management - Core",
                        "active": "active",
                        "id": "com.example.change",
                    }
                ]
            }
        )
    )
    respx.get(url__regex=r".*/api/now/table/sys_user").mock(return_value=_ok({"result": []}))

    report = run_doctor(_settings())
    text = report.text()
    assert report.ok is True
    assert "admin login: ok" in text
    assert "instance build: Washingtondc (glide-washingtondc-12-18-2024)" in text
    assert "Change Management - Core [com.example.change]: active=active" in text
    assert "agent user missing: run seed" in text
    assert PASSWORD not in text
    assert "xai-secret" not in text
    assert "syn.svc.change_agents" not in text


@respx.mock
def test_doctor_reports_failed_admin_login() -> None:
    respx.get(url__regex=r".*/api/now/table/sys_properties").mock(
        return_value=httpx.Response(401, json={"error": {"message": "User Not Authenticated"}})
    )
    report = run_doctor(_settings())
    assert report.ok is False
    assert report.text() == "admin login: failed"
    assert PASSWORD not in report.text()


@respx.mock
def test_doctor_reports_glide_war_when_build_properties_are_absent() -> None:
    respx.get(url__regex=r".*/api/now/table/sys_properties").mock(
        return_value=_ok(
            {"result": [{"name": "glide.war", "value": "glide-australia-02-11-2026.zip"}]}
        )
    )
    respx.get(url__regex=r".*/api/now/table/v_plugin").mock(return_value=_ok({"result": []}))
    respx.get(url__regex=r".*/api/now/table/sys_user").mock(return_value=_ok({"result": []}))
    text = run_doctor(_settings()).text()
    assert "glide.buildname and glide.buildtag were not found" in text
    assert "glide.war=glide-australia-02-11-2026.zip" in text


@respx.mock
def test_doctor_reports_agent_user_present_without_the_name() -> None:
    respx.get(url__regex=r".*/api/now/table/sys_properties").mock(
        return_value=_ok({"result": [{"name": "glide.buildname", "value": "X"}]})
    )
    respx.get(url__regex=r".*/api/now/table/v_plugin").mock(return_value=_ok({"result": []}))
    respx.get(url__regex=r".*/api/now/table/sys_user").mock(
        return_value=_ok({"result": [{"sys_id": "user1"}]})
    )
    text = run_doctor(_settings()).text()
    assert "agent user: present" in text
    assert "syn.svc.change_agents" not in text
