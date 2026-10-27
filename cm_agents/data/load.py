"""Load generated fixtures into the PDI.

Historical and open changes, the incidents, and the affected-CI rows go through
an Import Set with business rules off. Later agent-created changes still use
the Change API.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from cm_agents.data.batch import BatchError, batch_create
from cm_agents.data.generate import generate, write_fixtures
from cm_agents.data.ground_truth import build_ground_truth, write_ground_truth
from cm_agents.data.import_time import to_import_wall
from cm_agents.data.manifest import (
    add_artifact,
    add_record,
    load_manifest,
    new_manifest,
    save_manifest,
)
from cm_agents.data.queries import (
    BLACKOUT,
    CHANGE,
    CI,
    GROUP,
    IMPORT_SET,
    INCIDENT,
    PROPOSAL,
    RELATIONSHIP,
    SCHEDULE,
    SPAN,
    STAGING_TABLE,
    STD_TEMPLATE,
    STD_VERSION,
    TASK_CI,
    TEMPLATE,
)
from cm_agents.servicenow.client import ServiceNowClient, ServiceNowError
from cm_agents.settings import Settings, repo_root

IMPORT_ROW = "06803e7b8c1103100a22deb6dd2b4e9c"
CHUNK = 40
ROLE_WRITE = "sn_change_write"
CHG_STAGE = "u_syn_chg_import"
INC_STAGE = "u_syn_inc_import"
DATE_FIELDS = frozenset(
    {
        "opened_at",
        "closed_at",
        "work_start",
        "work_end",
        "start_date",
        "end_date",
        "resolved_at",
    }
)
CHANGE_FIELDS = (
    ("short_description", "string", "160"),
    ("description", "string", "4000"),
    ("type", "string", "40"),
    ("state", "string", "40"),
    ("active", "string", "40"),
    ("approval", "string", "40"),
    ("impact", "string", "40"),
    ("opened_at", "string", "40"),
    ("closed_at", "string", "40"),
    ("work_start", "string", "40"),
    ("work_end", "string", "40"),
    ("start_date", "string", "40"),
    ("end_date", "string", "40"),
    ("close_code", "string", "80"),
    ("close_notes", "string", "4000"),
    ("assignment_group", "reference", "sys_user_group"),
    ("cmdb_ci", "reference", "cmdb_ci"),
    ("parent", "reference", "task"),
    ("requested_by", "reference", "sys_user"),
    ("correlation_id", "string", "80"),
    ("chg_model", "reference", "chg_model"),
    ("implementation_plan", "string", "4000"),
    ("backout_plan", "string", "4000"),
    ("test_plan", "string", "4000"),
    ("justification", "string", "4000"),
)
TASK_CI_FIELDS = (
    ("task", "reference", "task"),
    ("ci_item", "reference", "cmdb_ci"),
)
INCIDENT_FIELDS = (
    ("short_description", "string", "160"),
    ("description", "string", "4000"),
    ("state", "string", "40"),
    ("active", "string", "40"),
    ("impact", "string", "40"),
    ("urgency", "string", "40"),
    ("priority", "string", "40"),
    ("opened_at", "string", "40"),
    ("resolved_at", "string", "40"),
    ("closed_at", "string", "40"),
    ("close_code", "string", "80"),
    ("close_notes", "string", "4000"),
    ("assignment_group", "reference", "sys_user_group"),
    ("cmdb_ci", "reference", "cmdb_ci"),
    ("caller_id", "reference", "sys_user"),
    ("parent", "reference", "task"),
    ("correlation_id", "string", "80"),
)
CHANGE_CHECK = (
    "state",
    "active",
    "approval",
    "opened_at",
    "closed_at",
    "work_start",
    "work_end",
    "start_date",
    "end_date",
    "close_code",
    "parent",
    "cmdb_ci",
    "assignment_group",
    "chg_model",
    "requested_by",
    "number",
)
INCIDENT_CHECK = (
    "state",
    "active",
    "impact",
    "urgency",
    "priority",
    "opened_at",
    "resolved_at",
    "closed_at",
    "close_code",
    "parent",
    "cmdb_ci",
    "caller_id",
    "number",
)
BASELINE_TABLES = (
    "change_request",
    "incident",
    "cmdb_ci",
    "cmdb_rel_ci",
    "task_ci",
    "sys_user",
    "sys_user_group",
    "cmn_schedule",
)


class SeedError(Exception):
    """The load cannot continue."""


def seed(
    settings: Settings,
    *,
    seed: int = 42,
    dry_run: bool = False,
    anchor: datetime | None = None,
) -> int:
    fixtures = generate(seed, anchor=anchor)
    directory = repo_root() / "data" / "synthetic"
    digest = write_fixtures(fixtures, directory)
    write_ground_truth(build_ground_truth(fixtures), directory)
    _say(f"anchor: {fixtures['anchor']}")
    _say(f"fixture hash: {digest}")
    if dry_run:
        return 0
    started = time.perf_counter()
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
        timeout=180,
    ) as client:
        created = _load(client, settings, fixtures, directory / "manifest.json", seed)
    _say(f"load seconds: {time.perf_counter() - started:.1f}")
    _say(f"created: {created}")
    _say("SEED OK")
    return 0


def values_match(expected: object, actual: object) -> bool:
    if _blank(expected) and _blank(actual):
        return True
    if isinstance(expected, bool):
        return _is_true(actual) if expected else _is_false(actual)
    return str(expected) == str(actual if actual is not None else "")


def _load(
    client: ServiceNowClient,
    settings: Settings,
    fixtures: dict[str, Any],
    path: Path,
    seed: int,
) -> int:
    manifest = _prepare_manifest(client, path, seed, str(fixtures["anchor"]))
    before = _population(client)
    groups = _ensure_groups(client, manifest, path, fixtures)
    _ensure_templates(client, manifest, path, fixtures, groups)
    users = _ensure_users(client, manifest, path, fixtures)
    _ensure_integration_user(client, settings, manifest, path)
    _ensure_memberships(client, manifest, path, fixtures, groups, users)
    schedules = _ensure_schedules(client, manifest, path, fixtures)
    cis = _ensure_cis(client, manifest, path, fixtures, schedules)
    _ensure_relationships(client, manifest, path, fixtures, cis)
    ids = _import_history(client, manifest, path, fixtures, groups, users, cis)
    _ensure_task_links(client, manifest, path, fixtures, ids, cis)
    _load_check(client, fixtures, ids, cis, groups, users)
    _print_gate(client, fixtures)
    _print_samples(client, fixtures)
    return _population(client) - before


def _prepare_manifest(
    client: ServiceNowClient, path: Path, seed: int, anchor: str
) -> dict[str, Any]:
    manifest = load_manifest(path)
    if manifest and (manifest.get("seed") != seed or manifest.get("anchor") != anchor):
        if client.count("change_request", CHANGE):
            raise SeedError("teardown first")
        manifest = None
    if manifest:
        return manifest
    if client.count("change_request", CHANGE):
        raise SeedError("teardown first")
    baseline = {table: client.count(table) for table in BASELINE_TABLES}
    manifest = new_manifest(seed, baseline, anchor)
    save_manifest(path, manifest)
    return manifest


def _ensure_groups(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    fixtures: dict[str, Any],
) -> dict[str, str]:
    names = {row["name"] for row in fixtures["groups"]}
    names.update(group for user in fixtures["users"] for group in user["groups"])
    found: dict[str, str] = {}
    for name in sorted(names):
        rows = client.get_table(
            "sys_user_group",
            query=f"name={name}",
            fields=["sys_id", "name"],
            limit=5,
        )
        match = next((row for row in rows if row.get("name") == name), None)
        if match:
            found[name] = str(match["sys_id"])
            continue
        if not name.startswith("SYN"):
            raise SeedError(f"required group is missing: {name}")
        created = client.create_record(
            "sys_user_group",
            {"name": name, "active": "true", "description": "Synthetic Larkspur Outfitters group"},
        )
        found[name] = str(created["sys_id"])
        add_record(manifest, "sys_user_group", found[name], name)
        save_manifest(path, manifest)
        _say(f"group created: {name}")
    return found


def _ensure_users(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    fixtures: dict[str, Any],
) -> dict[str, str]:
    found: dict[str, str] = {}
    for user in fixtures["users"]:
        name = user["user_name"]
        rows = client.get_table(
            "sys_user",
            query=f"user_name={name}",
            fields=["sys_id", "user_name"],
            limit=1,
        )
        if rows:
            found[name] = str(rows[0]["sys_id"])
            continue
        created = client.create_record(
            "sys_user",
            {
                "user_name": name,
                "first_name": user["first_name"],
                "last_name": user["last_name"],
                "email": user["email"],
                "active": "true",
            },
        )
        found[name] = str(created["sys_id"])
        add_record(manifest, "sys_user", found[name], name)
        save_manifest(path, manifest)
    _say(f"users ready: {len(found)}")
    return found


def _ensure_integration_user(
    client: ServiceNowClient,
    settings: Settings,
    manifest: dict[str, Any],
    path: Path,
) -> int:
    name = settings.sn_agent_user
    rows = client.get_table(
        "sys_user",
        query=f"user_name={name}",
        fields=["sys_id", "time_zone", "web_service_access_only"],
        limit=1,
    )
    created_user = 0
    if rows:
        sys_id = str(rows[0]["sys_id"])
    else:
        created = client.create_record(
            "sys_user",
            {
                "user_name": name,
                "first_name": "svc",
                "last_name": "change",
                "email": f"{name}@example.com",
                "active": "true",
                "locked_out": "false",
                "password_needs_reset": "false",
                "web_service_access_only": "true",
                "time_zone": "UTC",
                "user_password": settings.sn_agent_password,
            },
            input_display_value=True,
        )
        sys_id = str(created["sys_id"])
        add_record(manifest, "sys_user", sys_id, "integration")
        save_manifest(path, manifest)
        created_user = 1
    _ensure_role(client, manifest, path, sys_id)
    if not _login_ok(settings):
        client.update_record(
            "sys_user",
            sys_id,
            {"user_password": settings.sn_agent_password, "password_needs_reset": "false"},
            input_display_value=True,
        )
        if not _login_ok(settings):
            raise SeedError("integration user login: failed")
    stored = client.get_record("sys_user", sys_id, fields=["time_zone", "web_service_access_only"])
    zone = stored.get("time_zone") or "empty"
    _say("integration user login: ok")
    _say(f"integration user time_zone: {zone}")
    if not _is_true(stored.get("web_service_access_only")):
        raise SeedError("integration user is not web service access only")
    return created_user


def _ensure_role(
    client: ServiceNowClient, manifest: dict[str, Any], path: Path, user_id: str
) -> None:
    roles = client.get_table(
        "sys_user_role",
        query=f"name={ROLE_WRITE}",
        fields=["sys_id", "name"],
        limit=1,
    )
    if not roles:
        raise SeedError("role sn_change_write was not found")
    role_id = str(roles[0]["sys_id"])
    grants = client.get_table(
        "sys_user_has_role",
        query=f"user={user_id}^inherited=false",
        fields=["sys_id", "role"],
        limit=20,
    )
    direct = {str(row.get("role")) for row in grants}
    if role_id not in direct:
        created = client.create_record(
            "sys_user_has_role",
            {"user": user_id, "role": role_id, "inherited": "false"},
        )
        add_record(manifest, "sys_user_has_role", str(created["sys_id"]), ROLE_WRITE)
        save_manifest(path, manifest)
        direct.add(role_id)
    if direct != {role_id}:
        raise SeedError("integration user direct roles are not exactly sn_change_write")


def _login_ok(settings: Settings) -> bool:
    try:
        with ServiceNowClient(
            settings.sn_instance_url,
            settings.sn_agent_user,
            settings.sn_agent_password,
            secrets=settings.secret_values(),
            timeout=60,
        ) as agent:
            agent.get_table("change_request", fields=["sys_id"], limit=1)
    except ServiceNowError:
        return False
    return True


def _ensure_memberships(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    fixtures: dict[str, Any],
    groups: dict[str, str],
    users: dict[str, str],
) -> int:
    created = 0
    for user in fixtures["users"]:
        user_id = users[user["user_name"]]
        for name in user["groups"]:
            group_id = groups[name]
            rows = client.get_table(
                "sys_user_grmember",
                query=f"user={user_id}^group={group_id}",
                fields=["sys_id"],
                limit=1,
            )
            if rows:
                continue
            row = client.create_record(
                "sys_user_grmember",
                {"user": user_id, "group": group_id},
            )
            add_record(
                manifest,
                "sys_user_grmember",
                str(row["sys_id"]),
                f"{user['user_name']}|{name}",
            )
            created += 1
    save_manifest(path, manifest)
    _say(f"memberships created: {created}")
    return created


def _ensure_schedules(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    fixtures: dict[str, Any],
) -> dict[str, str]:
    found: dict[str, str] = {}
    for schedule in fixtures["schedules"]:
        name = schedule["name"]
        rows = client.get_table(
            "cmn_schedule",
            query=f"name={name}",
            fields=["sys_id", "name", "time_zone"],
            limit=1,
        )
        if rows:
            sys_id = str(rows[0]["sys_id"])
            zone = rows[0].get("time_zone")
        else:
            created = client.create_record(
                "cmn_schedule",
                {"name": name, "time_zone": "US/Eastern", "type": "maintenance"},
            )
            sys_id = str(created["sys_id"])
            add_record(manifest, "cmn_schedule", sys_id, name)
            save_manifest(path, manifest)
            stored = client.get_record("cmn_schedule", sys_id, fields=["time_zone"])
            zone = stored.get("time_zone")
        if zone != "US/Eastern":
            raise SeedError(f"schedule time zone did not persist: {zone or 'empty'}")
        found[name] = sys_id
        for span in schedule["spans"]:
            _ensure_span(client, manifest, path, sys_id, span)
    return found


def _ensure_span(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    schedule_id: str,
    span: dict[str, str],
) -> None:
    rows = client.get_table(
        "cmn_schedule_span",
        query=f"name={span['name']}^schedule={schedule_id}",
        fields=["sys_id"],
        limit=1,
    )
    if rows:
        return
    created = client.create_record(
        "cmn_schedule_span",
        {
            "name": span["name"],
            "schedule": schedule_id,
            "start_date_time": span["start_date_time"],
            "end_date_time": span["end_date_time"],
            "repeat_type": span["repeat_type"],
            "repeat_count": "1",
            "days_of_week": span["days_of_week"],
            "all_day": "false",
        },
    )
    add_record(manifest, "cmn_schedule_span", str(created["sys_id"]), span["name"])
    save_manifest(path, manifest)


def _ensure_cis(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    fixtures: dict[str, Any],
    schedules: dict[str, str],
) -> dict[str, str]:
    found = _index(client, "cmdb_ci", CI, "name")
    pending: dict[str, list[dict[str, Any]]] = {}
    for ci in fixtures["cis"]:
        if ci["name"] not in found:
            pending.setdefault(ci["table"], []).append(ci)
    created = 0
    for table, rows in pending.items():
        for offset in range(0, len(rows), CHUNK):
            chunk = rows[offset : offset + CHUNK]
            bodies = [_ci_body(ci, schedules) for ci in chunk]
            try:
                sys_ids = batch_create(client, table, bodies)
            except BatchError as exc:
                raise SeedError(str(exc)) from None
            for ci, sys_id in zip(chunk, sys_ids, strict=True):
                found[ci["name"]] = sys_id
                add_record(manifest, "cmdb_ci", sys_id, ci["name"])
            created += len(chunk)
            save_manifest(path, manifest)
            _say(f"cis {table} {created}")
    _say(f"cis ready: {len(found)}")
    return found


def _ci_body(ci: dict[str, Any], schedules: dict[str, str]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": ci["name"],
        "short_description": ci["name"] if ci["name"].startswith("SYN") else f"SYN {ci['name']}",
        "maintenance_schedule": schedules[ci["schedule"]],
    }
    if ci["environment"]:
        body["environment"] = ci["environment"]
    return body


def _ensure_relationships(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    fixtures: dict[str, Any],
    cis: dict[str, str],
) -> None:
    types = _relationship_types(client)
    existing = _relationship_ids(client)
    recorded = {row["sys_id"] for row in manifest["records"].get("cmdb_rel_ci", [])}
    bodies = []
    keys = []
    backfilled = False
    for link in fixtures["relationships"]:
        parent = cis[link["parent"]]
        child = cis[link["child"]]
        rel_type = types[link["type"]]
        ident = f"{parent}|{rel_type}|{child}"
        key = f"{link['parent']}|{link['type']}|{link['child']}"
        # A row created before a failed manifest write is already on the instance.
        if ident in existing:
            if existing[ident] not in recorded:
                add_record(manifest, "cmdb_rel_ci", existing[ident], key)
                backfilled = True
            continue
        bodies.append({"parent": parent, "child": child, "type": rel_type})
        keys.append(key)
    if backfilled:
        save_manifest(path, manifest)
    for offset in range(0, len(bodies), CHUNK):
        try:
            sys_ids = batch_create(client, "cmdb_rel_ci", bodies[offset : offset + CHUNK])
        except BatchError as exc:
            raise SeedError(str(exc)) from None
        for key, sys_id in zip(keys[offset : offset + CHUNK], sys_ids, strict=True):
            add_record(manifest, "cmdb_rel_ci", sys_id, key)
        save_manifest(path, manifest)
    _say(f"relationships created: {len(bodies)}")


def _relationship_types(client: ServiceNowClient) -> dict[str, str]:
    names = ("Depends on::Used by", "Runs on::Runs", "Hosted on::Hosts")
    found: dict[str, str] = {}
    for name in names:
        rows = client.get_table(
            "cmdb_rel_type",
            query=f"name={name}",
            fields=["sys_id", "name"],
            limit=1,
        )
        if not rows:
            raise SeedError(f"relationship type is missing: {name}")
        found[name] = str(rows[0]["sys_id"])
    return found


def _relationship_ids(client: ServiceNowClient) -> dict[str, str]:
    rows = client.get_records(
        "cmdb_rel_ci",
        query=RELATIONSHIP,
        fields=["sys_id", "parent", "child", "type"],
        page_size=200,
        max_records=5000,
    )
    return {
        f"{row.get('parent')}|{row.get('type')}|{row.get('child')}": str(row["sys_id"])
        for row in rows
    }


def _import_history(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    fixtures: dict[str, Any],
    groups: dict[str, str],
    users: dict[str, str],
    cis: dict[str, str],
) -> dict[str, str]:
    change_table = _ensure_import_table(
        client, manifest, path, CHG_STAGE, "SYN Change Import", "change_request", CHANGE_FIELDS
    )
    incident_table = _ensure_import_table(
        client, manifest, path, INC_STAGE, "SYN Incident Import", "incident", INCIDENT_FIELDS
    )
    requester = _role_user(fixtures, users, "service_desk")
    ids = _index(client, "change_request", CHANGE, "correlation_id")
    ids.update(_index(client, "incident", INCIDENT, "correlation_id"))
    releases = [row for row in fixtures["changes"] if row["release"]]
    rest = [row for row in fixtures["changes"] if not row["release"]]
    _import_records(
        client,
        manifest,
        path,
        change_table,
        "change_request",
        releases,
        ids,
        groups,
        requester,
        cis,
        verify=True,
    )
    _import_records(
        client,
        manifest,
        path,
        incident_table,
        "incident",
        fixtures["incidents"],
        ids,
        groups,
        requester,
        cis,
        verify=True,
    )
    _import_records(
        client,
        manifest,
        path,
        change_table,
        "change_request",
        rest,
        ids,
        groups,
        requester,
        cis,
        verify=True,
    )
    _label_import_sets(client, manifest, path)
    return ids


def _import_records(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    stage: str,
    target: str,
    rows: list[dict[str, Any]],
    ids: dict[str, str],
    groups: dict[str, str],
    requester: str,
    cis: dict[str, str],
    *,
    verify: bool,
) -> None:
    missing = [row for row in rows if row["key"] not in ids]
    if not missing:
        return
    ordered = missing
    if verify:
        probe_at = next((index for index, row in enumerate(missing) if row.get("parent")), 0)
        probe = missing[probe_at]
        _import_chunk(client, manifest, path, stage, target, [probe], ids, groups, requester, cis)
        _verify_imported(probe, ids, groups, cis, client, target)
        ordered = [row for row in missing if row["key"] != probe["key"]]
    done = len(missing) - len(ordered)
    for offset in range(0, len(ordered), CHUNK):
        chunk = ordered[offset : offset + CHUNK]
        _import_chunk(client, manifest, path, stage, target, chunk, ids, groups, requester, cis)
        done += len(chunk)
        _say(f"imported {target} {done}/{len(missing)}")


def _import_chunk(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    stage: str,
    target: str,
    chunk: list[dict[str, Any]],
    ids: dict[str, str],
    groups: dict[str, str],
    requester: str,
    cis: dict[str, str],
) -> None:
    payloads = [_payload(row, target, ids, groups, requester, cis) for row in chunk]
    _post_import(client, manifest, path, stage, payloads)
    joined = ",".join(row["key"] for row in chunk)
    found = client.get_records(
        target,
        query=f"correlation_idIN{joined}",
        fields=["sys_id", "correlation_id"],
        page_size=CHUNK,
        max_records=CHUNK,
    )
    by_key = {str(row.get("correlation_id")): str(row["sys_id"]) for row in found}
    if set(by_key) != {row["key"] for row in chunk}:
        raise SeedError(f"import did not insert every {target} row")
    for row in chunk:
        ids[row["key"]] = by_key[row["key"]]
        add_record(manifest, target, ids[row["key"]], row["key"])
    save_manifest(path, manifest)


def _verify_imported(
    row: dict[str, Any],
    ids: dict[str, str],
    groups: dict[str, str],
    cis: dict[str, str],
    client: ServiceNowClient,
    target: str,
) -> None:
    stored = client.get_record(
        target,
        ids[row["key"]],
        fields=[
            "number",
            "opened_at",
            "state",
            "active",
            "approval",
            "parent",
            "assignment_group",
            "cmdb_ci",
            "chg_model",
        ],
    )
    if stored.get("opened_at") != row["opened_at"]:
        raise SeedError(f"opened_at mismatch for {row['key']}: stored {stored.get('opened_at')}")
    if not values_match(row["state"], stored.get("state")):
        raise SeedError(f"state mismatch for {row['key']}")
    if not values_match(row["active"], stored.get("active")):
        raise SeedError(f"active mismatch for {row['key']}")
    if "approval" in row and not values_match(row["approval"], stored.get("approval")):
        raise SeedError(f"approval mismatch for {row['key']}")
    if not str(stored.get("number") or ""):
        raise SeedError(f"number was empty for {row['key']}")
    if stored.get("assignment_group") != groups[row["assignment_group"]]:
        raise SeedError(f"assignment group mismatch for {row['key']}")
    if stored.get("cmdb_ci") != cis[row["cmdb_ci"]]:
        raise SeedError(f"configuration item mismatch for {row['key']}")
    if target == "change_request" and stored.get("chg_model") != row["chg_model"]:
        raise SeedError(f"change model mismatch for {row['key']}")
    if row.get("parent") and stored.get("parent") != ids[row["parent"]]:
        raise SeedError(f"parent mismatch for {row['key']}")


def _payload(
    row: dict[str, Any],
    target: str,
    ids: dict[str, str],
    groups: dict[str, str],
    requester: str,
    cis: dict[str, str],
) -> dict[str, str]:
    values: dict[str, str] = {
        "short_description": row["short_description"],
        "description": row["description"],
        "state": row["state"],
        "active": "true" if row["active"] else "false",
        "impact": row["impact"],
        "opened_at": _wall(row["opened_at"]),
        "closed_at": _wall(row.get("closed_at", "")),
        "close_code": row.get("close_code", ""),
        "close_notes": row.get("close_notes", ""),
        "assignment_group": groups[row["assignment_group"]],
        "cmdb_ci": cis[row["cmdb_ci"]],
        "correlation_id": row["key"],
    }
    if target == "change_request":
        values.update(
            {
                "type": row["type"],
                "approval": row["approval"],
                "work_start": _wall(row["work_start"]),
                "work_end": _wall(row["work_end"]),
                "start_date": _wall(row["start_date"]),
                "end_date": _wall(row["end_date"]),
                "requested_by": requester,
                "chg_model": row["chg_model"],
                "implementation_plan": row["implementation_plan"],
                "backout_plan": row["backout_plan"],
                "test_plan": row["test_plan"],
                "justification": row["justification"],
            }
        )
    else:
        values.update(
            {
                "urgency": row["urgency"],
                "priority": row["priority"],
                "resolved_at": _wall(row["resolved_at"]),
                "caller_id": requester,
            }
        )
    if row.get("parent"):
        values["parent"] = ids[row["parent"]]
    return {f"u_{key}": value for key, value in values.items() if value != ""}


def _post_import(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    stage: str,
    payloads: list[dict[str, str]],
) -> None:
    """Post one staging row at a time.

    A JSON array sent to the Import Set API on this instance inserts only the
    first object. The multi-row endpoint needs a Rest Insert Multiple row,
    which seed does not create.
    """
    for payload in payloads:
        _post_one(client, manifest, path, stage, payload)


def _post_one(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    stage: str,
    payload: dict[str, str],
) -> str:
    try:
        response = client.request("POST", f"/api/now/import/{stage}", json=payload)
    except ServiceNowError as exc:
        raise SeedError(str(exc)) from None
    number = str(response.get("import_set") or "")
    if number:
        _record_import_set(client, manifest, path, number)
    results = response.get("result")
    if isinstance(results, dict):
        results = [results]
    if not isinstance(results, list) or len(results) != 1:
        raise SeedError("import returned an unexpected result")
    item = results[0]
    status = str(item.get("status") or "") if isinstance(item, dict) else ""
    if status not in {"inserted", "updated"}:
        detail = ""
        if isinstance(item, dict):
            detail = str(item.get("error_message") or item.get("status_message") or status)
        raise SeedError(f"import {status or 'failed'}: {detail}")
    if not isinstance(item, dict):
        return ""
    return str(item.get("sys_id") or "")


def _record_import_set(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    number: str,
) -> None:
    recorded = manifest.get("import_sets")
    if isinstance(recorded, list) and any(
        isinstance(row, dict) and row.get("key") == number for row in recorded
    ):
        return
    sets = client.get_table(
        "sys_import_set",
        query=f"number={number}",
        fields=["sys_id"],
        limit=1,
    )
    if not sets:
        return
    add_artifact(manifest, "import_sets", str(sets[0]["sys_id"]), number)
    save_manifest(path, manifest)


def _label_import_sets(client: ServiceNowClient, manifest: dict[str, Any], path: Path) -> None:
    """Record import sets. A synchronous set can stay in loading; teardown deletes it."""
    rows = client.get_records(
        "sys_import_set",
        query=IMPORT_SET,
        fields=["sys_id", "number", "state"],
        page_size=100,
        max_records=500,
    )
    for row in rows:
        sys_id = str(row["sys_id"])
        try:
            client.update_record(
                "sys_import_set",
                sys_id,
                {"short_description": "SYN import", "state": "processed"},
            )
        except ServiceNowError:
            pass
        add_artifact(manifest, "import_sets", sys_id, str(row.get("number") or ""))
    if rows:
        save_manifest(path, manifest)
    stored = client.get_table(
        "sys_import_set",
        query=IMPORT_SET,
        fields=["state"],
        limit=20,
    )
    states = ",".join(sorted({str(row.get("state") or "empty") for row in stored}))
    _say(f"import sets: {len(rows)} state={states or 'none'}")


def _ensure_import_table(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    name: str,
    label: str,
    target: str,
    fields: tuple[tuple[str, str, str], ...],
) -> str:
    rows = client.get_table(
        "sys_db_object", query=f"name={name}", fields=["sys_id", "name"], limit=1
    )
    if rows:
        table_name = str(rows[0]["name"])
        add_artifact(manifest, "staging_tables", str(rows[0]["sys_id"]), table_name)
    else:
        created = client.create_record(
            "sys_db_object",
            {
                "label": label,
                "name": name,
                "super_class": IMPORT_ROW,
                "create_access_controls": "false",
                "create_module": "false",
                "is_extendable": "false",
            },
        )
        table_name = str(created.get("name") or name)
        add_artifact(manifest, "staging_tables", str(created["sys_id"]), table_name)
        save_manifest(path, manifest)
    existing = {
        str(row.get("element"))
        for row in client.get_table(
            "sys_dictionary",
            query=f"name={table_name}",
            fields=["sys_id", "element"],
            limit=200,
        )
    }
    for element, internal, detail in fields:
        column = f"u_{element}"
        if column in existing:
            continue
        body: dict[str, str] = {
            "name": table_name,
            "element": column,
            "column_label": element,
            "internal_type": internal,
            "active": "true",
        }
        if internal == "reference":
            body["reference"] = detail
        else:
            body["max_length"] = detail
        created = client.create_record("sys_dictionary", body)
        add_artifact(manifest, "dictionary", str(created["sys_id"]), f"{table_name}.{column}")
    maps = client.get_table(
        "sys_transform_map",
        query=f"name={label}",
        fields=["sys_id"],
        limit=1,
    )
    if maps:
        map_id = str(maps[0]["sys_id"])
    else:
        created = client.create_record(
            "sys_transform_map",
            {
                "name": label,
                "source_table": table_name,
                "target_table": target,
                "active": "true",
                "run_business_rules": "false",
                "run_script": "false",
                "enforce_mandatory_fields": "false",
                "order": "100",
            },
        )
        map_id = str(created["sys_id"])
        add_artifact(manifest, "transform_maps", map_id, label)
    stored_map = client.get_record("sys_transform_map", map_id, fields=["run_business_rules"])
    rules = stored_map.get("run_business_rules")
    if not _is_false(rules):
        raise SeedError(f"transform map {label} is not running with business rules off")
    present = {
        str(row.get("source_field"))
        for row in client.get_table(
            "sys_transform_entry",
            query=f"map={map_id}",
            fields=["sys_id", "source_field"],
            limit=200,
        )
    }
    for element, _internal, _detail in fields:
        source = f"u_{element}"
        if source in present:
            continue
        created = client.create_record(
            "sys_transform_entry",
            {
                "map": map_id,
                "source_table": table_name,
                "target_table": target,
                "source_field": source,
                "target_field": element,
                "choice_action": "ignore",
                "use_source_script": "false",
                "coalesce": "false",
            },
        )
        add_artifact(manifest, "field_maps", str(created["sys_id"]), f"{label}.{source}")
    save_manifest(path, manifest)
    return table_name


def _ensure_task_links(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    fixtures: dict[str, Any],
    ids: dict[str, str],
    cis: dict[str, str],
) -> None:
    """Load affected CIs through the import set.

    A Table API insert is aborted by the business rule ``Change Model: Read
    only CI (Insert)`` when the change model does not allow CI edits. Closed
    and canceled changes are in that set. Business rules stay off on the map.
    """
    stage = _ensure_import_table(
        client,
        manifest,
        path,
        "u_syn_taskci_import",
        "SYN Task CI Import",
        "task_ci",
        TASK_CI_FIELDS,
    )
    rows = client.get_records(
        "task_ci",
        query=TASK_CI,
        fields=["sys_id", "task", "ci_item"],
        page_size=200,
        max_records=5000,
    )
    existing = {f"{row.get('task')}|{row.get('ci_item')}" for row in rows}
    missing: list[tuple[str, str, str]] = []
    for link in fixtures["task_ci"]:
        task_id = ids[link["change"]]
        ci_id = cis[link["ci"]]
        key = f"{task_id}|{ci_id}"
        if key in existing:
            continue
        missing.append((f"{link['change']}|{link['ci']}", task_id, ci_id))
    if not missing:
        _say("task_ci created: 0")
        return
    for index, (key, task_id, ci_id) in enumerate(missing, start=1):
        sys_id = _post_one(
            client,
            manifest,
            path,
            stage,
            {"u_task": task_id, "u_ci_item": ci_id},
        )
        if not sys_id:
            sys_id = _task_ci_id(client, task_id, ci_id)
        if index == 1:
            _verify_task_ci(client, sys_id, task_id, ci_id)
        add_record(manifest, "task_ci", sys_id, key)
        if index % CHUNK == 0 or index == len(missing):
            save_manifest(path, manifest)
            _say(f"task_ci {index}/{len(missing)}")


def _task_ci_id(client: ServiceNowClient, task_id: str, ci_id: str) -> str:
    found = client.get_table(
        "task_ci",
        query=f"task={task_id}^ci_item={ci_id}",
        fields=["sys_id"],
        limit=1,
    )
    if not found:
        raise SeedError("task_ci import did not return a sys_id")
    return str(found[0]["sys_id"])


def _verify_task_ci(client: ServiceNowClient, sys_id: str, task_id: str, ci_id: str) -> None:
    try:
        stored = client.get_record("task_ci", sys_id, fields=["task", "ci_item"])
    except ServiceNowError as exc:
        raise SeedError("task_ci import did not return the new row") from exc
    if stored.get("task") != task_id or stored.get("ci_item") != ci_id:
        raise SeedError("task_ci import did not keep the change and configuration item")


def _expected_change(row: dict[str, Any], ids: dict[str, str]) -> dict[str, object]:
    expected: dict[str, object] = {field: row.get(field, "") for field in CHANGE_CHECK}
    expected["parent"] = ids[row["parent"]] if row.get("parent") else ""
    expected["cmdb_ci"] = ids.get(row["cmdb_ci"], row["cmdb_ci"])
    expected["number"] = stored_number_sentinel()
    return expected


def stored_number_sentinel() -> str:
    return "*"


def _expected_incident(row: dict[str, Any], ids: dict[str, str]) -> dict[str, object]:
    expected: dict[str, object] = {field: row.get(field, "") for field in INCIDENT_CHECK}
    expected["parent"] = ids[row["parent"]] if row.get("parent") else ""
    expected["number"] = stored_number_sentinel()
    return expected


def _diff(key: str, expected: dict[str, object], stored: dict[str, Any]) -> list[str]:
    mismatches = []
    for field, want in expected.items():
        actual = stored.get(field)
        if field == "number":
            if not str(actual or ""):
                mismatches.append(f"{key} number empty")
            continue
        if not values_match(want, actual):
            mismatches.append(f"{key} {field}")
    return mismatches


def _ensure_templates(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    fixtures: dict[str, Any],
    groups: dict[str, str],
) -> None:
    """Publish the six SYN standard templates through an approved proposal.

    The create ACL on std_change_record_producer is answer=false. Approving a
    New Template proposal runs Generate Template On Approval, which inserts the
    producer, the version, and the template. The approval engine for this table
    is off, so admin sets approval=approved. There is no sysapproval_approver row.
    """
    catalog, category = _template_catalog(client)
    for spec in fixtures["templates"]:
        name = str(spec["name"])
        existing = client.get_table(
            "std_change_record_producer",
            query=f"name={name}",
            fields=["sys_id", "name", "template", "active"],
            limit=2,
        )
        if existing:
            _record_template(client, manifest, path, name, str(existing[0]["sys_id"]))
            _say(f"template present: {name}")
            continue
        _publish_template(client, manifest, path, spec, groups, catalog, category)
        _say(f"template created: {name}")
    save_manifest(path, manifest)


def _template_catalog(client: ServiceNowClient) -> tuple[str, str]:
    """Catalog and category from the out-of-box Replace printer toner producer."""
    rows = client.get_table(
        "std_change_record_producer",
        query="name=Replace printer toner",
        fields=["sys_id", "name", "category", "sc_catalogs"],
        limit=1,
    )
    if not rows:
        raise SeedError("standard template is missing: Replace printer toner")
    category = str(rows[0].get("category") or "")
    catalog = str(rows[0].get("sc_catalogs") or "").split(",")[0].strip()
    if not catalog or not category:
        raise SeedError("Replace printer toner has no catalog or category")
    return catalog, category


def _publish_template(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    spec: dict[str, Any],
    groups: dict[str, str],
    catalog: str,
    category: str,
) -> None:
    name = str(spec["name"])
    group_id = groups[str(spec["group"])]
    proposal = client.create_record(
        "std_change_proposal",
        {
            "short_description": name,
            "description": spec["description"],
            "proposal_type": "1",
            "template_name": name,
            "business_justification": spec["justification"],
            "template_value": _template_value(spec, group_id),
            "catalog": catalog,
            "category": category,
            "state": "1",
        },
    )
    proposal_id = str(proposal["sys_id"])
    add_record(manifest, "std_change_proposal", proposal_id, name)
    save_manifest(path, manifest)
    client.update_record(
        "std_change_proposal",
        proposal_id,
        {"state": "2", "approval": "approved"},
    )
    _record_template(client, manifest, path, name, "")


def _template_value(spec: dict[str, Any], group_id: str) -> str:
    pairs = (
        ("short_description", str(spec["short_description"])),
        ("description", str(spec["description"])),
        ("implementation_plan", str(spec["implementation_plan"])),
        ("backout_plan", str(spec["backout_plan"])),
        ("test_plan", str(spec["test_plan"])),
        ("assignment_group", group_id),
        ("justification", str(spec["justification"])),
        ("risk_impact_analysis", "Low"),
    )
    for key, value in pairs:
        if "^" in value or (key != "assignment_group" and "=" in value):
            raise SeedError(f"template value {key} cannot contain ^ or =")
    return "^".join(f"{key}={value}" for key, value in pairs)


def _record_template(
    client: ServiceNowClient,
    manifest: dict[str, Any],
    path: Path,
    name: str,
    producer_id: str,
) -> None:
    if not producer_id:
        found = client.get_table(
            "std_change_record_producer",
            query=f"name={name}",
            fields=["sys_id", "name", "template", "active"],
            limit=2,
        )
        if len(found) != 1:
            raise SeedError(f"template producer was not created: {name}")
        producer_id = str(found[0]["sys_id"])
        producer = found[0]
    else:
        producer = client.get_record(
            "std_change_record_producer",
            producer_id,
            fields=["sys_id", "name", "template", "active"],
        )
    if str(producer.get("active")).lower() not in {"true", "1"}:
        raise SeedError(f"template producer is inactive: {name}")
    template_id = str(producer.get("template") or "")
    if not template_id:
        bodies = client.get_table(
            "std_change_template",
            query=f"name={name}",
            fields=["sys_id", "name"],
            limit=2,
        )
        if len(bodies) != 1:
            raise SeedError(f"template body was not created: {name}")
        template_id = str(bodies[0]["sys_id"])
    versions = client.get_table(
        "std_change_producer_version",
        query=f"std_change_producer={producer_id}",
        fields=["sys_id"],
        limit=2,
    )
    if len(versions) != 1:
        raise SeedError(f"template version was not created: {name}")
    proposals = client.get_table(
        "std_change_proposal",
        query=f"template_name={name}",
        fields=["sys_id", "template_name"],
        limit=2,
    )
    if len(proposals) != 1:
        raise SeedError(f"template proposal was not recorded: {name}")
    add_record(manifest, "std_change_proposal", str(proposals[0]["sys_id"]), name)
    add_record(manifest, "std_change_record_producer", producer_id, name)
    add_record(manifest, "std_change_producer_version", str(versions[0]["sys_id"]), name)
    add_record(manifest, "std_change_template", template_id, name)
    save_manifest(path, manifest)


def _print_gate(client: ServiceNowClient, fixtures: dict[str, Any]) -> None:
    changes = fixtures["changes"]
    incidents = fixtures["incidents"]
    rows = [
        _gate_row(
            "change_request historical",
            _kind(changes, "historical"),
            _count(client, "change_request", "correlation_idSTARTSWITHSYN-CHG"),
            1500,
            False,
        ),
        _gate_row(
            "change_request open",
            _kind(changes, "open"),
            _count(client, "change_request", "correlation_idSTARTSWITHSYN-OPEN"),
            25,
            False,
        ),
        _gate_row(
            "change_request release",
            sum(1 for row in changes if row["release"]),
            _count(client, "change_request", "correlation_idSTARTSWITHSYN-REL"),
            20,
            False,
        ),
        _gate_row(
            "incident",
            len(incidents),
            _count(client, "incident", "correlation_idSTARTSWITHSYN-INC"),
            150,
            True,
        ),
        _gate_row(
            "incident p1",
            sum(1 for row in incidents if row["priority"] == "1"),
            _count(client, "incident", "correlation_idSTARTSWITHSYN-INC^priority=1"),
            10,
            True,
        ),
        _gate_row(
            "cmdb_ci",
            len(fixtures["cis"]),
            _count(client, "cmdb_ci", CI),
            300,
            False,
        ),
        _gate_row(
            "cmdb_rel_ci",
            len(fixtures["relationships"]),
            _count(client, "cmdb_rel_ci", RELATIONSHIP),
            600,
            True,
        ),
        _gate_row(
            "sys_user_group",
            len(fixtures["groups"]),
            _count(client, "sys_user_group", GROUP),
            6,
            False,
        ),
        _gate_row(
            "sys_user",
            len(fixtures["users"]),
            _seed_user_count(client, fixtures),
            40,
            False,
        ),
        _gate_row(
            "cmn_schedule",
            len(fixtures["schedules"]),
            _count(client, "cmn_schedule", SCHEDULE),
            2,
            False,
        ),
        _gate_row(
            "task_ci",
            len(fixtures["task_ci"]),
            _count(client, "task_ci", TASK_CI),
            2400,
            True,
        ),
    ]
    failed = False
    for label, fixture_count, pdi_count, target, about in rows:
        within = fixture_count == pdi_count and _within(fixture_count, target, about)
        failed = failed or not within
        mark = "yes" if within else "no"
        _say(f"{label} fixture={fixture_count} pdi={pdi_count} target={target} within={mark}")
    caused = sum(1 for row in incidents if row.get("caused_by"))
    parent_used = _count(client, "incident", f"{INCIDENT}^parentISNOTEMPTY")
    _say(
        f"incident caused_by fixture={caused} loaded=0 "
        f"pdi_parent={parent_used} decision=open"
    )
    if parent_used:
        failed = True
    resolved_query = f"{INCIDENT}^stateIN6,7"
    resolved_closed = _count(client, "incident", resolved_query)
    resolved_empty = _count(client, "incident", f"{resolved_query}^resolved_atISEMPTY")
    resolved_early = _count(
        client, "incident", f"{resolved_query}^resolved_atLT_FIELDopened_at"
    )
    _say(
        f"incident resolved_or_closed={resolved_closed} "
        f"resolved_at_empty={resolved_empty} resolved_before_opened={resolved_early}"
    )
    if resolved_empty or resolved_early:
        failed = True
    template_rows = (
        ("std_change_record_producer", TEMPLATE),
        ("std_change_proposal", PROPOSAL),
        ("std_change_producer_version", STD_VERSION),
        ("std_change_template", STD_TEMPLATE),
    )
    template_count = len(fixtures["templates"])
    for label, query in template_rows:
        pdi_count = _count(client, label, query)
        within = pdi_count == template_count == 6
        failed = failed or not within
        mark = "yes" if within else "no"
        _say(f"{label} fixture={template_count} pdi={pdi_count} target=6 within={mark}")
    freezes = _count(client, "cmn_schedule_blackout", BLACKOUT)
    _say(f"cmn_schedule_blackout fixture=0 pdi={freezes} target=2 exception=policy code")
    if failed or freezes:
        if failed:
            raise SeedError("fixture counts are not equal to the PDI or are outside the target")
        raise SeedError("unexpected synthetic blackouts are present")


def _print_samples(client: ServiceNowClient, fixtures: dict[str, Any]) -> None:
    change_fields = [
        "number",
        "state",
        "type",
        "active",
        "approval",
        "opened_at",
        "start_date",
        "work_end",
        "closed_at",
        "close_code",
        "short_description",
    ]
    incident_fields = [
        "number",
        "state",
        "active",
        "opened_at",
        "resolved_at",
        "closed_at",
        "close_code",
        "short_description",
    ]
    for key in fixtures["samples"]["changes"]:
        _print_sample(client, "change_request", key, change_fields)
    for key in fixtures["samples"]["incidents"]:
        _print_sample(client, "incident", key, incident_fields)


def _print_sample(
    client: ServiceNowClient, table: str, key: str, fields: list[str]
) -> None:
    rows = client.get_table(table, query=f"correlation_id={key}", fields=fields, limit=1)
    if not rows:
        raise SeedError(f"sample was not found: {key}")
    parts = [f"{field}={rows[0].get(field) or ''}" for field in fields]
    _say(f"sample {table} {key} " + " ".join(parts))


def _check_fields_resolution(
    row: dict[str, Any],
    ids: dict[str, str],
    cis: dict[str, str],
    groups: dict[str, str],
) -> dict[str, object]:
    expected = _expected_change(row, ids)
    expected["cmdb_ci"] = cis[row["cmdb_ci"]]
    expected["assignment_group"] = groups[row["assignment_group"]]
    return expected


def _load_check(
    client: ServiceNowClient,
    fixtures: dict[str, Any],
    ids: dict[str, str],
    cis: dict[str, str],
    groups: dict[str, str],
    users: dict[str, str],
) -> None:
    """Compare stored rows with fixture values. Reference fields use sys_ids."""
    requester = _role_user(fixtures, users, "service_desk")
    changes = _index_rows(
        client,
        "change_request",
        "correlation_idSTARTSWITHSYN-",
        ["correlation_id", *CHANGE_CHECK],
    )
    incidents = _index_rows(
        client,
        "incident",
        "correlation_idSTARTSWITHSYN-",
        ["correlation_id", *INCIDENT_CHECK],
    )
    mismatches: list[str] = []
    for row in fixtures["changes"]:
        stored = changes.get(row["key"])
        if stored is None:
            mismatches.append(f"{row['key']} missing")
            continue
        expected = _check_fields_resolution(row, ids, cis, groups)
        expected["requested_by"] = requester
        mismatches.extend(_diff(row["key"], expected, stored))
    for row in fixtures["incidents"]:
        stored = incidents.get(row["key"])
        if stored is None:
            mismatches.append(f"{row['key']} missing")
            continue
        expected = _expected_incident(row, ids)
        expected["cmdb_ci"] = cis[row["cmdb_ci"]]
        expected["caller_id"] = requester
        mismatches.extend(_diff(row["key"], expected, stored))
    empty_changes = client.count("change_request", "correlation_idSTARTSWITHSYN-^numberISEMPTY")
    empty_incidents = client.count("incident", "correlation_idSTARTSWITHSYN-^numberISEMPTY")
    _say(f"number empty changes={empty_changes} incidents={empty_incidents}")
    if empty_changes or empty_incidents or mismatches:
        preview = "; ".join(mismatches[:5])
        raise SeedError(f"field check failed ({len(mismatches)}): {preview}")
    change_count = len(fixtures["changes"])
    incident_count = len(fixtures["incidents"])
    _say(f"field check: changes={change_count} incidents={incident_count} ok")


def _index(client: ServiceNowClient, table: str, query: str, field: str) -> dict[str, str]:
    rows = _index_rows(client, table, query, ["sys_id", field])
    return {key: str(row["sys_id"]) for key, row in rows.items()}


def _index_rows(
    client: ServiceNowClient, table: str, query: str, fields: list[str]
) -> dict[str, dict[str, Any]]:
    key_field = "correlation_id" if "correlation_id" in fields else fields[1]
    rows = client.get_records(
        table,
        query=query,
        fields=fields,
        page_size=200,
        max_records=5000,
    )
    return {str(row[key_field]): row for row in rows if row.get(key_field)}


def _count(client: ServiceNowClient, table: str, query: str) -> int:
    try:
        return client.count(table, query)
    except ServiceNowError:
        return len(
            client.get_records(
                table, query=query, fields=["sys_id"], page_size=200, max_records=5000
            )
        )


def _seed_user_count(client: ServiceNowClient, fixtures: dict[str, Any]) -> int:
    rows = client.get_records(
        "sys_user",
        query="user_nameSTARTSWITHsyn.",
        fields=["user_name"],
        page_size=100,
        max_records=200,
    )
    names = {str(row.get("user_name")) for row in rows}
    return sum(1 for user in fixtures["users"] if user["user_name"] in names)


def _within(count: int, target: int, about: bool) -> bool:
    if not about:
        return count == target
    return abs(count - target) <= target * 0.10


def _kind(changes: list[dict[str, Any]], kind: str) -> int:
    return sum(1 for row in changes if row["kind"] == kind)


def _gate_row(
    label: str,
    fixture_count: int,
    pdi_count: int,
    target: int,
    about: bool,
) -> tuple[str, int, int, int, bool]:
    return (label, fixture_count, pdi_count, target, about)


def _role_user(fixtures: dict[str, Any], users: dict[str, str], role: str) -> str:
    for user in fixtures["users"]:
        if user["role"] == role:
            return users[user["user_name"]]
    raise SeedError(f"no seeded user has role {role}")


def _wall(text: str) -> str:
    if not text:
        return ""
    return to_import_wall(text)


def _population(client: ServiceNowClient) -> int:
    queries = (
        ("change_request", CHANGE),
        ("incident", INCIDENT),
        ("cmdb_ci", CI),
        ("cmdb_rel_ci", RELATIONSHIP),
        ("task_ci", TASK_CI),
        ("sys_user", "user_nameSTARTSWITHsyn."),
        ("sys_user_group", GROUP),
        ("cmn_schedule", SCHEDULE),
        ("cmn_schedule_span", SPAN),
        ("sys_user_grmember", "user.user_nameSTARTSWITHsyn."),
        ("sys_import_set", IMPORT_SET),
        ("sys_db_object", STAGING_TABLE),
        ("std_change_record_producer", TEMPLATE),
        ("std_change_proposal", PROPOSAL),
        ("std_change_producer_version", STD_VERSION),
        ("std_change_template", STD_TEMPLATE),
    )
    return sum(_count(client, table, query) for table, query in queries)


def _blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


def _is_true(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "t", "yes"}


def _is_false(value: object) -> bool:
    return str(value).strip().lower() in {"false", "0", "f", "no"}


def _say(text: str) -> None:
    print(text, flush=True)
