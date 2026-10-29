"""Delete the synthetic records and import artifacts recorded for this instance."""

from __future__ import annotations

from cm_agents.data.batch import BatchError, batch_delete
from cm_agents.data.manifest import load_manifest
from cm_agents.data.queries import (
    BLACKOUT,
    CHANGE,
    CI,
    DICTIONARY,
    GROUP,
    IMPORT_SET,
    INCIDENT,
    MEMBERSHIP,
    OWNED_MEMBERSHIP_GROUPS,
    PROPOSAL,
    RELATIONSHIP,
    ROLE,
    SCHEDULE,
    SPAN,
    STAGING_TABLE,
    STD_DELETE_MAP,
    STD_DELETE_STAGE,
    STD_TEMPLATE,
    STD_VERSION,
    TASK_CI,
    TEMPLATE,
    TRANSFORM_ENTRY,
    TRANSFORM_MAP,
    USER,
)
from cm_agents.servicenow.client import ServiceNowClient, ServiceNowError
from cm_agents.settings import Settings, repo_root

CHUNK = 40
USER_CHUNK = 15
# Data rows first. A membership or role query is not swept here: the integration
# user is put back into Conditional Script Writer as soon as that row is deleted.
SWEEPS_BEFORE_USERS = (
    ("cmdb_rel_ci", RELATIONSHIP),
    # Caused-by incidents point at changes. Emergency changes point at incidents.
    # Delete each child before the record it references.
    ("incident", f"{INCIDENT}^parentISNOTEMPTY"),
    ("change_request", f"{CHANGE}^parentISNOTEMPTY"),
    ("incident", INCIDENT),
    ("change_request", CHANGE),
    # Affected CI rows cannot be deleted while the change is read-only.
    # Deleting the change removes them.
    ("task_ci", TASK_CI),
)
SWEEPS_AFTER_USERS = (
    ("cmn_schedule_span", SPAN),
    ("cmdb_ci", CI),
    ("cmn_schedule", SCHEDULE),
    ("sys_user_group", GROUP),
    ("u_syn_chg_import", "sys_idISNOTEMPTY"),
    ("u_syn_inc_import", "sys_idISNOTEMPTY"),
    ("u_syn_taskci_import", "sys_idISNOTEMPTY"),
    ("sys_import_set", IMPORT_SET),
    ("sys_transform_entry", TRANSFORM_ENTRY),
    ("sys_transform_map", TRANSFORM_MAP),
    # Drop the staging table first. A direct dictionary delete is denied, and
    # dropping the table removes its columns.
    ("sys_db_object", STAGING_TABLE),
    ("sys_dictionary", DICTIONARY),
)
RECORD_ORDER = (
    "std_change_producer_version",
    "std_change_record_producer",
    "std_change_template",
    "std_change_proposal",
    "cmdb_rel_ci",
    "incident",
    "change_request",
    "task_ci",
    "sys_user_grmember",
    "sys_user_has_role",
    "sys_user",
    "cmn_schedule_span",
    "cmdb_ci",
    "cmn_schedule",
    "sys_user_group",
)
ARTIFACT_ORDER = (
    ("import_sets", "sys_import_set"),
    ("field_maps", "sys_transform_entry"),
    ("transform_maps", "sys_transform_map"),
    ("staging_tables", "sys_db_object"),
    ("dictionary", "sys_dictionary"),
    ("update_xml", "sys_update_xml"),
)
SYN_LEFT = (
    ("change_request", CHANGE),
    ("incident", INCIDENT),
    ("cmdb_ci", CI),
    ("cmdb_rel_ci", RELATIONSHIP),
    ("task_ci", TASK_CI),
    ("sys_user", USER),
    ("sys_user_grmember", MEMBERSHIP),
    ("sys_user_has_role", ROLE),
    ("sys_user_group", GROUP),
    ("cmn_schedule", SCHEDULE),
    ("cmn_schedule_span", SPAN),
    ("std_change_record_producer", TEMPLATE),
    ("std_change_proposal", PROPOSAL),
    ("std_change_producer_version", STD_VERSION),
    ("std_change_template", STD_TEMPLATE),
    ("cmn_schedule_blackout", BLACKOUT),
    ("sys_import_set", IMPORT_SET),
    ("sys_db_object", STAGING_TABLE),
    ("sys_dictionary", DICTIONARY),
)
UPDATE_XML_QUERY = (
    "nameLIKEu_syn_chg_import^ORnameLIKEu_syn_inc_import^ORnameLIKEu_syn_taskci_import"
    "^ORtarget_nameLIKEu_syn_chg_import^ORtarget_nameLIKEu_syn_inc_import"
    "^ORtarget_nameLIKEu_syn_taskci_import"
    "^ORnameLIKEu_syn_std_delete^ORtarget_nameLIKEu_syn_std_delete"
)
IMPORT_ROW = "06803e7b8c1103100a22deb6dd2b4e9c"
STANDARD_LEFT = (
    ("std_change_producer_version", STD_VERSION),
    ("std_change_record_producer", TEMPLATE),
    ("std_change_template", STD_TEMPLATE),
    ("std_change_proposal", PROPOSAL),
)


