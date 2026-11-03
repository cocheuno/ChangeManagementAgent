# Phase 4 Report: Release Management

Status: committed locally on `grok-build`. Not pushed. Stopped here. Phase 5 has not started.

The instance is still the Phase 1 seed (`anchor 2026-10-27`). This phase did not re-seed and did not run a full teardown. `.env` is not in this commit. `config/policy.yaml` was not changed. `XAI_MODEL` was not changed. The runtime model id in the audit log is `grok-4.7`. The Risk Calculator was not called. Agents do not write approvals. `admin` and `itil` were not granted. The normal change model was not edited.

A release is a normal change named `SYN RELEASE <service> <version>`. Member changes point at it through `parent` (`docs/DISCOVERY.md` item 10). There is no `rm_release` table, and no plugin was activated.

## Preflight

`UV_PROJECT_ENVIRONMENT` was unset. The same command set it to `%LOCALAPPDATA%\venvs\ChangeManagementAgent`. No `.venv` was created in the repository. This is the suite before the Phase 4 code. The audited line landed on the pytest banner. Python for the later runs in this session is 3.13.2. The setup guide says 3.12.6. That guide was not edited.

```
UV_PROJECT_ENVIRONMENT=C:\Users\caronet\AppData\Local\venvs\ChangeManagementAgent
===== uv sync =====
Resolved 66 packages in 3ms
===== pytest =====
Audited 65 packages in 135ms
collected 125 items
============================ 125 passed in 38.13s =============================
===== doctor =====
admin login: ok
instance build: glide.buildname and glide.buildtag were not found; glide.war=glide-australia-02-11-2026__patch3-05-25-2026_06-12-2026_1106.zip
agent user: present
```

The doctor plugin list matches Phase 3. The classic Release Management plugin is absent. ReleaseOps stays inactive. `com.snc.release_management_read_roles` stays active.

## Out-of-box originals

Phase 3 had set `change.conflict.ci_maint_sched` to true and the demo schedule `Global Infrastructure` condition to `nameNOT LIKEsyn-`. Both are approved for this phase, with a record-before-write and a restore-after-delete. Seed stores the value it has just read under `oob_originals` and does not replace a stored original. Teardown writes those stored values back after the data rows, reads them back, and only then deletes the manifest.

On this PDI the two rows were already at the approved targets when that recorder was added. The gitignored manifest was given the Phase 3 pre-change readings, and the live rows were not written again:

- `sys_properties` `638460b6b70023008ef6eac7ee11a9f2`, field value, stored original `false`
- `cmn_schedule_maintenance` `0842df2437501000bff8e0f617733483`, field condition, stored original empty

A deleted manifest on this already-changed PDI would record the current targets. Teardown was not run. A teardown would restore `false` and the empty condition.

## Unit tests

Ruff (`E`, `F`, `I`, `UP`, line length 100) and the offline suite, after the Phase 4 code. Live tests stay outside the default `testpaths`.

```
All checks passed!
collected 138 items
============================ 138 passed in 38.62s =============================
```

The 138 includes the four out-of-box record and restore tests and the release tests. The release source has no `score_change` and no `run_risk`. An unauthorized member is the only readiness failure returned, even when conflicts, a freeze, an open incident, and missing notes are also true.

## Scenario records

`remove_scenario_records` deletes a `change_request` or `incident` whose `correlation_id` starts with `SYN-` and does not start with `SYN-CHG-`, `SYN-OPEN-`, `SYN-REL-`, or `SYN-INC-`. It refuses a row that `counts_in_metrics` accepts. The full teardown was not run. The Phase 1 seed was not touched.

Before the first S06 attempt, that removal printed remaining 0 and deleted the Phase 3 review rows `CHG0039417` through `CHG0039421`, `INC0011000`, and `INC0011001`.

The first S06 attempt (`CM_AGENTS_RUN=phase4-gate`, thread `SYN-S06-816e63ec`, release `CHG0039422`) passed readiness, both authorization interrupts, go/no-go, and the four stage tasks, then raised `CHG0039425 has a change task` while closing a member. Those five rows were removed before the accepted gate:

