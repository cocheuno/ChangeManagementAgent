import pytest

from cm_agents.data.load import INCIDENT_CHECK, INCIDENT_FIELDS
from cm_agents.data.queries import DICTIONARY, OWNED_MEMBERSHIP_GROUPS
from cm_agents.data.teardown import (
    ARTIFACT_ORDER,
    SWEEPS_AFTER_USERS,
    SWEEPS_BEFORE_USERS,
    TeardownError,
    _sweep,
    keep_synthetic_user,
)


def test_owned_membership_groups_skip_the_platform_group() -> None:
    assert "Change Management" in OWNED_MEMBERSHIP_GROUPS
    assert "CAB Approval" in OWNED_MEMBERSHIP_GROUPS
    assert "eCAB Approval" in OWNED_MEMBERSHIP_GROUPS
    assert "SYN Store DevOps" in OWNED_MEMBERSHIP_GROUPS
    assert "Conditional Script Writer" not in OWNED_MEMBERSHIP_GROUPS


def test_keep_synthetic_user_requires_our_email_or_the_manifest() -> None:
    assert keep_synthetic_user("syn.ada.lovelace", "syn.ada.lovelace@example.com", "a", set())
    assert keep_synthetic_user("syn.svc", "other@example.org", "a", {"a"})
    assert not keep_synthetic_user("syn.other", "other@example.org", "b", set())
    assert not keep_synthetic_user("Synaptics", "synaptics@example.com", "c", set())


class _Stuck:
    def __init__(self) -> None:
        self.calls = 0

    def get_table(self, table: str, **_kwargs: object) -> list[dict[str, str]]:
        self.calls += 1
        return [{"sys_id": "row-1"}]

    def count(self, table: str, query: str | None = None) -> int:
        return 1


def test_sweep_stops_when_a_delete_does_not_reduce_the_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cm_agents.data.teardown._delete_ids", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("cm_agents.data.teardown._still_there", lambda *_args, **_kwargs: False)
    client = _Stuck()
    with pytest.raises(TeardownError, match="did not reduce"):
        _sweep(client, "sys_user_grmember", "user.user_nameSTARTSWITHsyn.")
    assert client.calls == 1


def test_affected_cis_are_removed_with_the_change() -> None:
    last_change = max(
        index
        for index, (table, _query) in enumerate(SWEEPS_BEFORE_USERS)
        if table == "change_request"
    )
    task_ci = next(
        index for index, (table, _query) in enumerate(SWEEPS_BEFORE_USERS) if table == "task_ci"
    )
    assert last_change < task_ci


def test_teardown_does_not_delete_the_human_caused_by_field() -> None:
    assert "name=incident" not in DICTIONARY
    assert "u_caused_by" not in DICTIONARY
    assert ("u_caused_by", "reference", "change_request") in INCIDENT_FIELDS
    assert "u_caused_by" in INCIDENT_CHECK


def test_staging_table_is_dropped_before_its_dictionary_rows() -> None:
    tables = [table for table, _query in SWEEPS_AFTER_USERS]
    assert tables.index("sys_db_object") < tables.index("sys_dictionary")
    buckets = [bucket for bucket, _table in ARTIFACT_ORDER]
    assert buckets.index("staging_tables") < buckets.index("dictionary")


def test_sweep_finishes_when_the_query_is_empty() -> None:
    class _Empty:
        def get_table(self, table: str, **_kwargs: object) -> list[dict[str, str]]:
            return []

    assert _sweep(_Empty(), "cmdb_ci", "nameSTARTSWITHsyn-") == 0  # type: ignore[arg-type]