class TeardownError(Exception):
    """Synthetic rows are still present, or a baseline count moved."""


def teardown(settings: Settings) -> int:
    path = repo_root() / "data" / "synthetic" / "manifest.json"
    manifest = load_manifest(path)
    if manifest is None:
        print("manifest missing", flush=True)
        return 2
    baseline = manifest.get("baseline")
    if not isinstance(baseline, dict):
        raise TeardownError("manifest has no baseline")
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
        timeout=180,
    ) as client:
        for table, query in SWEEPS_BEFORE_USERS:
            print(f"sweep {table}", flush=True)
            _sweep(client, table, query)
        user_ids = _synthetic_user_ids(client, manifest)
        print(f"synthetic users: {len(user_ids)}", flush=True)
        _delete_owned_memberships(client, user_ids)
        _delete_direct_roles(client, user_ids)
        _delete_synthetic_users(client, user_ids)
        for table, query in SWEEPS_AFTER_USERS:
            print(f"sweep {table}", flush=True)
            _sweep(client, table, query)
        _delete_standard_catalog(client, manifest)
        _delete_recorded(client, manifest)
        for _ in range(4):
            if not _sweep(client, "sys_update_xml", UPDATE_XML_QUERY):
                break
        _verify(client, baseline)
        # incident.u_caused_by is a human-made column. Deleting the SYN
        # incidents clears its values. This does not delete the column.
        _require_caused_by_field(client)
    path.unlink()
    print("TEARDOWN OK", flush=True)
    return 0


def _sweep(client: ServiceNowClient, table: str, query: str) -> int:
    removed = 0
    while removed < 20000:
        try:
            rows = client.get_table(table, query=query, fields=["sys_id"], limit=100)
        except ServiceNowError as exc:
            if exc.status_code in {400, 404}:
                return removed
            raise
        ids = [str(row["sys_id"]) for row in rows if row.get("sys_id")]
        if not ids:
            return removed
        before = _match_count(client, table, query, len(ids))
        _delete_ids(client, table, ids)
        if _still_there(client, table, ids[0]):
            raise TeardownError(f"could not delete {table}")
        after = _match_count(client, table, query, before)
        if after >= before:
            raise TeardownError(
                f"{table} delete did not reduce the match count ({before} -> {after})"
            )
        removed += before - after
    raise TeardownError(f"too many {table} rows")


def _match_count(client: ServiceNowClient, table: str, query: str, fallback: int) -> int:
    try:
        return client.count(table, query)
    except ServiceNowError as exc:
        if exc.status_code in {400, 404}:
            return fallback
        raise


def keep_synthetic_user(user_name: str, email: str, sys_id: str, recorded: set[str]) -> bool:
    """True for a seeded user. A syn. prefix alone is not enough."""
    if not user_name.lower().startswith("syn."):
        return False
    if sys_id in recorded:
        return True
    return email.lower().endswith("@example.com")


def _synthetic_user_ids(client: ServiceNowClient, manifest: dict[str, object]) -> list[str]:
    recorded = _recorded_user_ids(manifest)
    rows = client.get_records(
        "sys_user",
        query=USER,
        fields=["sys_id", "user_name", "email"],
        page_size=100,
        max_records=200,
    )
    found: list[str] = []
    seen: set[str] = set()
    for row in rows:
        sys_id = str(row.get("sys_id") or "")
        if not sys_id or sys_id in seen:
            continue
        if not keep_synthetic_user(
            str(row.get("user_name") or ""),
            str(row.get("email") or ""),
            sys_id,
            recorded,
        ):
            continue
        seen.add(sys_id)
        found.append(sys_id)
    for sys_id in recorded:
        if sys_id in seen or not _still_there(client, "sys_user", sys_id):
            continue
        row = client.get_record("sys_user", sys_id, fields=["user_name", "email"])
        if keep_synthetic_user(
            str(row.get("user_name") or ""),
            str(row.get("email") or ""),
            sys_id,
            recorded,
        ):
            seen.add(sys_id)
            found.append(sys_id)
    return found