```
scenario changes=5 scenario incidents=0
scenario CHG0039422 correlation_id=SYN-S06-816e63ec
scenario CHG0039423 correlation_id=SYN-S06-816e63ec-syn-store-web
scenario CHG0039424 correlation_id=SYN-S06-816e63ec-syn-store-api
scenario CHG0039425 correlation_id=SYN-S06-816e63ec-syn-store-catalog
scenario CHG0039426 correlation_id=SYN-S06-816e63ec-syn-store-cart
scenario changes remaining=0 scenario incidents remaining=0
```

`var/sim_state.json` still lists `syn-ful-api` under `failed_prod` from the Phase 3 S07 run. S06 does not deploy that CI. The flag was left set.

## Release history

`tests/live/test_release_history.py` reads `ground_truth.json` and the live rows `correlation_idSTARTSWITHSYN-REL-` with `short_description` starting `SYN RELEASE `. Planned end is `end_date`. Actual end is `work_end`. Both are UTC (`display_value=false`). On time means actual end on or before planned end. The fixtures were not regenerated.

```
ground_truth releases=20 on_time=17 pct=85.0
servicenow releases=20 with_both_dates=20 on_time=17
late CHG0037762 SYN RELEASE SYN Online Store 2025.11.0 end_date=2025-11-02 09:00:00 work_end=2025-11-07 08:00:00
late CHG0037774 SYN RELEASE SYN Order Fulfillment 2026.03.0 end_date=2026-03-08 09:00:00 work_end=2026-03-13 09:00:00
late CHG0037780 SYN RELEASE SYN HR Portal 2026.05.0 end_date=2026-05-03 08:00:00 work_end=2026-05-08 08:00:00
```

All 20 live rows have both dates. The three late numbers are the generator's late set. The store `2025.11.0` row is the Pacific fold: `work_end` is stored one hour later than a naive conversion and is still five days after `end_date`. The count is 17 of 20, next to ground truth 17 of 20 (`release_on_time_pct` 85.0). S06 uses `SYN-S06-`, so it is outside this query.

## S06

`CM_AGENTS_RUN=phase4-gate-2` was set before pytest. The live conftest default is `phase2-gate`, and `setdefault` does not override a value that is already set. The release notes file `reports/release/2026.11.0.md` was deleted first so the notes call ran again. The window is `2026-11-15 03:00:00` to `2026-11-15 09:00:00` UTC (Saturday 22:00 Eastern through Sunday 04:00 Eastern). The go resume passes `--now` as the approved start plus 30 minutes.

The flow that passed:

1. Release `CHG0039427` was created in New (`-5`), assignment group Change Management, summary `SYN RELEASE SYN Online Store 2026.11.0`.
2. Four member changes were created by the test, parented to that release, on `syn-store-web`, `syn-store-api`, `syn-store-catalog`, and `syn-store-cart`. Three were walked to Scheduled. `syn-store-cart` (`CHG0039431`) was left at Authorize.
3. `release run` interrupted at `requester_info` / `readiness` with state `-5` and detail `CHG0039431 failed the authorization check: awaiting authorization`. The release stayed New. That check is returned alone, before plan quality, conflicts, freeze, CI ownership, open P1/P2, or release notes.
4. The test helper approved the member. Resume interrupted at Assess, state `-4`, groups `['Change Management']`.
5. Resume interrupted at Authorize, state `-3`, groups `['Change Management', 'CAB Approval']`.
6. Resume interrupted at `go_no_go`, state `-2`.
7. Resume with decision `go` closed the release. State `3`, close code `successful`, risk `4` (Low, the highest member tier, written by code).

