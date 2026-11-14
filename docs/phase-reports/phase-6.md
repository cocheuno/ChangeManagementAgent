# Phase 6 Report: Hardening and handover

Status: both full cycles passed. Committed locally on `grok-build`. Not pushed.

The instance is seed 42, anchor `2026-10-27 00:00:00`. There was no teardown after that seed. The approved settings are applied: `change.conflict.ci_maint_sched` is `true`, and the Global Infrastructure maintenance condition is `nameNOT LIKEsyn-`. The manifest still stores the originals `false` and an empty condition. `.env` is not in this commit. `config/policy.yaml` was not changed. `XAI_MODEL` was not changed. The runtime model id in the audit log is `grok-4.7`. The Risk Calculator was not called. Agents do not write approvals. No role was granted. `glide.db.instant_alter.enabled` was not changed. It is still `true`. The review section classifies it as changed outside this project's code.

## Preflight

`UV_PROJECT_ENVIRONMENT` was unset at the start of the phase. The same command set it to `%LOCALAPPDATA%\venvs\ChangeManagementAgent`. No `.venv` was created in the repository. This is the suite before the Phase 6 code. The audited line landed on the pytest banner. Python for the later runs is 3.13.2. The setup guide says 3.12.6. That guide was not edited.

```
UV_PROJECT_ENVIRONMENT=C:\Users\caronet\AppData\Local\venvs\ChangeManagementAgent
===== uv sync =====
Resolved 66 packages in 17ms
===== pytest =====Audited
65 packages in 467ms
collected 143 items
============================ 143 passed in 29.03s =============================
===== doctor =====
admin login: ok
instance build: glide.war=glide-australia-02-11-2026__patch3-05-25-2026_06-12-2026_1106.zip
agent user: present
```

The doctor plugin list matches Phase 4 and Phase 5. Change Success Score stays inactive. The Risk Calculator stays active. ReleaseOps stays inactive. `com.snc.release_management_read_roles` stays active. There is no `rm_release` plugin.

## Offline suite

`uv run ruff check cm_agents tests` printed `All checks passed!`.

After the first Phase 6 commit, `uv run pytest -m "not live" -q --tb=line`:

```
152 passed, 14 deselected in 210.13s (0:03:30)
```

After the teardown and actual-date fixes, the same command, before either cycle:

```
170 passed, 14 deselected in 225.37s (0:03:45)
```

The 14 deselected tests are every test under `tests/live`. `uv run pytest` stays offline. `uv run pytest -m live` collects that directory. `-m` is not in addopts.

The gate's own doctor, immediately before the first teardown:

```
admin login: ok
instance build: glide.buildname and glide.buildtag were not found; glide.war=glide-australia-02-11-2026__patch3-05-25-2026_06-12-2026_1106.zip
agent user: present
```

That step exited 0 in 17.1 seconds. The plugin list was the same.

## Anchor

Midnight UTC on the load date 2026-11-14 is refused. `generate(7)` raised `RuntimeError: anchor does not cover the fixed history calendar (SYN-CHG-0001 opened_at 2025-11-06 15:00:00)`. Both cycles passed `--anchor 2026-10-27`. Each seed printed `anchor: 2026-10-27 00:00:00`. The fixture hashes differ:

```
seed 7  60112be56cf06df92ca4b9734225b88e9d189479735a9c3bf08a4ff0d6a6ed57
seed 42 9131ae609660986728b97188837af2b09efd165cd5a9952f5885cf4e9042007d
```

## Cycles

`CM_AGENTS_RUN` was `phase6-seed7` for the first scenario run and `phase6-seed42` for the second. The gate stopped on a failing step. None failed. The process exited 0.

Cycle seed 7 wall clock was 4037.1 seconds. Teardown 1083.8, seed 1247.7, scenarios 1705.5.

The first teardown printed the simulator, restored the two stored originals, and found no change-model tasks left on `SYN-` changes:

```
simulator state: failed_prod=[] version_count=0
oob change.conflict.ci_maint_sched field=value value='false'
oob global_infrastructure_condition field=condition value=''
change_task on SYN changes=0
TEARDOWN OK
```

One `POST /api/now/v1/batch` failed before a response during the `u_syn_chg_import` sweep. The batch helper then deleted those rows one at a time. The SYN counts at the end were 0. `task_ci` printed `before_seed=730 baseline=733 already_later=3 created_after_seed=16`. Those 16 rows are newer than the seed clock and did not fail the check.

Seed 7 then printed:

```
simulator state: failed_prod=[] version_count=0
environment Production=184
environment Test=42
environment empty=74
frequency SYN HR Portal ground_truth=7.8 servicenow=7.8
frequency SYN Online Store ground_truth=7.9 servicenow=7.9
frequency SYN Order Fulfillment ground_truth=3.1 servicenow=3.1
frequency SYN Payments ground_truth=8.7 servicenow=8.7
load seconds: 1226.9
created: 5095
SEED OK
```

`scenario run all` started from `simulator state: failed_prod=[] version_count=0`. S01 through S09 each printed `1 passed`. S10 is the same file as S09. S06's first interrupt named the unauthorized member and the deferred plan-quality check:

```
detail: CHG0045596 failed the authorization check: awaiting authorization; plan quality was not checked because a member is awaiting authorization
```

S07 closed unsuccessful, linked the incident, and left the previous failure recorded until the next teardown:

```
s07 number=CHG0045597 state=3 close_code=unsuccessful
s07 incident number=INC0011789 u_caused_by=747e7761c3e85f50aef2be1d05013104 change_sys_id=747e7761c3e85f50aef2be1d05013104 priority=3 impact=2 urgency=2
s07 prod steps=['env=PROD step=canary_10 result=ok', 'env=PROD step=canary_100 result=failed']
```

S09 and S10 compared ServiceNow with that cycle's `ground_truth.json` for the period ending at the manifest anchor. The test passed in 27.04 seconds. `s09 seed change_task count=0`.

Cycle seed 42 wall clock was 3605.7 seconds. Teardown 1106.1, seed 1103.4, scenarios 1396.2.

The second teardown showed S07's simulator failure and then cleared it:

```
simulator state: failed_prod=['syn-ful-api'] version_count=19
oob change.conflict.ci_maint_sched field=value value='false'
oob global_infrastructure_condition field=condition value=''
change_task on SYN changes=0
TEARDOWN OK
```

Seed 42 printed the same environment counts and the same four frequencies, each matching that cycle's ground truth, then `load seconds: 1097.7`, `created: 5095`, and `SEED OK`. The scenario run again started from an empty simulator file. S01 through S09 each passed. S06 printed:

```
detail: CHG0047155 failed the authorization check: awaiting authorization; plan quality was not checked because a member is awaiting authorization
```

S07 printed `CHG0047156` closed `unsuccessful`, with `INC0011955` `u_caused_by` equal to that change. S09 passed in 30.53 seconds. There was no teardown after this seed.

A read after the gate, on `cmn_schedule_maintenance` named Global Infrastructure, returned condition `nameNOT LIKEsyn-`. `change.conflict.ci_maint_sched` read back `true`. The manifest originals are still `false` and `''`.

Both cycles' S09 metrics were:

| Metric | Value |
|---|---|
| Success | 93.9 |
| Failure | 6.1 |
| Lead time hours | 122.0 |
| MTTR hours | 4.0 |
| Release on time | 85.0 |
| Emergency ratio | 7.8 |
| Standard share | 43.8 |
| Success by type | standard 98.0, normal 91.6, emergency 85.3 |
| Weekly frequency | HR Portal 7.8, Online Store 7.9, Order Fulfillment 3.1, Payments 8.7 |
| Volume by service | HR Portal 439, Online Store 433, Order Fulfillment 171, Payments 498 |
| Volume by type | emergency 120, normal 746, standard 675 |

