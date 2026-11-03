"""Originals for the two approved out-of-box changes.

Seed reads each value and stores it once, before it writes the approved
target. A later seed does not replace that stored value. Teardown writes
the stored values back after the synthetic data rows are gone.
"""

from __future__ import annotations

from typing import Any

PROPERTY_KEY = "change.conflict.ci_maint_sched"
GLOBAL_CONDITION_KEY = "global_infrastructure_condition"
PROPERTY_TARGET = "true"
GLOBAL_CONDITION_TARGET = "nameNOT LIKEsyn-"


class OobError(RuntimeError):
    """A stored out-of-box value could not be written back."""


def record_oob_original(
    manifest: dict[str, Any],
    key: str,
    *,
    table: str,
    sys_id: str,
    field: str,
    value: str,
) -> bool:
    """Store the value read before a change. Return False when the key exists."""
    bucket = manifest.setdefault("oob_originals", {})
    if not isinstance(bucket, dict):
        raise OobError("oob_originals is not an object")
    if key in bucket:
        return False
    bucket[key] = {
        "table": table,
        "sys_id": sys_id,
        "field": field,
        "value": value,
    }
    return True


def restore_oob_originals(client: Any, manifest: dict[str, Any]) -> None:
    """Write every stored original back and read it back."""
    originals = manifest.get("oob_originals") or {}
    if not isinstance(originals, dict):
        raise OobError("oob_originals is not an object")
    for key, row in originals.items():
        if not isinstance(row, dict):
            raise OobError(f"oob original {key} is not an object")
        table = str(row.get("table") or "")
        sys_id = str(row.get("sys_id") or "")
        field = str(row.get("field") or "")
        value = "" if row.get("value") is None else str(row.get("value"))
        if not table or not sys_id or not field:
            raise OobError(f"oob original {key} is incomplete")
        client.update_record(table, sys_id, {field: value})
        stored = client.get_record(table, sys_id, fields=[field])
        actual = stored.get(field)
        if actual is None:
            actual = ""
        if str(actual) != value:
            raise OobError(f"oob original {key} read back {actual!r} after writing {value!r}")
