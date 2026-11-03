# Phase 3 Report: Deployment and Review

Status: review fixes committed locally on `grok-build`. Not pushed. Stopped here. Phase 4 has not started.

The instance is still the Phase 1 seed (`anchor 2026-10-27`). This phase did not re-seed and did not run a full teardown. `.env` is not in this commit. `config/policy.yaml` was not changed. `XAI_MODEL` was not changed. The runtime model id in the audit log is `grok-4.7`. The Risk Calculator was not called. Agents do not write approvals. `admin` and `itil` were not granted.

## Preflight

`UV_PROJECT_ENVIRONMENT` was unset. The same command set it to `%LOCALAPPDATA%\venvs\ChangeManagementAgent`. No `.venv` was created in the repository. `uv sync` and `pytest` were one command. The audited line landed on the pytest banner. Both timing lines are from `uv sync`. This is the suite before the Phase 3 code.

```
UV_PROJECT_ENVIRONMENT=C:\Users\caronet\AppData\Local\venvs\ChangeManagementAgent
===== uv sync =====
Resolved 66 packages in 4ms
===== pytest =====Audited 65 packages in 328ms
collected 93 items
============================= 93 passed in 38.74s =============================
```

`cm-agents doctor` then printed the Australia build and `agent user: present`. The plugin list matches Phase 2.

```
admin login: ok
instance build: glide.buildname and glide.buildtag were not found; glide.war=glide-australia-02-11-2026__patch3-05-25-2026_06-12-2026_1106.zip
agent user: present
```

Python for these runs is 3.13.2. The setup guide says 3.12.6. That guide was not edited.

## Roles

Each candidate was granted on top of `sn_change_write`, exercised in a new ServiceNow session, and revoked. An earlier pass reused the session that signed in before the grant. httpx kept that cookie, so its journal negatives are not evidence. This is the fresh-session matrix. `caused_by_stuck=True` means the updated incident's `u_caused_by` still pointed at the change.

```
direct_before=sn_change_write
===== candidate task_editor =====
read_work_notes rows=0 marker_visible=False
read_approval_comments rows=0 marker_visible=False
create_incident=ok update_incident=ok caused_by_stuck=True
create_change_task=ok update_change_task=ok type=testing
===== candidate sn_incident_read =====
read_work_notes rows=0 marker_visible=False
read_approval_comments rows=0 marker_visible=False
create_incident=ok update_incident=ok caused_by_stuck=True
create_change_task=ok update_change_task=ok type=testing
===== candidate sn_incident_write =====
read_work_notes rows=0 marker_visible=False
read_approval_comments rows=0 marker_visible=False
create_incident=ok update_incident=ok caused_by_stuck=True
create_change_task=ok update_change_task=ok type=testing
===== candidate audit_viewer =====
read_work_notes rows=1 marker_visible=True
work_notes_field_marker=False
read_approval_comments rows=9 marker_visible=True
create_incident=ok update_incident=ok caused_by_stuck=True
create_change_task=ok update_change_task=ok type=testing
===== candidate itil =====
read_work_notes rows=0 marker_visible=False
read_approval_comments rows=0 marker_visible=False
create_incident=ok update_incident=ok caused_by_stuck=True
create_change_task=ok update_change_task=ok type=testing
direct_after=sn_change_write
probe_left=0
```

`sys_journal_field` read ACLs are: no roles, `audit_viewer`, and a script that requires `sn_hr_sp.esc_admin`. There is no `itil` ACL on that table. The `work_notes` column on the change stays empty. The journal row is the read path. Approval comments are the same journal, element `comments`.

`sn_change_write` already created and updated incidents, including `u_caused_by`, and created and updated change tasks. That role stays for those operations.

`audit_viewer` is the role that reads work notes and approval comments. It contains only the path `audit_admin` to `audit_viewer`. It was granted and kept.