Monthly volume was 128, 131, 127, 127, 130, 130, 125, 129, 123, 122, 122, and 147 from 2025-11 through 2026-10. Each test asserted those numbers against that cycle's own `ground_truth.json`, and `period.end` against the manifest anchor.

## Configuration evidence

The check ran after seed 42, while that manifest was on disk. It queried `sys_update_xml` rows whose `sys_created_by` is the admin user or the integration user, and whose `sys_created_on` or `sys_updated_on` is on or after `2026-10-20 00:00:00`. Payloads were read only to classify a row, and they were not printed.

```
update_xml rows=988
update_xml hand_made=3
update_xml approved=2
update_xml manifest=120
update_xml orphan=863
```

The classifier returns 1 while any orphan remains. The orphan names are the categories already listed when this phase stopped, plus more copies of the same import and template customer updates. No new live configuration type appeared.

The two approved rows are `change.conflict.ci_maint_sched` and the Global Infrastructure condition. Hand-made, listed on their own:

- `incident.u_caused_by` (setup guide Part B8). Three customer updates: target `Incident`, and two with target `Incident.Caused by Change`.
- `snc_basic_auth_api_access` (setup guide Part B5). One live `sys_user_has_role` row. A payload search returned 0 `sys_update_xml` rows.

| What | Rows | Still on the instance |
|---|---:|---|
| `glide.db.instant_alter.enabled` | 1 | Yes. Value `true`. Inserted `2026-10-21 19:44:44` by admin. `sys_audit` has 0 rows. Changed outside this project's code. Left unchanged. |
| `taxonomy.category.new_content_job_last_run` | 1 | Yes. A scheduled job updates this out-of-box property. |
| `pwd_process` `Service-Desk Password Reset for Local ServiceNow` | 1 | The customer update names the out-of-box record. The payload was not printed. |
| `SYN-PROBE service scope` blackouts | 4 | No. Each customer update is `DELETE`. |
| Earlier import and template customer updates | 856 | The current manifest matches its own 120 rows. These names are earlier copies. |

The 856 names are 503 `sys_transform_entry`, 45 `sys_transform_map`, 46 `sys_db_object`, 49 `sc_cat_item_catalog`, 49 `sc_cat_item_category`, 49 `std_change_record_producer`, 49 `std_change_template`, 12 `sys_transform_script`, 3 `sys_template`, and 51 `u_syn_` documentation and dictionary rows. The count is higher than the 461 seen before the cycles because this gate seeded twice, and teardown does not delete a replaced field map's customer update. They were not deleted.

## Cost and time

From `var/audit.jsonl`, rows with `run` `phase6-seed7` or `phase6-seed42` and a model id. The model id is `grok-4.7`. Older phase runs were not included. The API key is not in the log. Latency is the sum of `latency_ms` on those calls.

| Scenario | Seed 7 calls | Seed 7 tokens | Seed 7 latency ms | Seed 42 calls | Seed 42 tokens | Seed 42 latency ms |
|---|---:|---:|---:|---:|---:|---:|
| S01 | 4 | 7524 | 22871 | 5 | 9116 | 24642 |
| S02 | 6 | 15228 | 68515 | 6 | 15747 | 70281 |
| S03 | 6 | 23780 | 150862 | 6 | 21570 | 124668 |
| S04 | 8 | 25117 | 138771 | 8 | 24322 | 128205 |
| S05 | 8 | 26177 | 157667 | 8 | 26027 | 140987 |
| S06 | 12 | 28410 | 100201 | 18 | 41811 | 171534 |
| S07 | 8 | 27024 | 136762 | 8 | 27333 | 140811 |
| S08 | 8 | 24240 | 135082 | 8 | 24075 | 134810 |
| S09 | 2 | 5665 | 23316 | 2 | 5362 | 17537 |
| Total | 62 | 183165 | 934047 | 69 | 195363 | 953475 |

