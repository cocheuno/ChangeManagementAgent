# Phase 3 Report: Deployment and Review

Status: committed locally on `grok-build`. Not pushed. Stopped here for review. Phase 4 has not started.

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

The first delete attempt returned HTTP 403 on `task_ci`. The retry, after skipping that delete, is the output above. The passing gate then created its own scenario-marked rows (`CHG0039339` through `CHG0039343`, plus the S05 trigger and the S07 incident). They are not seed rows. A later `remove_scenario_records` deletes them. They were left in place after the gate.

## Maintenance windows

`syn-shared-sqlclu-prd-01` uses `SYN Tier-1 Maintenance (Sat 22:00-Sun 04:00)`, `time_zone=US/Eastern`, `type=maintenance`. The span `SYN Saturday night` is `20110101T220000` to `20110102T040000`, weekly, `days_of_week=6`. It was written with `display_value=false`, so ServiceNow matches 22:00–04:00 as UTC. Saturday 17:00 Eastern (22:00 UTC) raised no maintenance flag. Saturday 22:00 Eastern (03:00 UTC), which is the S04 window 2026-11-08 03:00:00–05:00:00 UTC, returned `not_in_maintenance_window`. The schedule's time zone field does not move that stored span onto Saturday night Eastern.

Policy code in `America/New_York` does contain that Saturday window. Policy governs the maintenance check. The Deployment precondition requires `clock.now()` to be inside the approved planned start and end. A standard change outside the policy span is blocked. A normal or emergency change is not. `not_in_maintenance_window` is not a scheduling block and not a deployment block. CI overlap and blackout still come from the OOB conflict API. The CI and the span were not modified. `docs/DISCOVERY.md` Phase 3 records this. Item 7 still governs CI overlap. Its maintenance-window sentence does not govern deployment.

`Blackout Wednesdays (GMT)` (`83cd9a930a0a2c3e6d4957fe9651c24d`) has an empty condition and applies to every `cmdb_ci`. `Software Blackout` applies only to `cmdb_ci_spkg`. S02's requested Tuesday 20:00 Eastern window is Wednesday in GMT, so the conflict API returned `blackout` and scheduling moved the window to 2026-11-06 01:00:00–03:00:00 UTC. That move is correct. Policy was not retuned. The live deploy clock is the approved start plus 30 minutes, so a moved window still satisfies the clock check.

A standard template's `readonly_fields` are `description`, `implementation_plan`, `backout_plan`, and `test_plan`. Business rule `Restrict fields from Standard Change` aborts the whole update if any of them change. Intake omits those four on a standard change and writes the deployment method in a work note. The plan judge still reads the request text.

## Gate

Unit tests after the Phase 3 code, including the simulator and the scheduling-note change: `uv run ruff check cm_agents tests` printed `All checks passed!`, then `uv run pytest` printed `95 passed in 41.12s`. The default suite does not collect `tests/live`.

The live gate is S01, S02 close, S03, S05, and S07. `tests/live/test_s02.py` still stops at `go_no_go` and was not in this run. Running it with `test_s02_close.py` would put two changes on `syn-hr-portal`. `CM_AGENTS_RUN=phase3-gate-2` was set before pytest so the live conftest default (`phase2-gate`) did not override it.

```
s01 number=CHG0039339 type=standard state=3 close_code=successful start=2026-11-08 03:00:00
s02 deploy now 2026-11-06 01:30:00
s02 number=CHG0039340 state=3 risk=4 close_code=successful
s03 number=CHG0039341 state=-5 risk=2 start=2026-11-08 03:00:00
s03 note [agent:scheduling] moved: requested 2026-10-30 22:00:00 to 2026-10-31 00:00:00 UTC; chosen 2026-11-08 03:00:00 to 2026-11-08 05:00:00 UTC; maintenance inside; conflicts not_in_maintenance_window; source ok; prior freeze SYN Month-End Close Freeze, lead time
s03 note [agent:review] rejected: SYN reject: backout is not acceptable
s05 trigger number=INC0010998 priority=1 impact=1 urgency=1 state=1
s05 number=CHG0039342 type=emergency state=3 close_code=successful
s07 deploy now 2026-11-20 01:30:00
s07 number=CHG0039343 state=3 close_code=unsuccessful
s07 incident priority=3 impact=2 urgency=2 caused_by_match=True
s07 prod steps=['env=PROD step=canary_10 result=ok', 'env=PROD step=canary_100 result=failed']
======================== 5 passed in 693.88s (0:11:33) ========================
```

S01 is a standard change on the stage load balancer `syn-store-lb-05`. It closed `successful` with the requested start unchanged. Its simulator step is `env=STAGE`, which is that CI's environment. S02 closed `successful` at risk `4` after one approver at Assess and one at Authorize, then a go. S03 was rejected at CAB, stayed New (`-5`), risk `2`, with no implementation task, and the scheduling note names the freeze. S05 was typed `emergency`, the first interrupt was Authorize, the close resume did not print `go_no_go`, and it closed `successful`. S07 closed `unsuccessful`. The incident's `correlation_id` is the thread id, `u_caused_by` is the change, impact and urgency are `2`, and priority `3` was read back. The PROD `deploy_step` rows for that thread end at `canary_100 result=failed`. The next audit row is `rollback env=PROD result=rolled_back`. There is no later PROD `deploy_step`.

An earlier live attempt (`CM_AGENTS_RUN=phase3-gate`) failed all five and is not this gate. S01 hit the standard-field business rule. S02 deployed at the requested instant after the blackout had moved the window, and the clock check refused it. S03's note did not yet name the freeze. S05 stayed a normal change because the trigger priority was `3`. S07 reached Closed and `unsuccessful`, then the test stopped on urgency `3`. That attempt's PROD rows also end at `canary_100 result=failed` and one rollback. Its calls are listed under Cost and are not in the gate total.