def _recorded_user_ids(manifest: dict[str, object]) -> set[str]:
    records = manifest.get("records")
    if not isinstance(records, dict):
        return set()
    rows = records.get("sys_user")
    if not isinstance(rows, list):
        return set()
    found: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not row.get("sys_id"):
            continue
        key = str(row.get("key") or "")
        if key == "integration" or key.lower().startswith("syn."):
            found.add(str(row["sys_id"]))
    return found


def _delete_owned_memberships(client: ServiceNowClient, user_ids: list[str]) -> None:
    """Delete memberships seed added. Leave the platform-managed group alone."""
    if not user_ids:
        return
    group_ids = _owned_group_ids(client)
    if not group_ids:
        return
    for chunk in _chunks(user_ids, USER_CHUNK):
        query = f"userIN{','.join(chunk)}^groupIN{','.join(sorted(group_ids))}"
        ids = _ids_for(client, "sys_user_grmember", query)
        if not ids:
            continue
        before = _match_count(client, "sys_user_grmember", query, len(ids))
        _delete_ids(client, "sys_user_grmember", ids)
        after = _match_count(client, "sys_user_grmember", query, before)
        if after > 0:
            raise TeardownError(
                f"synthetic memberships remain after delete ({before} -> {after})"
            )


def _owned_group_ids(client: ServiceNowClient) -> set[str]:
    found: set[str] = set()
    for name in OWNED_MEMBERSHIP_GROUPS:
        rows = client.get_table(
            "sys_user_group",
            query=f"name={name}",
            fields=["sys_id", "name"],
            limit=5,
        )
        for row in rows:
            if str(row.get("name") or "") == name and row.get("sys_id"):
                found.add(str(row["sys_id"]))
    return found


def _delete_direct_roles(client: ServiceNowClient, user_ids: list[str]) -> None:
    """Delete direct role grants. Inherited grants belong to the platform group."""
    for chunk in _chunks(user_ids, USER_CHUNK):
        query = f"userIN{','.join(chunk)}^inherited=false"
        ids = _ids_for(client, "sys_user_has_role", query)
        if not ids:
            continue
        before = _match_count(client, "sys_user_has_role", query, len(ids))
        _delete_ids(client, "sys_user_has_role", ids)
        after = _match_count(client, "sys_user_has_role", query, before)
        if after > 0:
            raise TeardownError(f"direct roles remain after delete ({before} -> {after})")


def _delete_synthetic_users(client: ServiceNowClient, user_ids: list[str]) -> None:
    for sys_id in user_ids:
        if not _still_there(client, "sys_user", sys_id):
            continue
        if _try_delete_user(client, sys_id) and not _still_there(client, "sys_user", sys_id):
            continue
        # One pass, including the platform-managed membership. Do not repeat it.
        _delete_ids(
            client,
            "sys_user_grmember",
            _ids_for(client, "sys_user_grmember", f"user={sys_id}"),
        )
        if _try_delete_user(client, sys_id) and not _still_there(client, "sys_user", sys_id):
            continue
        _delete_ids(
            client,
            "sys_user_has_role",
            _ids_for(client, "sys_user_has_role", f"user={sys_id}"),
        )
        _try_delete_user(client, sys_id)
        if _still_there(client, "sys_user", sys_id):
            raise TeardownError("could not delete synthetic user")


def _try_delete_user(client: ServiceNowClient, sys_id: str) -> bool:
    try:
        client.delete_record("sys_user", sys_id)
    except ServiceNowError as exc:
        if exc.status_code == 404:
            return True
        return False
    return True


def _ids_for(client: ServiceNowClient, table: str, query: str) -> list[str]:
    try:
        rows = client.get_records(
            table,
            query=query,
            fields=["sys_id"],
            page_size=200,
            max_records=500,
        )
    except ServiceNowError as exc:
        if exc.status_code in {400, 404}:
            return []
        raise
    return [str(row["sys_id"]) for row in rows if row.get("sys_id")]


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _still_there(client: ServiceNowClient, table: str, sys_id: str) -> bool:
    try:
        rows = client.get_table(table, query=f"sys_id={sys_id}", fields=["sys_id"], limit=1)
    except ServiceNowError as exc:
        if exc.status_code in {400, 404}:
            return False
        raise
    return bool(rows)


