"""Read-only instance check: build, plugins, and whether the agent user exists."""

from __future__ import annotations

from dataclasses import dataclass

from cm_agents.servicenow.client import ServiceNowClient, ServiceNowError
from cm_agents.settings import Settings

PLUGIN_QUERY = "nameLIKEChange^ORnameLIKERelease^ORnameLIKECAB^ORnameLIKEConflict"
BUILD_QUERY = "nameINglide.buildname,glide.buildtag,glide.war"
BUILD_FALLBACK_QUERY = "nameSTARTSWITHglide.build^ORname=glide.war"


@dataclass
class DoctorReport:
    lines: list[str]
    ok: bool

    def text(self) -> str:
        return "\n".join(self.lines)


def run_doctor(settings: Settings) -> DoctorReport:
    lines: list[str] = []
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
    ) as client:
        try:
            build_rows = _build_properties(client)
        except ServiceNowError as exc:
            if exc.status_code in (401, 403):
                lines.append("admin login: failed")
                return DoctorReport(lines, ok=False)
            raise
        lines.append("admin login: ok")
        lines.append(_build_line(build_rows))
        table, plugins = _plugins(client)
        lines.append(f"plugin status ({table}):")
        if plugins:
            for row in plugins:
                lines.append(_plugin_line(row))
        else:
            lines.append("  no matching plugins")
        agent_rows = client.get_table(
            "sys_user",
            query=f"user_name={settings.sn_agent_user}",
            fields=["sys_id"],
            limit=1,
        )
        if agent_rows:
            lines.append("agent user: present")
        else:
            lines.append("agent user missing: run seed")
    return DoctorReport(lines, ok=True)


def _build_properties(client: ServiceNowClient) -> list[dict[str, object]]:
    rows = client.get_table(
        "sys_properties",
        query=BUILD_QUERY,
        fields=["name", "value"],
        limit=10,
    )
    if rows:
        return rows
    return client.get_table(
        "sys_properties",
        query=BUILD_FALLBACK_QUERY,
        fields=["name", "value"],
        limit=20,
    )


def _build_line(rows: list[dict[str, object]]) -> str:
    values = {str(row.get("name")): str(row.get("value") or "") for row in rows}
    name = values.get("glide.buildname")
    tag = values.get("glide.buildtag")
    if name or tag:
        return f"instance build: {name or 'unknown'} ({tag or 'unknown'})"
    war = values.get("glide.war")
    if war:
        return (
            "instance build: glide.buildname and glide.buildtag were not found; "
            f"glide.war={war}"
        )
    if not values:
        return "instance build: not found"
    found = ", ".join(f"{key}={value}" for key, value in sorted(values.items()))
    return f"instance build: glide.buildname and glide.buildtag were not found; {found}"


def _plugins(client: ServiceNowClient) -> tuple[str, list[dict[str, object]]]:
    errors: list[str] = []
    for table in ("v_plugin", "sys_plugins"):
        for fields in (["name", "active", "id"], ["name", "active"]):
            try:
                rows = client.get_table(table, query=PLUGIN_QUERY, fields=fields, limit=100)
            except ServiceNowError as exc:
                errors.append(f"{table} HTTP {exc.status_code}")
                continue
            rows.sort(key=lambda row: str(row.get("name") or ""))
            return table, rows
    detail = "; ".join(errors) if errors else "no plugin table"
    raise ServiceNowError(f"Plugin query failed: {detail}")


def _plugin_line(row: dict[str, object]) -> str:
    name = str(row.get("name") or "unknown")
    active = row.get("active")
    plugin_id = row.get("id")
    if plugin_id:
        return f"  {name} [{plugin_id}]: active={active}"
    return f"  {name}: active={active}"
