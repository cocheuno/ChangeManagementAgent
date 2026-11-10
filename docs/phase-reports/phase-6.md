# Phase 6 Report: Hardening and handover

Status: stopped before the two full cycles. Committed locally on `grok-build`. Not pushed.

The instance is still the Phase 1 seed (`anchor 2026-10-27`). This phase did not run teardown, seed, or `scenario run all`. `.env` is not in this commit. `config/policy.yaml` was not changed. `XAI_MODEL` was not changed. No system property was written. The Risk Calculator was not called. Agents do not write approvals. No role was granted.

The stop is the `sys_update_xml` check. `glide.db.instant_alter.enabled` is `true`. Admin wrote that customer update on 2026-10-21. It maps to neither a manifest record nor the two approved settings, and it is not the role grant or `incident.u_caused_by`.

## Preflight

`UV_PROJECT_ENVIRONMENT` was unset. The same command set it to `%LOCALAPPDATA%\venvs\ChangeManagementAgent`. No `.venv` was created in the repository. This is the suite before the Phase 6 code. The audited line landed on the pytest banner. Python for the later runs in this session is 3.13.2. The setup guide says 3.12.6. That guide was not edited.

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

## Offline suite after the Phase 6 code

`uv run ruff check cm_agents tests` printed `All checks passed!`.

`uv run pytest -m "not live"`:

```
152 passed, 14 deselected in 210.13s (0:03:30)
```

The 14 deselected tests are every test under `tests/live`. `uv run pytest` stays offline: a run with no `-m` does not collect that directory. `uv run pytest -m live` collects it. `-m` is not in addopts.

## What the code does

The readiness interrupt names every deterministic failure in one list: authorization, CI ownership, freeze, conflict, open P1/P2, and release notes. While any member is awaiting authorization, the list says plan quality was not checked. The plan-quality LLM call waits until the members are authorized. `tests/unit/test_release.py` covers a release that fails several checks at once. S06's assertions still require the authorization text. They do not require that text to be the only text. S06 was not run.

Seed writes `Production` and `Test` on `cmdb_ci.environment` and leaves stage empty. After a real load it prints the count of each stored value and the deployment frequency for each service next to that run's `ground_truth.json`. A mismatch raises `SeedError`. Seed was not run.

A rolled-back deploy leaves the previous version installed. `tests/unit/test_simulator.py` covers that, and it covers `reset_state` clearing a recorded PROD failure so a later deploy can proceed. Seed and teardown print `var/sim_state.json` and then delete it. Teardown then restores the two approved settings, prints the read-back, and counts `change_task` rows on `SYN-` changes. Teardown was not run.

`cm-agents scenario run all` runs S01, the closed S02 outcome, then S03 through S09. S10 is the same test as S09, so it runs once. Each passing file is followed by `remove_scenario_records`. `tests/live/test_s09.py` reads `period` from that cycle's `ground_truth.json` and requires `period.end` to equal the manifest anchor. The dates in `scenarios/S09.yaml` and `scenarios/S10.yaml` stay the original demo window.

`README.md` and `docs/RUNBOOK.md` point at `docs/setup/PDI_AND_WORKSTATION_SETUP.md` for setup. The runbook has the 15-minute demo for S01, S03, S07, S06, and the metrics report.

## Configuration evidence

The check queried `sys_update_xml` rows whose `sys_created_by` is the admin user or the integration user, and whose `sys_created_on` or `sys_updated_on` is on or after `2026-10-20 00:00:00`. The count was 595. All 595 are the admin user. The integration user has 0. Payloads were read only to classify a row, and they were not printed.

The run printed:

```
update_xml rows=595
update_xml hand_made=6
update_xml approved=2
update_xml manifest=119
update_xml orphan=468
```

The two approved rows are the property `change.conflict.ci_maint_sched` (`638460b6b70023008ef6eac7ee11a9f2`) and the Global Infrastructure condition (`0842df2437501000bff8e0f617733483`). The live property value read back as `true`.

Hand-made, listed on their own:

- `incident.u_caused_by` (setup guide Part B8). The customer updates are `sys_dictionary_incident_u_caused_by` (target `Incident.Caused by Change`), `sys_documentation_incident_u_caused_by_en` (the same target), and `sys_ui_section_bf1d96e3c0a801640190725e63f8ac80` (target `Incident`). The section row is the incident form. Its payload names the field.
- `snc_basic_auth_api_access` (setup guide Part B5). One `sys_user_has_role` row exists, created `2026-10-21 23:23:29` by admin, on the admin user. A payload search for `snc_basic_auth_api_access` returned 0 `sys_update_xml` rows, and the grant's sys_id is not in an update name. The grant is live. It has no customer update to map.

The first classifier also marked three seed rows as the incident field because the staging column is named `u_caused_by`: the `u_syn_inc_import` dictionary and documentation rows, and one `sys_transform_entry` whose target is `u_u_caused_by`. The matcher now ignores a `u_syn_` or import-table name, so those three stay with the other seed rows. The unit test covers that. The instance was not queried again after that change.

Rows that map to neither:

| What | Rows | Still on the instance |
|---|---:|---|
| `glide.db.instant_alter.enabled` | 1 | Yes. Value `true`. Customer update `INSERT_OR_UPDATE` at `2026-10-21 19:44:52`. Updated by admin at `2026-10-21 19:44:44`. |
| `SYN-PROBE service scope` blackouts | 4 | No. Each customer update is `DELETE`. `cmn_schedule_blackout` `nameSTARTSWITHSYN-PROBE` returned 0. |
| Import and template customer updates whose sys_id is not in the current manifest | 461 | The current manifest still has its own copies: 3 staging tables, 45 dictionary rows, 3 transform maps, 45 field maps, and 6 of each standard-change table. These 461 names are earlier copies. |
| `taxonomy.category.new_content_job_last_run` | 1 | Yes. Value `2026-11-08`. The customer update was created `2026-10-19 19:26:37`, before this window, and a job updated it `2026-11-08 08:00:58`. |
| `pwd_process` `Service-Desk Password Reset for Local ServiceNow` | 1 | The customer update was created `2026-10-19 19:26:45` and updated `2026-11-09 08:00:55`. The record sys_id is the out-of-box id `4ff0c881bf220100710071a7bf0739fa`. The payload was not printed. |

The 461 import and template names are 279 `sys_transform_entry`, 24 `sys_transform_map`, 24 `sys_db_object`, 19 `sc_cat_item_catalog`, 19 `sc_cat_item_category`, 19 `std_change_record_producer`, 19 `std_change_template`, 5 `sys_transform_script`, 3 `sys_template`, and the `u_syn_` dictionary and documentation rows. The manifest's `update_xml` list is empty. Seed records the record sys_id, and the current copies are the 119 rows that matched. Teardown's update-xml sweep only names `u_syn_` import and delete tables, so a replaced field map's customer update stays behind.

`glide.db.instant_alter.enabled` is the row that stops this phase. It is a live system property. This phase did not change it, and it is not one of the two approved settings.

## Cycles, cost, and time

Not run. There is no per-scenario token count and no cycle wall clock. `CM_AGENTS_RUN` was not set. The audit log was not summarized.

## Files

- `cm_agents/agents/release.py` — every deterministic readiness failure in one list. Plan quality waits for authorization.
- `tests/unit/test_release.py` — one release fails authorization, CI ownership, freeze, conflict, an open incident, and notes together.
- `cm_agents/data/load.py` — prints simulator state, resets it, and compares environment counts and deployment frequency with `ground_truth.json`.
- `cm_agents/data/teardown.py` — prints simulator state, resets it, prints the restored settings, and counts remaining change tasks.
- `cm_agents/deploy/simulator.py` — `describe_state`, `reset_state`, and `installed_version`.
- `tests/unit/test_simulator.py` — rollback keeps `v1`, and reset allows a later PROD deploy.
- `cm_agents/scenarios.py` — `scenario run S01` through `S10`, and `all`.
- `cm_agents/cli.py` — the `scenario` command.
- `tests/unit/test_scenarios.py` — `all` runs each scenario file once and stops on the first failure.
- `cm_agents/data/update_xml.py` — the customer-update classification.
- `tests/unit/test_update_xml.py` — manifest, approved, hand-made, and the staging column.
- `tests/conftest.py` — marks `tests/live` as `live` and skips that directory when no `-m` is set.
- `tests/unit/test_live_marker.py` — default and `-m "not live"` omit `test_s01.py`. `-m live` collects it.
- `pyproject.toml` — `testpaths` includes `tests/live`, and the `live` marker is registered.
- `tests/live/test_s09.py` — the metrics window is the manifest anchor and that cycle's ground truth.
- `scenarios/S09.yaml` and `scenarios/S10.yaml` — comments only. The original dates stay.
- `README.md` and `docs/RUNBOOK.md` — setup is a link. The runbook has the demo.
- `docs/ASSUMPTIONS.md` — Open records the stop.
- `docs/phase-reports/phase-6.md` — this report.

## Dependencies

No new dependency. `pyproject.toml` gained the pytest marker and the live test path. `uv.lock` was not changed.

## Deviations

1. The two full cycles were not run. The customer-update check returned a live system property that maps to neither list.
2. The basic-auth role grant has no `sys_update_xml` row. The live `sys_user_has_role` row is the evidence for Part B5.
3. The check's date test includes `sys_updated_on`, so two records created on 2026-10-19 appear because a later job updated them.

## Open

The cycles stay blocked until `glide.db.instant_alter.enabled` is accepted or reverted. This phase did not revert it.

The 461 earlier import and template customer updates, and the four `SYN-PROBE` delete updates, also map to neither the current manifest nor the two approved settings. The probe blackout rows themselves are gone. Teardown does not sweep those customer updates today.

Phase 4 left `CHG0039427` through `CHG0039431` (thread `SYN-S06-cdb4dbcf`). `remove_scenario_records` deletes them. The Phase 1 seed was not torn down.

`syn-ful-api` can still be on `failed_prod` in `var/sim_state.json` from the earlier S07 run. Seed and teardown now print that state and delete the file. Neither command was run.

## What this phase did not do

Stopped after the local commit. The gate `teardown → seed → scenario run all` was not run for seed 7 or seed 42. The instance was not left on a fresh seed 42. `docs/setup/PDI_AND_WORKSTATION_SETUP.md`, `config/policy.yaml`, and `XAI_MODEL` were not edited. The risk endpoint was not called. No agent wrote an approval. No plugin was activated. The normal change model was not edited. No standard template and no proposal was created. No role was granted. No `.venv` was created in the repository.