def _delete_standard_catalog(client: ServiceNowClient, manifest: dict[str, object]) -> None:
    """Remove SYN standard templates. Table API delete on these tables is denied.

    An onBefore transform script calls GlideRecord.deleteRecord. The staging
    table exists only for that call and is dropped before this function returns.
    """
    ids = _standard_ids(client, manifest)
    if ids:
        _transform_delete_ids(client, ids)
    _drop_template_stage(client)
    for table, _query in STANDARD_LEFT:
        for sys_id in ids:
            if _still_there(client, table, sys_id):
                raise TeardownError(f"could not delete {table}")


def _standard_ids(client: ServiceNowClient, manifest: dict[str, object]) -> list[str]:
    found: list[str] = []
    records = manifest.get("records")
    if isinstance(records, dict):
        for table, _query in STANDARD_LEFT:
            rows = records.get(table)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict) and row.get("sys_id"):
                    _add_sys_id(found, str(row["sys_id"]))
    for table, query in STANDARD_LEFT:
        for sys_id in _ids_for(client, table, query):
            _add_sys_id(found, sys_id)
    producers = [
        sys_id
        for sys_id in found
        if _still_there(client, "std_change_record_producer", sys_id)
    ]
    for producer_id in producers:
        for sys_id in _ids_for(
            client,
            "std_change_producer_version",
            f"std_change_producer={producer_id}",
        ):
            _add_sys_id(found, sys_id)
    return found


def _add_sys_id(found: list[str], sys_id: str) -> None:
    sys_id = sys_id.lower()
    if len(sys_id) != 32 or any(char not in "0123456789abcdef" for char in sys_id):
        raise TeardownError("refusing to delete an unexpected sys_id")
    if sys_id not in found:
        found.append(sys_id)


def _transform_delete_ids(client: ServiceNowClient, ids: list[str]) -> None:
    _drop_template_stage(client)
    quoted = ", ".join(f"'{sys_id}'" for sys_id in ids)
    script = (
        "// SYN standard template delete\n"
        "(function runTransformScript(source, map, log, target) {\n"
        f"  var ids = [{quoted}];\n"
        "  var tables = ['std_change_producer_version', 'std_change_record_producer', "
        "'std_change_template', 'std_change_proposal'];\n"
        "  for (var t = 0; t < tables.length; t++) {\n"
        "    for (var i = 0; i < ids.length; i++) {\n"
        "      var gr = new GlideRecord(tables[t]);\n"
        "      if (gr.get(ids[i])) {\n"
        "        gr.setWorkflow(false);\n"
        "        gr.deleteRecord();\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "  ignore = true;\n"
        "})(source, map, log, target);\n"
    )
    stage = client.create_record(
        "sys_db_object",
        {
            "label": STD_DELETE_MAP,
            "name": STD_DELETE_STAGE,
            "super_class": IMPORT_ROW,
            "create_access_controls": "false",
            "create_module": "false",
            "is_extendable": "false",
        },
    )
    table = str(stage.get("name") or STD_DELETE_STAGE)
    client.create_record(
        "sys_dictionary",
        {
            "name": table,
            "element": "u_target",
            "column_label": "target",
            "internal_type": "string",
            "max_length": "40",
            "active": "true",
        },
    )
    transform = client.create_record(
        "sys_transform_map",
        {
            "name": STD_DELETE_MAP,
            "source_table": table,
            "target_table": "std_change_proposal",
            "active": "true",
            "run_business_rules": "false",
            "run_script": "true",
            "enforce_mandatory_fields": "false",
            "order": "100",
        },
    )
    client.create_record(
        "sys_transform_script",
        {
            "map": str(transform["sys_id"]),
            "when": "onBefore",
            "active": "true",
            "order": "100",
            "script": script,
        },
    )
    try:
        client.request("POST", f"/api/now/import/{table}", json={"u_target": ids[0]})
    except ServiceNowError:
        pass