The first live S05 and S07 runs then showed a field the matrix had not read back. Creating an incident with impact `1` and urgency `1` stored impact `1`, urgency `3`, priority `3`. The priority lookup is impact 1 + urgency 3 = priority 3. The only write ACL on `incident.urgency` names `sn_incident_write`. `incident.impact` also has an ACL with no role, which is why impact stuck and urgency did not. `sn_incident_write` contains `email_composer`, `sn_nb_action.next_best_action_user`, `sn_itsm_contact_query`, `sn_incident_read`, `sn_uib_collab.user`, `template_editor`, and `sn_gd_guidance.guidance_user`. It does not contain `admin` or `itil`. `itil` contains `sn_incident_write`, so `itil` is wider, and the fresh-session test already showed `itil` does not read the journal.

After granting `sn_incident_write` and signing in again:

```
granted sn_incident_write
direct roles: sn_change_write, audit_viewer, sn_incident_write
before priority=3 impact=1 urgency=3
after priority=1 impact=1 urgency=1 state=1
```

The agent does not write priority. Impact `1` and urgency `1` calculate to priority `1`.

| Role | Operation that needs it |
|---|---|
| `sn_change_write` | Create and update incidents, including `u_caused_by`. Create and update change tasks. The Phase 2 change writes. |
| `audit_viewer` | Read work notes and approval comments on `sys_journal_field`. |
| `sn_incident_write` | Write `incident.urgency`, so the priority lookup can produce a P1 or the tier pair the deployment agent sends. |

`admin`, `change_manager`, `itil_admin`, `sn_change_admin`, `sn_hr_sp.esc_admin`, and `incident_manager` were not granted. `discover.py` can still grant `itil` on a 403 for its throwaway user. Discover was not run.

## Scenario records

A scenario or agent row is a `change_request` or `incident` whose `correlation_id` starts with `SYN-` and does not start with `SYN-CHG-`, `SYN-OPEN-`, `SYN-REL-`, or `SYN-INC-`. Thread ids `SYN-` plus hex, and `SYN-S01-` through `SYN-S07-`, match that query. The S05 trigger uses `SYN-SCN-S05-trigger`. A deployment incident uses the thread id, not `SYN-INC-`.

`counts_in_metrics` is true only for the four seed prefixes. `metric_change_query` and `metric_incident_query` use those prefixes. Phase 5 cannot count a scenario row by querying the broad `SYN-` change or incident query. Change tasks are removed with the parent change. A direct `task_ci` delete is aborted by `Change Model: Read only CI (Delete)`, so teardown does not delete `task_ci` itself. Deleting the change removes those rows.

`remove_scenario_records` prints the matches, refuses a row that `counts_in_metrics` accepts, deletes them, and raises if any remain. `teardown()` calls it before the seed sweeps. The full teardown was not run. The five Phase 2 changes were removed this way:

```
scenario changes=5 scenario incidents=0
scenario CHG0039311 correlation_id=SYN-S04A-114cdd6d
scenario CHG0039312 correlation_id=SYN-S04B-7288c690
scenario CHG0039313 correlation_id=SYN-S08C-c4538dba
scenario CHG0039314 correlation_id=SYN-S08I-1a7a43d2
scenario CHG0039315 correlation_id=SYN-S02-eb66bb0a
scenario changes remaining=0 scenario incidents remaining=0
```

The first delete attempt returned HTTP 403 on `task_ci`. The retry, after skipping that delete, is the output above. The first passing gate then created `CHG0039339` through `CHG0039343`, plus `INC0010998` and `INC0010999`. Before this review's gate, `remove_scenario_records` deleted those seven rows and printed remaining 0. The rows this gate left are listed under Open.

## Maintenance windows

The first conflict probe flagged Saturday 22:00 Eastern and cleared Saturday 17:00 Eastern. That looked like a UTC reading of the span text. The span was already the Eastern wall clock. `change.conflict.ci_maint_sched` defaults to false, so the checker ignored the CI's `maintenance_schedule`. `Global Infrastructure` is demo data, with an empty condition, and its span is Saturday 01:00–04:00. That demo window supplied `not_in_maintenance_window`.

`_ensure_schedules` updates the existing spans in place. It does not rewrite the wall clock to UTC. A UTC instant would put Saturday 22:00 Eastern outside the window in June. The same path sets `change.conflict.ci_maint_sched` to true and, when the demo condition is empty, sets it to `nameNOT LIKEsyn-`. `float_day`, `float_week`, and `yearly_type` are cleared. `is_legacy_schedule` stays true. This was not a full reseed. After that path, both schedules read back as `US/Eastern`:

```
span SYN Saturday night 20110101T220000 20110102T040000 days 6
span SYN Tuesday evening 20110104T200000 20110104T230000 days 2
span SYN Thursday evening 20110106T200000 20110106T230000 days 4
```

Four probe changes on `syn-shared-sqlclu-prd-01`, then deleted. November 7 2026 is Eastern Standard Time. June 6 2026 is Eastern Daylight Time. The flagged schedule is the SYN tier-1 row `a50fc9acc3505750aef2be1d0501318c`.

```
nov_2200 2026-11-08 03:00:00 2026-11-08 04:00:00 clear []
nov_1700 2026-11-07 22:00:00 2026-11-07 23:00:00 flagged ['a50fc9acc3505750aef2be1d0501318c']
jun_2200 2026-06-07 02:00:00 2026-06-07 03:00:00 clear []
jun_1700 2026-06-06 21:00:00 2026-06-06 22:00:00 flagged ['a50fc9acc3505750aef2be1d0501318c']
probe_left 0
```

Only the Saturday 22:00 Eastern probes are free of `not_in_maintenance_window`. Policy code still governs the deployment check. The Deployment precondition requires `clock.now()` to be inside the approved planned start and end. A standard change outside the policy span is blocked. A normal or emergency change is not. `not_in_maintenance_window` is not a scheduling block and not a deployment block. CI overlap and blackout still come from the OOB conflict API. `docs/DISCOVERY.md` Phase 3 records the cause and the fix. Item 7 still governs CI overlap. Its maintenance-window sentence does not govern deployment.

`Blackout Wednesdays (GMT)` (`83cd9a930a0a2c3e6d4957fe9651c24d`) comes from ServiceNow's demo data. It has an empty condition and applies to every `cmdb_ci`. `Software Blackout` applies only to `cmdb_ci_spkg`. S02's requested Tuesday 20:00 Eastern window is Wednesday in GMT, so the conflict API returned `blackout` and scheduling moved the window to 2026-11-06 01:00:00–03:00:00 UTC. That move is correct. Policy was not retuned. The blackout was not edited. The live deploy clock is the approved start plus 30 minutes, so a moved window still satisfies the clock check.

A standard template's `readonly_fields` are `description`, `implementation_plan`, `backout_plan`, and `test_plan`. Business rule `Restrict fields from Standard Change` aborts the whole update if any of them change. Intake omits those four on a standard change and writes the deployment method in a work note. The plan judge still reads the request text.

## Gate

Unit tests for this review, with no network and no LLM: `uv run ruff check cm_agents tests` printed `All checks passed!`, then `uv run pytest` printed `125 passed in 17.60s`. The default suite does not collect `tests/live`. Python for that run is 3.13.2.

Simulator, one test for each strategy's success, injected failure, and rollback:

- `test_canary_succeeds`
- `test_blue_green_succeeds`
- `test_rolling_succeeds`
- `test_big_bang_succeeds`
- `test_canary_injected_failure_stops_at_canary_100`
- `test_blue_green_injected_failure_stops_at_switch`
- `test_rolling_injected_failure_stops_at_batch_75`
- `test_big_bang_injected_failure_stops_at_all`
- `test_canary_rollback_restores_the_previous_version_and_keeps_prod_blocked`
- `test_blue_green_rollback_restores_the_previous_version_and_keeps_prod_blocked`
- `test_rolling_rollback_restores_the_previous_version_and_keeps_prod_blocked`
- `test_big_bang_rollback_restores_the_previous_version_and_keeps_prod_blocked`

The earlier replay and stage tests stay: `test_canary_failure_blocks_a_later_prod_deploy_and_rollback_restores`, `test_stage_failure_does_not_block_prod`.

Deployment preconditions, including no automatic retry after a PROD failure:

- `test_normal_change_without_a_go_is_blocked`
- `test_emergency_change_does_not_need_a_go`
- `test_a_change_that_is_not_scheduled_is_blocked`
- `test_a_missing_window_is_blocked`
- `test_a_clock_outside_the_window_is_blocked`
- `test_a_standard_change_outside_maintenance_is_blocked`
- `test_a_normal_change_outside_maintenance_is_not_blocked`
- `test_a_standard_change_inside_the_saturday_window_is_allowed`
- `test_a_prod_failure_is_not_retried`

Review close-code rules and the PIR-required rule:

- `test_rolled_back_closes_unsuccessful`
- `test_priority_1_through_3_closes_unsuccessful`
- `test_priority_4_closes_successful_with_issues`
- `test_a_verified_deploy_closes_successful`
- `test_pir_is_required_for_unsuccessful_emergency_high_risk_and_caused_incident`
- `test_pir_is_not_required_for_a_successful_normal_change`

The span clock is stored unchanged: `test_saturday_night_is_stored_as_the_eastern_wall_clock`, `test_tuesday_and_thursday_evenings_are_stored_as_the_eastern_wall_clock`, `test_a_summer_clock_is_not_rewritten_to_utc`, `test_a_span_clock_must_be_compact`.

The live gate is S01, S02 close, S03, S05, and S07. `tests/live/test_s02.py` still stops at `go_no_go` and was not in this run. Running it with `test_s02_close.py` would put two changes on `syn-hr-portal`. Before this run, `remove_scenario_records` deleted the previous gate's rows and printed `scenario changes remaining=0 scenario incidents remaining=0`. `var/sim_state.json` no longer listed `syn-ful-api` under `failed_prod`. `CM_AGENTS_RUN=phase3-gate-3` was set before pytest so the live conftest default (`phase2-gate`) did not override it.

```
s01 number=CHG0039417 type=standard state=3 close_code=successful start=2026-11-08 03:00:00
s02 deploy now 2026-11-06 01:30:00
s02 number=CHG0039418 state=3 risk=4 close_code=successful
s03 number=CHG0039419 state=-5 risk=2 start=2026-11-08 03:00:00
s03 approval comment SYN reject: backout is not acceptable
s03 note [agent:review] rejected: SYN reject: backout is not acceptable
s03 note [agent:scheduling] moved: requested 2026-10-30 22:00:00 to 2026-10-31 00:00:00 UTC; chosen 2026-11-08 03:00:00 to 2026-11-08 05:00:00 UTC; maintenance inside; conflicts none; source ok; prior freeze SYN Month-End Close Freeze, lead time
s05 trigger number=INC0011000 priority=1 impact=1 urgency=1 state=1
s05 number=CHG0039420 type=emergency state=3 close_code=successful
pir file CHG0039420.md
pir section '## Timeline' present=True
pir section '## What went well' present=True
pir section "## What didn't" present=True
pir section '## Root-cause hypothesis' present=True
pir section 'Hypothesis:' present=True
pir section '## Actions' present=True
s07 deploy now 2026-11-20 01:30:00
s07 number=CHG0039421 state=3 close_code=unsuccessful
s07 incident number=INC0011001 sys_id=76dd2706c3d45310aef2be1d0501315d u_caused_by=ef7de3c2c3d45310aef2be1d0501310d change_sys_id=ef7de3c2c3d45310aef2be1d0501310d priority=3 impact=2 urgency=2
s07 prod steps=['env=PROD step=canary_10 result=ok', 'env=PROD step=canary_100 result=failed']
pir file CHG0039421.md
pir section '## Timeline' present=True
pir section '## What went well' present=True
pir section "## What didn't" present=True
pir section '## Root-cause hypothesis' present=True
pir section 'Hypothesis:' present=True
pir section '## Actions' present=True
======================== 5 passed in 655.61s (0:10:55) ========================
```