```
ground_truth releases=20 on_time=17 pct=85.0
servicenow releases=20 with_both_dates=20 on_time=17
late CHG0037762 SYN RELEASE SYN Online Store 2025.11.0 end_date=2025-11-02 09:00:00 work_end=2025-11-07 08:00:00
late CHG0037774 SYN RELEASE SYN Order Fulfillment 2026.03.0 end_date=2026-03-08 09:00:00 work_end=2026-03-13 09:00:00
late CHG0037780 SYN RELEASE SYN HR Portal 2026.05.0 end_date=2026-05-03 08:00:00 work_end=2026-05-08 08:00:00
thread: SYN-S06-cdb4dbcf
interrupt: requester_info
step: readiness
change: CHG0039427
state: -5
detail: CHG0039431 failed the authorization check: awaiting authorization
s06 assess groups=['Change Management']
s06 authorize groups=['Change Management', 'CAB Approval']
thread: SYN-S06-cdb4dbcf
interrupt: go_no_go
step: go_no_go
change: CHG0039427
state: -2
thread: SYN-S06-cdb4dbcf
interrupt: none
step: closed
change: CHG0039427
state: 3
s06 closed CHG0039427 state=3 risk=4 close_code=successful
s06 release tasks=6
s06 task Implement type=implementation state=4 result=Implement
s06 task Post implementation testing type=testing state=4 result=Post implementation testing
s06 task SYN DEV implementation type=implementation state=3 result=result=passed result=passed
s06 task SYN TEST implementation type=implementation state=3 result=result=passed result=passed
s06 task SYN STAGE implementation type=implementation state=3 result=result=passed result=passed
s06 task SYN PROD implementation type=implementation state=3 result=result=passed result=passed
s06 member CHG0039428 state=3 close_code=successful tasks=2 notes=Closed with release CHG0039427 SYN RELEASE SYN Online Store 2026.11.0.
s06 member CHG0039429 state=3 close_code=successful tasks=2 notes=Closed with release CHG0039427 SYN RELEASE SYN Online Store 2026.11.0.
s06 member CHG0039430 state=3 close_code=successful tasks=2 notes=Closed with release CHG0039427 SYN RELEASE SYN Online Store 2026.11.0.
s06 member CHG0039431 state=3 close_code=successful tasks=2 notes=Closed with release CHG0039427 SYN RELEASE SYN Online Store 2026.11.0.
s06 notes file 2026.11.0.md
s06 section '## User-facing changes' present=True
s06 section '## Support and service desk notes' present=True
s06 section '## Known errors and workarounds' present=True
======================== 2 passed in 321.20s (0:05:21) ========================
```

Each member's two tasks are `Implement` (implementation, state `4`) and `Post implementation testing` (testing, state `4`). None of them is a `SYN ` task. `sys_choice` `name=change_task^element=state^language=en` labels `4` as Canceled. The four `SYN` tasks on the release are type implementation, state `3` (Closed), and each description and close note contains `result=passed`. The simulator installed version on those four CIs, in DEV, TEST, STAGE, and PROD, is `CHG0039427`. Each deploy used its own simulator thread id, `SYN-S06-cdb4dbcf|<ci>|<environment>`.

`reports/release/2026.11.0.md` starts with `# Release notes 2026.11.0` and contains the three sections. The file is gitignored. The test asserts the headings, not the wording.

Entering Implement is what inserts the two model tasks. A direct Scheduled to Review move is HTTP 400, so Implement cannot be skipped. Deleting `change_task` as the agent user is HTTP 403. The model was not edited, and no role was added. Close accepts only those two names on a member and raises on any other task, including a `SYN ` task.

## Cost

From `var/audit.jsonl`, rows with `run=phase4-gate-2` and a model id. Deploy and rollback rows have an empty model and are not counted. The model id is `grok-4.7`. The API key is not in the log.

```
calls 7
tokens 17177
actions {'plan_quality': 4, 'release_notes': 1, 'cab_brief': 1, 'close_notes': 1}
```

Four plan-quality calls are the four members, judged once readiness has passed. One release-notes call writes the three sections. One CAB brief is the release authorization. One close-notes call is the release. The first readiness interrupt does not call the model. The failed attempt is not in this total. `run=phase4-gate` was 6 calls and 15573 tokens (`plan_quality` 4, `release_notes` 1, `cab_brief` 1) and stopped before the close-notes call.

## Files