Gate total: 131 calls, 378528 tokens, 1887522 ms of model latency. Cycle wall clocks are above: 4037.1 seconds for seed 7 and 3605.7 seconds for seed 42. S09 and S10 share one report invocation, so S10 is inside the S09 row.

## Files

- `cm_agents/agents/release.py` — every deterministic readiness failure in one list. Plan quality waits for authorization. A missing member risk is reported while a member awaits authorization. The review move stamps `work_end` first.
- `cm_agents/servicenow/changes.py` — `stamp_actual` writes the scenario clock and pulls a later platform `work_start` back with `work_end`.
- `cm_agents/agents/deployment.py` — uses `stamp_actual`.
- `cm_agents/servicenow/client.py` — a dropped GET is retried. A dropped write is not.
- `cm_agents/data/load.py` — prints simulator state, resets it, compares environment counts and deployment frequency, and clears schedule-span dictionary defaults on insert. A create of a configuration object is appended to the config history.
- `cm_agents/data/teardown.py` — prints simulator state, restores the two settings, counts change tasks, records `baseline_later`, and drops a leftover staging column by rebuilding the table. A delete of a configuration object is appended to the config history. The history file is not deleted.
- `cm_agents/data/config_history.py` — append-only `data/synthetic/config_history.jsonl`.
- `cm_agents/data/manifest.py` — stores `baseline_later`.
- `cm_agents/deploy/simulator.py` — `describe_state`, `reset_state`, and `installed_version`.
- `cm_agents/scenarios.py` and `cm_agents/cli.py` — `scenario run`.
- `cm_agents/data/update_xml.py` — the customer-update classification.
- `tests/conftest.py`, `tests/unit/test_live_marker.py`, and `pyproject.toml` — the `live` marker.
- `tests/live/test_s09.py` — the metrics window is the manifest anchor and that cycle's ground truth.
- `README.md` and `docs/RUNBOOK.md` — setup is a link. Both show `cm-agents seed --seed 42 --anchor 2026-10-27` and why that anchor is required.
- `docs/ASSUMPTIONS.md` — Open records the finished cycles.
- `docs/phase-reports/phase-6.md` — this report.

`data/synthetic/`, `reports/`, and `var/` stay gitignored.

## Dependencies

No new dependency. `pyproject.toml` gained the pytest marker and the live test path. `uv.lock` was not changed.

## Deviations

