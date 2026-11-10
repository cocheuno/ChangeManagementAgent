"""Classify sys_update_xml rows written during this build.

Hand-made admin work is listed on its own: the basic-auth role grant and the
incident.u_caused_by field (setup guide Parts B5 and B8). Every other row
must name a manifest record or one of the two approved settings. A row that
names neither is printed and fails the check. Payloads are not printed.
"""

from __future__ import annotations

import re
from typing import Any

from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import Settings, repo_root

# The role grant is dated 2026-10-21. The PDI is in Australia, so the query
# starts a day earlier and still excludes plugin rows from before the build.
BUILD_SINCE = "2026-10-20 00:00:00"
ROLE_GRANT = "snc_basic_auth_api_access role grant (setup guide Part B5)"
CAUSED_BY = "incident.u_caused_by field (setup guide Part B8)"
APPROVED = {
    "638460b6b70023008ef6eac7ee11a9f2": "change.conflict.ci_maint_sched",
    "0842df2437501000bff8e0f617733483": "Global Infrastructure condition",
}
_HEX = re.compile(r"[0-9a-f]{32}")
_PAGE = 200
_CAP = 5000


class UpdateXmlError(RuntimeError):
    """The update-xml check could not be completed."""


def update_xml_query(users: list[str], since: str = BUILD_SINCE) -> str:
    """Rows those users created or updated since the build started.

    `^NQ` keeps each date test inside the user test. A trailing `^OR` would
    include every row updated in that window, whoever wrote it.
    """
    if not users:
        raise UpdateXmlError("no users to query")
    for user in users:
        if any(mark in user for mark in (",", "^", "=")):
            raise UpdateXmlError("a user name cannot be used in an encoded query")
    joined = ",".join(users)
    created = f"sys_created_byIN{joined}^sys_created_on>={since}"
    updated = f"sys_created_byIN{joined}^sys_updated_on>={since}"
    return f"{created}^NQ{updated}"


def manifest_ids(manifest: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    records = manifest.get("records") or {}
    if isinstance(records, dict):
        for rows in records.values():
            _collect(found, rows)
    for bucket in (
        "import_sets",
        "staging_tables",
        "dictionary",
        "transform_maps",
        "field_maps",
        "update_xml",
    ):
        _collect(found, manifest.get(bucket))
    originals = manifest.get("oob_originals") or {}
    if isinstance(originals, dict):
        for row in originals.values():
            if isinstance(row, dict) and row.get("sys_id"):
                found.add(str(row["sys_id"]).lower())
    return found


def classify_text(text: str, known: set[str]) -> tuple[str, str] | None:
    """Return kind and detail when the text names a known record or a hand-made change."""
    ids = set(_HEX.findall(text.lower()))
    approved = [APPROVED[item] for item in sorted(ids) if item in APPROVED]
    if approved:
        return "approved", "; ".join(approved)
    matched = sorted(ids & known)
    if matched:
        return "manifest", matched[0]
    label = _hand_made_label(text)
    if label:
        return "hand_made", label
    return None


def _hand_made_label(text: str) -> str | None:
    """The two admin changes from the setup guide.

    The import staging column is also named u_caused_by. Those rows belong to
    the seed, so a u_syn_ name is not the incident field.
    """
    lowered = text.lower()
    if "snc_basic_auth_api_access" in lowered:
        return ROLE_GRANT
    if "u_syn_" in lowered or "syn incident import" in lowered or "syn change import" in lowered:
        return None
    if "u_caused_by" in lowered and "incident" in lowered:
        return CAUSED_BY
    return None


def classify_row(
    row: dict[str, Any],
    known: set[str],
    payload: str = "",
) -> tuple[str, str]:
    visible = f"{row.get('name') or ''}\n{row.get('target_name') or ''}"
    found = classify_text(visible, known)
    if found is None and payload:
        found = classify_text(f"{visible}\n{payload}", known)
    if found is None:
        return "orphan", ""
    return found


def report_update_xml(settings: Settings) -> int:
    """Print the classification. Return 1 when any row maps to neither list."""
    from cm_agents.data.manifest import load_manifest

    path = repo_root() / "data" / "synthetic" / "manifest.json"
    manifest = load_manifest(path)
    if manifest is None:
        raise UpdateXmlError("manifest missing")
    known = manifest_ids(manifest)
    users = [settings.sn_admin_user, settings.sn_agent_user]
    query = update_xml_query(users)
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
        timeout=180,
    ) as client:
        rows = _pages(client, query)
        classified = _classify_pages(client, rows, known)
    counts = {"hand_made": 0, "approved": 0, "manifest": 0, "orphan": 0}
    for kind, _detail, _row in classified:
        counts[kind] = counts.get(kind, 0) + 1
    print(f"update_xml rows={len(classified)}", flush=True)
    for kind in ("hand_made", "approved", "manifest", "orphan"):
        print(f"update_xml {kind}={counts[kind]}", flush=True)
    for kind, detail, row in classified:
        if kind == "manifest":
            continue
        name = str(row.get("name") or "")
        target = str(row.get("target_name") or "")
        sys_id = str(row.get("sys_id") or "")
        created_by = str(row.get("sys_created_by") or "")
        label = "admin" if created_by == settings.sn_admin_user else "agent"
        print(
            f"update_xml {kind} by={label} name={name} target={target} "
            f"sys_id={sys_id} detail={detail}",
            flush=True,
        )
    if counts["orphan"]:
        return 1
    return 0


def _collect(found: set[str], rows: object) -> None:
    if not isinstance(rows, list):
        return
    for row in rows:
        if isinstance(row, dict) and row.get("sys_id"):
            found.add(str(row["sys_id"]).lower())


def _pages(client: ServiceNowClient, query: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    fields = ["sys_id", "name", "target_name", "sys_created_by", "action"]
    while len(rows) < _CAP:
        page = client.get_table(
            "sys_update_xml",
            query=query,
            fields=fields,
            limit=_PAGE,
            offset=offset,
        )
        rows.extend(page)
        if len(page) < _PAGE:
            return rows
        offset += _PAGE
    raise UpdateXmlError(f"more than {_CAP} sys_update_xml rows")


def _classify_pages(
    client: ServiceNowClient,
    rows: list[dict[str, Any]],
    known: set[str],
) -> list[tuple[str, str, dict[str, Any]]]:
    classified: list[tuple[str, str, dict[str, Any]]] = []
    for row in rows:
        kind, detail = classify_row(row, known)
        if kind == "orphan":
            payload = _payload(client, str(row.get("sys_id") or ""))
            kind, detail = classify_row(row, known, payload)
        classified.append((kind, detail, row))
    return classified


def _payload(client: ServiceNowClient, sys_id: str) -> str:
    if not sys_id:
        return ""
    stored = client.get_record("sys_update_xml", sys_id, fields=["payload"])
    return str(stored.get("payload") or "")