- `cm_agents/agents/release.py` — readiness before authorization, highest-member risk, four stage tasks, and member close.
- `cm_agents/graphs/release_graph.py` — the release graph and its three interrupts.
- `cm_agents/graphs/state.py` — `ReleaseState`.
- `cm_agents/graphs/runner.py` — `SYN-RUN-` and `SYN-S06-` open the release graph. Seed `SYN-REL-` threads are refused.
- `cm_agents/cli.py` — `release new` and `release run`.
- `cm_agents/servicenow/changes.py` — change-task reads include `description` and `close_notes`.
- `cm_agents/data/oob.py` — record one original, and restore it with a read-back.
- `cm_agents/data/load.py` — record the two approved originals before either write.
- `cm_agents/data/teardown.py` — restore those originals after the data rows, before the manifest is deleted.
- `tests/unit/test_oob.py` — the record, the second-seed keep, the restore, and the teardown order.
- `tests/unit/test_release.py` — the readiness order, the risk copy, and the model-task names.
- `tests/live/test_s06.py` — the live release gate.
- `tests/live/test_release_history.py` — the 20 seeded releases, read from ServiceNow.
- `tests/live/support.py` — interrupt output keeps a `detail` line.
- `scenarios/S06.yaml` — Store `2026.11.0`, one member left awaiting authorization.
- `prompts/grok-build-change-release-deployment-agents.md` — the S06 expected-outcome cell. The rest of the prompt was not rewritten.
- `docs/DISCOVERY.md` — item 10 for this flow, and the two stored originals.
- `docs/ASSUMPTIONS.md` — the same two originals, the stage tasks, and the rows left on the instance.
- `docs/phase-reports/phase-4.md` — this report.

Release notes are under `reports/release/`, which is gitignored. The simulator state and the audit log are under `var/`, which is gitignored. The manifest is `data/synthetic/manifest.json`, which is gitignored.

## Dependencies

No new dependency. `uv.lock` and `pyproject.toml` were not changed. The pins from Phase 2 are unchanged: `langgraph` runs the graph and the interrupts, `langgraph-checkpoint-sqlite` stores the checkpoint across processes, and `langchain-xai` is the Grok client.

## Deviations

1. `change.conflict.ci_maint_sched` set to true, and the `Global Infrastructure` condition set to `nameNOT LIKEsyn-`, are approved out-of-box changes. Seed records each original in the manifest before it changes the row. Teardown restores those stored values after the data rows. On this PDI the stored originals are the Phase 3 pre-change readings, property `false` and an empty condition. See `docs/DISCOVERY.md` and `docs/ASSUMPTIONS.md`.
2. The per-member PROD implementation and testing tasks in the master prompt §6.6 are replaced. The release carries one implementation task for DEV, TEST, STAGE, and PROD, and that task records the stage result. Member changes close with the release. Their close notes name the release change. The 20 seeded releases are not backfilled.
3. The S06 expected outcome is this flow, and it cites `docs/DISCOVERY.md` item 10. Readiness still fails first and names the member that is awaiting authorization. All four stages still pass.
4. The out-of-box normal model inserts `Implement` and `Post implementation testing` when a change enters Implement, then sets them to `change_task.state` `4` (Canceled) on the way out. The agent cannot delete `change_task` (HTTP 403). Scheduled to Review is HTTP 400, so Implement cannot be skipped. Those two rows stay, on the release and on each member. The agent creates no member task. A member task whose name is anything else, including a `SYN ` task, still fails the close.

## Open

Phase 5 metrics are not built. A metrics query has to use the seed prefixes, or call `counts_in_metrics`, so the scenario rows cannot enter a count.

This gate's scenario rows are still on the instance (`CHG0039427` through `CHG0039431`, thread `SYN-S06-cdb4dbcf`). They are marked so Phase 5 metrics cannot count them, and `remove_scenario_records` deletes them.

`syn-ful-api` is still on `failed_prod` from Phase 3. Clear it before another S07 run. S06 did not deploy that CI.

Any further system property, out-of-box record, role, or change-model edit stops for approval. The two approved rows above are the only ones this phase records.

## What this phase did not do

Stopped after the local commit. Phase 5 code was not started. `docs/setup/PDI_AND_WORKSTATION_SETUP.md`, `config/policy.yaml`, and `XAI_MODEL` were not edited. The risk endpoint was not called. No agent wrote an approval. No plugin was activated. The normal change model, the standard template, the blackout, and the CI records were not edited. No role was granted. The seed was not torn down and was not regenerated. No `.venv` was created in the repository.