## Cost

From `var/audit.jsonl`, rows with `run=phase3-gate-2` and a model id. Deploy and rollback rows have an empty model and are not counted. The model id is `grok-4.7`. The API key is not in the log.

```
calls 16
tokens 50611
actions {'plan_quality': 5, 'close_notes': 4, 'cab_brief': 4, 'pir': 3}
```

Five plan-quality calls are S01, S02, S03, S05, and S07. Four close notes are the four changes that reached Review after a deployment. S03 was rejected and has no close note. Four CAB briefs are the four changes that reached authorization. S01 is standard and has no brief. Three PIRs are S03 (high risk), S05 (emergency), and S07 (unsuccessful). S01 and S02 are successful and not high risk, so they have no PIR.

The failed attempt, `run=phase3-gate`, is separate: 11 calls, 36168 tokens, actions `plan_quality` 4, `cab_brief` 4, `close_notes` 1, `pir` 2. Those calls are not part of the 16.

## Files

- `cm_agents/deploy/simulator.py` — seeded strategies, injected failure, and the per-CI PROD block.
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
- `cm_agents/enablement/guard.py` — the OOB maintenance flag does not block scheduling.
- `cm_agents/data/queries.py` — seed prefixes, the scenario query, and `counts_in_metrics`.
- `cm_agents/data/teardown.py` — `remove_scenario_records`, without a direct `task_ci` delete.
- `cm_agents/data/load.py` — direct roles `sn_change_write`, `audit_viewer`, and `sn_incident_write`.
- `cm_agents/data/manifest.py` — drop the scenario sys_ids from the gitignored manifest.
- `scenarios/S01.yaml`, `scenarios/S03.yaml`, `scenarios/S05.yaml`, `scenarios/S07.yaml` — the four new scenarios. S02 was already present.
- `tests/live/test_s01.py`, `tests/live/test_s02_close.py`, `tests/live/test_s03.py`, `tests/live/test_s05.py`, `tests/live/test_s07.py` — the gate.
- `tests/live/support.py` — the deploy clock is the approved start plus 30 minutes.
- `tests/helpers/approve_as_human.py` — approve or reject the one pending approver. Agent code does not import it.
- `tests/unit/test_simulator.py` — each strategy, replay, and the PROD block.
- `tests/unit/test_guard.py`, `tests/unit/test_enablement.py`, `tests/unit/test_change_graph.py`, `tests/unit/test_queries.py` — the new blocks, edges, and metric prefixes.
- `docs/DISCOVERY.md` — the Phase 3 schedule, blackout, and standard-field evidence.
- `docs/ASSUMPTIONS.md` — the three roles, the scenario marker, and the deployment-window rule.
- `docs/phase-reports/phase-3.md` — this report.

PIR files are under `reports/pir/`, which is gitignored. The simulator state and the audit log are under `var/`, which is gitignored.

## Dependencies

No new dependency. `uv.lock` and `pyproject.toml` were not changed. The three direct pins from Phase 2 are unchanged: `langgraph` runs the graph and the interrupts, `langgraph-checkpoint-sqlite` stores the checkpoint across processes, and `langchain-xai` is the Grok client.

## Deviations

1. Policy code governs the maintenance check. `docs/DISCOVERY.md` item 7 says to use the OOB conflict API for the maintenance-window result. On this PDI that result flags the policy Saturday window, because the span is stored as a UTC clock. Scheduling and deployment do not treat `not_in_maintenance_window` as a block. CI overlap and blackout still come from that API. The CI and the span were not modified.
2. S02's Tuesday-evening Eastern window is Wednesday in GMT. `Blackout Wednesdays (GMT)` applies to every CI, so scheduling moved the window. The deploy resume uses the approved start plus 30 minutes. Policy was not changed to ignore the blackout.
3. Intake does not write the four standard template plan fields. The business rule aborts the whole update. The deployment method is recorded in a work note. The judge still reads the YAML plans. The template was not edited.
4. `sn_incident_write` was added after the role matrix. The matrix proved create and update, and it did not read urgency back. The urgency ACL is the reason. `itil` is wider and does not read the journal, so it was not used.
5. `tests/live/test_s02.py` was not part of this gate. It stops at `go_no_go` and shares `syn-hr-portal` with the close test.
6. The first live attempt failed and was re-run as `phase3-gate-2`. The failed attempt's 11 calls are not in the gate total. Before the re-run, `var/sim_state.json` was cleared so the new S07 thread could perform its one injected PROD failure. The failed attempt had left `syn-ful-api` on the no-redeploy list.
7. S01's simulator environment is STAGE. `syn-store-lb-05` is a stage CI. The no-redeploy assertion is the S07 PROD audit.
8. Teardown does not delete `task_ci` rows directly. `Change Model: Read only CI (Delete)` aborts that delete. Deleting the change removes them.

## Open

Phase 4 has not started. The release graph and a staged release deploy are not built.

The passing gate's scenario rows are still on the instance. They are marked so Phase 5 metrics cannot count them, and `remove_scenario_records` deletes them.

The maintenance span and `Blackout Wednesdays (GMT)` were left as they are. The standard template was not edited.

## What this phase did not do

No push. No Phase 4 code. No edit to the master prompt, `docs/setup/PDI_AND_WORKSTATION_SETUP.md`, `config/policy.yaml`, or `XAI_MODEL`. No call to the risk endpoint. No approval written by an agent. No plugin activated and no OOB change model, template, CI, span, or blackout edited. No `admin` or `itil` grant. No full teardown and no re-seed. No `.venv` in the repository.
