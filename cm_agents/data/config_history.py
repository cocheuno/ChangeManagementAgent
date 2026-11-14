"""Append-only history of configuration objects this project creates or deletes.

The file is ``data/synthetic/config_history.jsonl``, next to the manifest.
``.gitignore`` ignores ``data/synthetic/``. Teardown deletes the manifest and
does not delete this file.

Each line is one create or one delete: ``action``, ``table``, ``sys_id``,
``name``, and ``time``. The file cannot cover the 856 earlier import and
template customer updates. Those objects were created and deleted before this
file existed, and nothing here rewrites their ``sys_update_xml`` rows.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from cm_agents.data.import_time import UTC
from cm_agents.settings import repo_root

HISTORY_NAME = "config_history.jsonl"
CONFIG_TABLES = frozenset(
    {
        "cmn_schedule",
        "cmn_schedule_span",
        "sys_db_object",
        "sys_dictionary",
        "sys_documentation",
        "sys_transform_map",
        "sys_transform_entry",
        "sys_transform_script",
        "sys_import_set",
        "sys_template",
        "sys_update_xml",
        "std_change_proposal",
        "std_change_record_producer",
        "std_change_producer_version",
        "std_change_template",
        "sc_cat_item_catalog",
        "sc_cat_item_category",
    }
)
_SYS_ID = re.compile(r"^[0-9a-fA-F]{32}$")
_NAME_FIELDS: dict[str, tuple[str, ...]] = {
    "cmn_schedule": ("name",),
    "cmn_schedule_span": ("name",),
    "sys_db_object": ("name",),
    "sys_dictionary": ("name", "element"),
    "sys_documentation": ("name", "element"),
    "sys_transform_map": ("name",),
    "sys_transform_entry": ("source_field",),
    "sys_transform_script": ("when",),
    "sys_import_set": ("number",),
    "sys_template": ("name",),
    "sys_update_xml": ("name",),
    "std_change_proposal": ("template_name", "short_description"),
    "std_change_record_producer": ("name",),
    "std_change_producer_version": ("version",),
    "std_change_template": ("name",),
    "sc_cat_item_catalog": ("sc_cat_item",),
    "sc_cat_item_category": ("sc_cat_item",),
}


def config_history_path() -> Path:
    return repo_root() / "data" / "synthetic" / HISTORY_NAME


def is_config_sys_id(table: str, sys_id: str) -> bool:
    return table in CONFIG_TABLES and bool(_SYS_ID.fullmatch(sys_id))


def config_row_name(table: str, row: dict[str, Any]) -> str:
    """A stable label. Dictionary and documentation use ``name.element``."""
    if table in {"sys_dictionary", "sys_documentation"}:
        base = str(row.get("name") or "")
        element = str(row.get("element") or "")
        if base and element:
            return f"{base}.{element}"
        return base or element
    for key in (
        "name",
        "number",
        "source_field",
        "template_name",
        "short_description",
        "version",
        "when",
        "sc_cat_item",
    ):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def record_config(
    action: str,
    table: str,
    sys_id: str,
    name: str,
    when: datetime | None = None,
) -> None:
    """Append one line. Short ids and other tables are ignored.

    Unit tests use ids such as ``span1``. Those must not create the real file.
    """
    if action not in {"create", "delete"}:
        raise ValueError(f"config history action must be create or delete, not {action}")
    if not is_config_sys_id(table, sys_id):
        return
    moment = when or datetime.now(UTC)
    payload = {
        "action": action,
        "table": table,
        "sys_id": sys_id.lower(),
        "name": name,
        "time": moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"),
    }
    path = config_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def name_fields(table: str) -> tuple[str, ...]:
    return _NAME_FIELDS.get(table, ("name",))


def record_documentation(client: Any, table_name: str, element: str = "") -> None:
    """Record platform documentation created with a table or a column."""
    if element:
        query = f"name={table_name}^element={element}"
    else:
        query = f"name={table_name}^elementISEMPTY"
    rows = client.get_table(
        "sys_documentation",
        query=query,
        fields=["sys_id", "name", "element"],
        limit=20,
    )
    for row in rows:
        record_config(
            "create",
            "sys_documentation",
            str(row.get("sys_id") or ""),
            config_row_name("sys_documentation", row) or table_name,
        )


def record_matching(
    client: Any,
    table: str,
    query: str,
    name: str,
    *,
    name_field: str = "",
) -> None:
    """Record rows a platform step created. ``name`` is used when the row has none."""
    if table not in CONFIG_TABLES:
        return
    fields = ["sys_id"]
    if name_field:
        fields.append(name_field)
    rows = client.get_table(table, query=query, fields=fields, limit=20)
    for row in rows:
        label = str(row.get(name_field) or "") if name_field else ""
        record_config("create", table, str(row.get("sys_id") or ""), label or name)