1. The load date 2026-11-14 cannot be the anchor. `SYN-CHG-0001` opens at `2025-11-06 15:00:00`, which is before that date minus 365 days. Both cycles pinned `2026-10-27`. S09 still read the anchor from the manifest.
2. The customer-update check still returns orphans. They are `glide.db.instant_alter.enabled` (changed outside this project's code), the taxonomy job property, the password-reset process, four deleted `SYN-PROBE` blackouts, and 856 earlier import and template customer updates. No new live configuration type appeared. The property was left unchanged, and the ghost rows were left in place.
3. The basic-auth role grant has no `sys_update_xml` row. The live `sys_user_has_role` row is the evidence for Part B5.
4. One batch delete on the first teardown lost the connection. The helper deleted those rows one at a time, and teardown still passed.

## Open

`glide.db.instant_alter.enabled` remains `true`. It is classified as changed outside this project's code. The 856 import and template customer updates remain. `data/synthetic/config_history.jsonl` cannot cover those 856 rows. Teardown still does not sweep a customer update whose name lacks `u_syn_`.

The integration user reads work notes and approval comments through `sys_journal_field` with `audit_viewer`. The `change_request.work_notes` field itself stays empty for that user.

## What this phase did not do

Did not push. Did not start Problem Management. Did not edit `docs/setup/PDI_AND_WORKSTATION_SETUP.md`, `config/policy.yaml`, or `XAI_MODEL`. The risk endpoint was not called. No agent wrote an approval. No plugin was activated. The normal change model was not edited. No role was granted. `glide.db.instant_alter.enabled` was not written. The ghost customer updates were not deleted. The instance was not torn down after seed 42. The review did not rerun the two cycles.

## Review

This review is on `7c97d3f`, the fast-forward of `origin/main` after pull request 6. The two cycles above stay as recorded.

### glide.db.instant_alter.enabled

Classification: changed outside this project's code. The property was left at `true`.

- `sys_properties` has one row, `sys_id` `d3b741c2c3001310aef2be1d0501317e`. `value` is `true`. `sys_created_on` and `sys_updated_on` are both `2026-10-21 19:44:44`. `sys_updated_by` is admin.
- `sys_audit` for that document key returned 0 rows. There is no audited old value and no audited new value.
- The customer update `sys_properties_d3b741c2c3001310aef2be1d0501317e` is `INSERT_OR_UPDATE`, created `2026-10-21 19:44:52` by admin, target `glide.db.instant_alter.enabled`. The payload value is `true`, type `boolean`, with those same timestamps. The payload has no old value.
- The first evidenced project write is the `SYN-PROBE service scope` blackout whose payload `sys_created_on` is `2026-10-21 23:56:39`. Its customer update is a `DELETE` created `2026-10-21 23:56:41`. A `sys_audit` search for `SYN-PROBE` before `2026-10-21 19:44:44` returned 0 rows.
- A search of `cm_agents/` and `tests/` for `instant_alter` returned no matches.

The same evidence is in `docs/DISCOVERY.md`.

### Config history

`data/synthetic/config_history.jsonl` sits next to the manifest. `.gitignore` ignores `data/synthetic/`. Teardown deletes the manifest and does not delete this file. Each line records one create or one delete: table, `sys_id`, name, and time. Seed appends a line when it creates a configuration object. Teardown appends a line when it deletes one.

This file cannot cover the 856 earlier import and template customer updates. Those objects were created and deleted before the file existed, and this review did not rewrite their `sys_update_xml` rows. Their classification by table stays:

| Table | Rows |
|---|---:|
| `sys_transform_entry` | 503 |
| `sys_transform_map` | 45 |
| `sys_db_object` | 46 |
| `sc_cat_item_catalog` | 49 |
| `sc_cat_item_category` | 49 |
| `std_change_record_producer` | 49 |
| `std_change_template` | 49 |
| `sys_transform_script` | 12 |
| `sys_template` | 3 |
| `u_syn_` documentation and dictionary | 51 |

The fresh check splits that last 51 into 48 `sys_documentation` and 3 `sys_dictionary`. This review did not seed or tear down, so the history file is not on disk yet. The next seed or teardown appends to it.

### Schedule span defaults

`docs/DISCOVERY.md` records that inserting a `cmn_schedule_span` with empty `float_day`, `float_week`, and `yearly_type` stores the defaults `1`, `1`, and `doy`, and that the following update clears them.

### README

`README.md` shows `cm-agents seed --seed 42 --anchor 2026-10-27`. The fixed history starts at `2025-11-06 15:00:00` UTC, and midnight on a load date after `2026-11-06` is refused.

### Member risk while authorization is pending

`readiness_failures` reports `{number} failed the member risk check: risk is missing` in the same list as the other deterministic readiness failures while a member awaits authorization. Plan quality stays deferred until every member is authorized. S06 was not run again. Its assertion still looks for `awaiting authorization` inside the detail.

### Offline suite

`uv run pytest -m "not live"` on Python 3.13.2:

```
collected 188 items / 14 deselected / 174 selected
================ 174 passed, 14 deselected in 66.15s (0:01:06) ================
```

### Customer-update check

The check ran again against the seed 42 manifest. It returned exit 1 because orphans remain. The totals match the check after the cycles:

```
update_xml rows=988
update_xml hand_made=3
update_xml approved=2
update_xml manifest=120
update_xml orphan=863
```

The 863 orphans are the same categories: 1 `glide.db.instant_alter.enabled`, 1 taxonomy job property, 1 password-reset process, 4 `SYN-PROBE` blackout deletes, and the 856 rows in the table above. No new live configuration type appeared. The classifier was not changed to hide `instant_alter`.