def _drop_template_stage(client: ServiceNowClient) -> None:
    map_ids = _ids_for(client, "sys_transform_map", f"name={STD_DELETE_MAP}")
    script_ids = _ids_for(client, "sys_transform_script", "scriptLIKE SYN standard template delete")
    for map_id in map_ids:
        script_ids.extend(
            _ids_for(client, "sys_transform_script", f"map={map_id}")
        )
    for sys_id in script_ids:
        _delete_quiet(client, "sys_transform_script", sys_id)
    for table, query in (
        ("sys_import_set", f"table_name={STD_DELETE_STAGE}"),
        ("sys_transform_map", f"name={STD_DELETE_MAP}"),
        ("sys_dictionary", f"name={STD_DELETE_STAGE}"),
        ("sys_db_object", f"name={STD_DELETE_STAGE}"),
        ("sys_update_xml", f"nameLIKE{STD_DELETE_STAGE}^ORtarget_nameLIKE{STD_DELETE_STAGE}"),
    ):
        for sys_id in _ids_for(client, table, query):
            _delete_quiet(client, table, sys_id)
    if _match_count(client, "sys_db_object", f"name={STD_DELETE_STAGE}", 1):
        raise TeardownError("template delete staging table remains")
    if _match_count(client, "sys_transform_map", f"name={STD_DELETE_MAP}", 1):
        raise TeardownError("template delete transform map remains")


def _delete_quiet(client: ServiceNowClient, table: str, sys_id: str) -> None:
    try:
        client.delete_record(table, sys_id)
    except ServiceNowError as exc:
        if exc.status_code in {403, 404}:
            return
        raise


def _delete_recorded(client: ServiceNowClient, manifest: dict[str, object]) -> None:
    records = manifest.get("records")
    if isinstance(records, dict):
        for table in RECORD_ORDER:
            rows = records.get(table)
            if not isinstance(rows, list):
                continue
            ids = [
                str(row["sys_id"])
                for row in rows
                if isinstance(row, dict) and row.get("sys_id")
            ]
            if table == "sys_user_group":
                ids = [
                    str(row["sys_id"])
                    for row in rows
                    if isinstance(row, dict) and str(row.get("key", "")).startswith("SYN")
                ]
            _delete_ids(client, table, ids)
    for bucket, table in ARTIFACT_ORDER:
        rows = manifest.get(bucket)
        if not isinstance(rows, list):
            continue
        ids = [str(row["sys_id"]) for row in rows if isinstance(row, dict) and row.get("sys_id")]
        _delete_ids(client, table, ids)


def _delete_ids(client: ServiceNowClient, table: str, sys_ids: list[str]) -> None:
    for offset in range(0, len(sys_ids), CHUNK):
        chunk = sys_ids[offset : offset + CHUNK]
        try:
            batch_delete(client, table, chunk)
        except (BatchError, ServiceNowError):
            for sys_id in chunk:
                _delete_one(client, table, sys_id)


def _delete_one(client: ServiceNowClient, table: str, sys_id: str) -> None:
    try:
        client.delete_record(table, sys_id)
    except ServiceNowError as exc:
        if exc.status_code == 404:
            return
        if table == "change_request":
            try:
                client.update_record(table, sys_id, {"parent": ""})
                client.delete_record(table, sys_id)
                return
            except ServiceNowError as retry:
                if retry.status_code == 404:
                    return
                raise TeardownError(str(retry)) from None
        raise TeardownError(str(exc)) from None


def _require_caused_by_field(client: ServiceNowClient) -> None:
    rows = client.get_table(
        "sys_dictionary",
        query="name=incident^element=u_caused_by",
        fields=["element", "column_label", "internal_type", "reference", "active"],
        limit=2,
    )
    if len(rows) != 1:
        raise TeardownError(f"incident.u_caused_by dictionary count is {len(rows)}")
    row = rows[0]
    if (
        row.get("internal_type") != "reference"
        or row.get("reference") != "change_request"
        or row.get("active") != "true"
        or row.get("column_label") != "Caused by Change"
    ):
        raise TeardownError("incident.u_caused_by is not the approved change reference")
    print(
        "incident.u_caused_by remains "
        f"element={row.get('element')} reference={row.get('reference')} "
        f"label={row.get('column_label')} active={row.get('active')}",
        flush=True,
    )


def _verify(client: ServiceNowClient, baseline: dict[str, object]) -> None:
    failed = False
    for table, query in SYN_LEFT:
        try:
            count = client.count(table, query)
        except ServiceNowError as exc:
            if exc.status_code in {400, 404}:
                count = 0
            else:
                raise
        print(f"{table} syn={count}", flush=True)
        failed = failed or count != 0
    for table, expected in baseline.items():
        actual = client.count(str(table))
        print(f"{table} total={actual} baseline={expected}", flush=True)
        failed = failed or actual != int(expected)
    if failed:
        raise TeardownError("synthetic rows remain or a baseline count changed")