S01 is a standard change on the stage load balancer `syn-store-lb-05`. It closed `successful` with the requested start unchanged. Its simulator step is `env=STAGE`, which is that CI's environment. S02 closed `successful` at risk `4` after one approver at Assess and one at Authorize, then a go. S03 was rejected at CAB and returned to New (`-5`). That is ServiceNow's standard rejection transition. Review recorded the rejection and did not close the change. There is no implementation task. The approval comment read back is `SYN reject: backout is not acceptable`, and the Review work note is `[agent:review] rejected: SYN reject: backout is not acceptable`. The scheduling note names the freeze. S03's chosen window now has `conflicts none`, which matches the corrected Saturday span. S05 was typed `emergency`, the first interrupt was Authorize, the close resume did not print `go_no_go`, and it closed `successful`. Its PIR is `reports/pir/CHG0039420.md`, and each required section is present. S07 closed `unsuccessful`. Incident `INC0011001` has `u_caused_by` equal to the change `ef7de3c2c3d45310aef2be1d0501310d`, impact `2`, urgency `2`, and priority `3` read back. Its PIR is `reports/pir/CHG0039421.md`, with the same sections present. The PROD `deploy_step` rows for that thread end at `canary_100 result=failed`. There is no later PROD `deploy_step`.

An earlier live attempt (`CM_AGENTS_RUN=phase3-gate`) failed all five and is not this gate. A later pass (`CM_AGENTS_RUN=phase3-gate-2`, 5 passed in 693.88s) is the run this review did not accept. Neither run's calls are in the total below.

## Cost

From `var/audit.jsonl`, rows with `run=phase3-gate-3` and a model id. Deploy and rollback rows have an empty model and are not counted. The model id is `grok-4.7`. The API key is not in the log.

```
calls 16
tokens 50000
actions {'plan_quality': 5, 'close_notes': 4, 'cab_brief': 4, 'pir': 3}
```

Five plan-quality calls are S01, S02, S03, S05, and S07. Four close notes are the four changes that reached Review after a deployment. S03 was rejected and has no close note. Four CAB briefs are the four changes that reached authorization. S01 is standard and has no brief. Three PIRs are S03 (high risk), S05 (emergency), and S07 (unsuccessful). S01 and S02 are successful and not high risk, so they have no PIR.

Earlier runs are not part of the 16. `run=phase3-gate` was 11 calls and 36168 tokens. `run=phase3-gate-2` was 16 calls and 50611 tokens.

## Files

- `cm_agents/deploy/simulator.py` — seeded strategies, injected failure, and a failed deploy that does not replace the installed version.
- `cm_agents/deploy/__init__.py` — package marker.
- `cm_agents/agents/deployment.py` — preconditions, tasks, simulator, incident, and the move to Review.
- `cm_agents/agents/review.py` — close code, close, and PIR.
- `cm_agents/agents/intake.py` — omit the four read-only standard plan fields.
- `cm_agents/agents/scheduling.py` — the work note names the policy reasons that forced a move.
- `cm_agents/graphs/change_graph.py` — deployment, rollback wait, and review.
- `cm_agents/graphs/runner.py` — pin `simulated_now` for the request and for a resume.
- `cm_agents/graphs/state.py` — deployment and review results on the checkpoint.
- `cm_agents/cli.py` — `resume --now` merges into the resume value.
- `cm_agents/servicenow/changes.py` — Implement, Review, Closed, tasks, and approval comments.
- `cm_agents/enablement/windows.py` — a standard change outside the policy span is a deployment block.
- `cm_agents/enablement/guard.py` — the OOB maintenance flag does not block scheduling. Policy still governs the window.
- `cm_agents/data/queries.py` — seed prefixes, the scenario query, and `counts_in_metrics`.
- `cm_agents/data/teardown.py` — `remove_scenario_records`, without a direct `task_ci` delete.
- `cm_agents/data/load.py` — direct roles, the Eastern span clock, and the conflict property that makes ServiceNow read the CI schedule.
- `cm_agents/data/generate.py` — the span strings stay America/New_York wall times.
- `cm_agents/data/manifest.py` — drop the scenario sys_ids from the gitignored manifest.
- `scenarios/S01.yaml`, `scenarios/S03.yaml`, `scenarios/S05.yaml`, `scenarios/S07.yaml` — the four new scenarios. S02 was already present.
- `tests/live/test_s01.py`, `tests/live/test_s02_close.py`, `tests/live/test_s03.py`, `tests/live/test_s05.py`, `tests/live/test_s07.py` — the gate.
- `tests/live/support.py` — the deploy clock, and the PIR section check.
- `tests/helpers/approve_as_human.py` — approve or reject the one pending approver. Agent code does not import it.
- `tests/unit/test_simulator.py` — success, injected failure, and rollback for each strategy.
- `tests/unit/test_deployment.py` — deployment preconditions and no automatic PROD retry.
- `tests/unit/test_review.py` — close-code rules and the PIR-required rule.
- `tests/unit/test_span_time.py` — the stored span stays the Eastern wall clock.
- `tests/unit/test_guard.py`, `tests/unit/test_enablement.py`, `tests/unit/test_change_graph.py`, `tests/unit/test_queries.py` — the blocks, edges, and metric prefixes.
- `docs/DISCOVERY.md` — the Phase 3 schedule, blackout, and standard-field evidence.
- `docs/ASSUMPTIONS.md` — the three roles, the scenario marker, and the deployment-window rule.
- `docs/phase-reports/phase-3.md` — this report.

PIR files are under `reports/pir/`, which is gitignored. The simulator state and the audit log are under `var/`, which is gitignored.

## Dependencies

No new dependency. `uv.lock` and `pyproject.toml` were not changed. The three direct pins from Phase 2 are unchanged: `langgraph` runs the graph and the interrupts, `langgraph-checkpoint-sqlite` stores the checkpoint across processes, and `langchain-xai` is the Grok client.

## Deviations

1. Policy code still governs the maintenance check. The ServiceNow span now matches that window in Eastern time, including daylight saving. `not_in_maintenance_window` is still not a scheduling block and not a deployment block. CI overlap and blackout still come from the OOB conflict API. Seed turns on `change.conflict.ci_maint_sched` and excludes SYN names from the demo schedule `Global Infrastructure`. The CI pointer and `Blackout Wednesdays (GMT)` were not edited.
2. S02's Tuesday-evening Eastern window is Wednesday in GMT. `Blackout Wednesdays (GMT)` comes from ServiceNow's demo data and applies to every CI, so scheduling moved the window. The deploy resume uses the approved start plus 30 minutes. Policy was not changed to ignore the blackout.
3. Intake does not write the four standard template plan fields. The business rule aborts the whole update. The deployment method is recorded in a work note. The judge still reads the YAML plans. The template was not edited.
4. `sn_incident_write` was added after the role matrix. The matrix proved create and update, and it did not read urgency back. The urgency ACL is the reason. `itil` is wider and does not read the journal, so it was not used.
5. `tests/live/test_s02.py` was not part of this gate. It stops at `go_no_go` and shares `syn-hr-portal` with the close test.
6. This review's live gate is `phase3-gate-3`. `phase3-gate` and `phase3-gate-2` are not in that total. Before this run, `syn-ful-api` was removed from `failed_prod` so the new S07 thread could perform its one injected PROD failure.
7. S01's simulator environment is STAGE. `syn-store-lb-05` is a stage CI. The no-redeploy assertion is the S07 PROD audit.
8. Teardown does not delete `task_ci` rows directly. `Change Model: Read only CI (Delete)` aborts that delete. Deleting the change removes them.

## Open

Phase 4 has not started. The release graph and a staged release deploy are not built.

This gate's scenario rows are still on the instance (`CHG0039417` through `CHG0039421`, `INC0011000`, and `INC0011001`). They are marked so Phase 5 metrics cannot count them, and `remove_scenario_records` deletes them.

`Blackout Wednesdays (GMT)` was left as demo data. The standard template was not edited. A production design would read journal entries through the record's `work_notes` and `comments` fields, rather than through a cross-table audit role. The three direct roles were not changed.

## What this phase did not do

No push. No Phase 4 code. No edit to the master prompt, `docs/setup/PDI_AND_WORKSTATION_SETUP.md`, `config/policy.yaml`, or `XAI_MODEL`. No call to the risk endpoint. No approval written by an agent. No plugin activated. No OOB change model, template, CI, or blackout edited. The seeded spans were updated in place, and the demo schedule `Global Infrastructure` now excludes names containing `syn-`. No `admin` or `itil` grant. No full teardown and no full re-seed. No `.venv` in the repository.
