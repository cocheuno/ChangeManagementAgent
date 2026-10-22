# Phase 1 Report: Synthetic data

Status: committed locally on `grok-build`. Not pushed. Stopped here for review. Phase 2 has not started.

The instance is left seeded. `data/synthetic/` (fixtures, ground truth, and the manifest) stays gitignored. No plugin was activated. `.env` is not in this commit and is not in git history.

## Gate

The passing run is one script: `uv sync`, `ruff check cm_agents tests`, `pytest -q`, `cm-agents doctor`, `seed --dry-run` twice, `seed`, `seed`, `teardown`, `seed`, `cm-agents doctor`. Exit code 0. The script sets `UV_PROJECT_ENVIRONMENT` to `%LOCALAPPDATA%\venvs\ChangeManagementAgent` when that variable is empty. It does not create `.venv` in the repository.

```
===== uv sync =====
Resolved 23 packages in 7ms
Audited 23 packages in 57ms
===== ruff =====
All checks passed!
===== pytest =====
74 passed in 6.41s
```

`test_patterns_are_within_three_points` checks P1–P6 in the fixtures at ±3 percentage points. `test_release_membership_and_ground_truth` checks payments failure 20.0, P6 count 12, and release on-time 85.0. Phase 0 was 51 passed. The new tests were added. No assertion was loosened or deleted.

Doctor, before the seeds and again after the final seed:

```
admin login: ok
instance build: glide.buildname and glide.buildtag were not found; glide.war=glide-australia-02-11-2026__patch3-05-25-2026_06-12-2026_1106.zip
agent user: present
```

Release-related plugin lines from that same doctor output:

```
Global scope support for the ReleaseOps scoped application [com.glide.releaseopsglobal]: active=inactive
Read only roles for Release Management [com.snc.release_management_read_roles]: active=active
ReleaseOps Backend [com.glide.releaseops]: active=inactive
```

`rm_release` is still absent. Those three plugins were not activated. See `docs/DISCOVERY.md` item 10.

Dry-run hashes, both runs, and every later seed in this gate:

```
fixture hash: 7cf80a6c73939302d0d6ecbbb909dd2ed6bc16834561b86da0cdbc361492afcc
dry-run hashes match
```

The hash changed once during Phase 1, before this gate. On the Pacific fall-back hour, `2025-11-02 08:00:00` UTC and `2025-11-02 09:00:00` UTC both format as `2025-11-02 01:00:00` Pacific, and this instance stores that wall time as `09:00` UTC. The fixture now uses that later instant. The four `2025.11.0` release end times are the rows this moves. Populations were not retuned. On-time stays 85.0 (17 of 20). See `docs/DISCOVERY.md` item 9.

Seed 1 in this gate repaired two changes a cascade proof had deleted (`SYN-CHG-0001`, `SYN-CHG-1456`) and their three affected-CI rows. It is not the clean create.

```
imported change_request 2/2
import sets: 3 state=loading
task_ci 3/3
number empty changes=0 incidents=0
field check: changes=1545 incidents=164 ok
load seconds: 19.7
created: 5
SEED OK
```

Seed 2 is the idempotency check. It created nothing.

```
import sets: 3 state=loading
task_ci created: 0
number empty changes=0 incidents=0
field check: changes=1545 incidents=164 ok
change_request historical fixture=1500 pdi=1500 target=1500 within=yes
change_request open fixture=25 pdi=25 target=25 within=yes
change_request release fixture=20 pdi=20 target=20 within=yes
incident fixture=164 pdi=164 target=150 within=yes
incident caused_by fixture=74 pdi=74 target=80 within=yes
incident p1 fixture=10 pdi=10 target=10 within=yes
cmdb_ci fixture=300 pdi=300 target=300 within=yes
cmdb_rel_ci fixture=557 pdi=557 target=600 within=yes
sys_user_group fixture=6 pdi=6 target=6 within=yes
sys_user fixture=40 pdi=40 target=40 within=yes
cmn_schedule fixture=2 pdi=2 target=2 within=yes
task_ci fixture=2400 pdi=2400 target=2400 within=yes
std_change_record_producer fixture=0 pdi=0 target=6 exception=create ACL answer=false
cmn_schedule_blackout fixture=0 pdi=0 target=2 exception=policy code
load seconds: 18.4
created: 0
SEED OK
```

Seed 1 printed the same count block, all `within=yes`, with the same two exceptions.

Teardown, after that pair. Synthetic counts were 0, including `task_ci`, `sys_user_grmember`, `sys_user_has_role`, the three staging tables, import sets, and dictionary rows. Non-SYN totals matched the pre-seed snapshot stored in the manifest:

```
change_request total=105 baseline=105
cmdb_ci total=2784 baseline=2784
cmdb_rel_ci total=220 baseline=220
cmn_schedule total=17 baseline=17
incident total=67 baseline=67
sys_user total=637 baseline=637
sys_user_group total=53 baseline=53
task_ci total=167 baseline=167
TEARDOWN OK
```

`Synaptics Pointing Device Driver` and `SynthCore` are inside that `cmdb_ci` total of 2784. They were not deleted. See `docs/DISCOVERY.md` item 9.

Seed 3 is the full load on the empty instance. This is the duration to report. 690.2 seconds is about 11.5 minutes.

```
fixture hash: 7cf80a6c73939302d0d6ecbbb909dd2ed6bc16834561b86da0cdbc361492afcc
group created: SYN Fulfillment DevOps
group created: SYN Payments DevOps
group created: SYN Platform Ops
group created: SYN Release Management
group created: SYN Service Desk
group created: SYN Store DevOps
users ready: 40
integration user login: ok
integration user time_zone: empty
memberships created: 43
cis ready: 300
relationships created: 557
imported change_request 20/20
imported incident 90/90
imported change_request 1525/1525
imported incident 74/74
import sets: 2 state=loading
task_ci 2400/2400
number empty changes=0 incidents=0
field check: changes=1545 incidents=164 ok
change_request historical fixture=1500 pdi=1500 target=1500 within=yes
change_request open fixture=25 pdi=25 target=25 within=yes
change_request release fixture=20 pdi=20 target=20 within=yes
incident fixture=164 pdi=164 target=150 within=yes
incident caused_by fixture=74 pdi=74 target=80 within=yes
incident p1 fixture=10 pdi=10 target=10 within=yes
cmdb_ci fixture=300 pdi=300 target=300 within=yes
cmdb_rel_ci fixture=557 pdi=557 target=600 within=yes
sys_user_group fixture=6 pdi=6 target=6 within=yes
sys_user fixture=40 pdi=40 target=40 within=yes
cmn_schedule fixture=2 pdi=2 target=2 within=yes
task_ci fixture=2400 pdi=2400 target=2400 within=yes
std_change_record_producer fixture=0 pdi=0 target=6 exception=create ACL answer=false
cmn_schedule_blackout fixture=0 pdi=0 target=2 exception=policy code
sample change_request SYN-OPEN-16 number=CHG0033115 state=-5 type=normal active=true approval=not requested opened_at=2026-10-23 16:00:00 closed_at= close_code= short_description=SYN open change 16
sample change_request SYN-OPEN-21 number=CHG0033120 state=-4 type=normal active=true approval=requested opened_at=2026-10-23 16:00:00 closed_at= close_code= short_description=SYN open change 21
sample change_request SYN-OPEN-01 number=CHG0033100 state=-2 type=normal active=true approval=approved opened_at=2026-10-23 16:00:00 closed_at= close_code= short_description=SYN open change 1
sample change_request SYN-CHG-0001 number=CHG0031601 state=3 type=normal active=false approval=approved opened_at=2025-11-06 15:00:00 closed_at=2025-11-11 18:00:00 close_code=successful short_description=SYN rotate application log files
sample change_request SYN-CHG-1456 number=CHG0033055 state=4 type=standard active=false approval=not requested opened_at=2025-11-08 15:00:00 closed_at= close_code= short_description=SYN canceled standard change 1
sample incident SYN-INC-0159 number=INC0010250 state=1 active=true opened_at=2026-10-24 16:00:00 closed_at= close_code= short_description=SYN open incident 1
sample incident SYN-INC-0085 number=INC0010256 state=6 active=false opened_at=2025-11-11 15:30:00 closed_at= close_code=Workaround provided short_description=SYN caused incident 1
sample incident SYN-INC-0001 number=INC0010166 state=7 active=false opened_at=2025-11-09 21:00:00 closed_at=2025-11-10 06:00:00 close_code=Solution provided short_description=SYN trigger incident 1
load seconds: 690.2
created: 5071
SEED OK
GATE DONE
```

The five change samples are New (`-5`), Assess (`-4`), Scheduled (`-2`), Closed (`3`), and Canceled (`4`). The fixtures do not use Implement or Review. The three incident samples are New (`1`), Resolved (`6`), and Closed (`7`), which are the incident states the fixtures use. Every seeded change and incident had a number (`number empty changes=0 incidents=0`). `sys_number` was not edited. `created: 5071` is the before/after difference of the synthetic population query on this clean load.

The `import sets: 2` line is printed after the change and incident waves and before the affected-CI wave. The third set, for `u_syn_taskci_import`, is created while those 2,400 rows are posted and is recorded in the manifest. All three stay in state `loading`. Teardown deletes them by staging table name. See `docs/DISCOVERY.md` item 9.

## What was loaded

- 1,500 historical changes, 25 open changes, and 20 release changes. The releases are outside the 1,500. Total change fixtures: 1,545.
- 164 incidents (84 triggers, 74 caused-by, 6 open). Target 150 is "about", and 164 is within 10 percent. Caused-by 74 is within 10 percent of 80.
- 300 configuration items, 557 relationships (target about 600), 6 groups, 40 synthetic users, 2 maintenance schedules, 2,400 affected-CI rows.
- 43 membership rows: synthetic users added to the existing Change Management, CAB Approval, and eCAB Approval groups, plus the SYN DevOps, platform, service-desk, and release groups. The groups themselves were not edited. No approval definition was edited.
- The integration user from `.env`, Web service access only, direct role `sn_change_write` only. Login read `change_request` with HTTP 200. `time_zone` is stored empty, as Phase 0 found. `itil` was not granted. The user name is not repeated here.

Staging tables, recorded in the manifest and removed by teardown after the data rows: `u_syn_chg_import`, `u_syn_inc_import`, `u_syn_taskci_import`. Each has a transform map (`run_business_rules` false) and field maps. Import sets for those three tables are recorded too.

Historical changes have no `change_task` and no approval rows. Per-environment deployment tasks are not backfilled. They are created when a release runs in a later phase.

## Earlier gate attempts

Three attempts failed before the run above. Each failure is why the loader or teardown works the way it does. The business rules were not disabled.

1. A JSON array posted to the import API inserted only the first object. Seed now posts one JSON object at a time. The attempt stopped at `import returned an unexpected result`.
2. A Table API insert of `task_ci` returned HTTP 403 from business rule `Change Model: Read only CI (Insert)`. The 2,400 affected-CI rows go through `u_syn_taskci_import` with business rules off.
3. A direct delete of `task_ci` returned HTTP 403 from `Change Model: Read only CI (Delete)`. Deleting an affected CI on an open change is also blocked by `Prevent removal/update of primary CI`. Deleting the change removes its affected-CI rows. Teardown deletes changes first, then sweeps any `task_ci` still left. The passing teardown found none left (`task_ci syn=0`) and the non-SYN `task_ci` total was 167, matching the baseline.

An earlier teardown also showed that deleting `sys_dictionary` returns HTTP 403. Dropping the staging table (`sys_db_object`) removes its dictionary rows. Teardown drops the table first.

A membership sweep that deleted every `syn.` membership looped, because the instance puts the integration user back into `Conditional Script Writer` under a new sys_id. Teardown now deletes memberships only in the six SYN groups and in Change Management, CAB Approval, and eCAB Approval, then deletes the user. The passing teardown left `sys_user` at the baseline of 637.

## Deviations

1. **Groups are 6, not 8.** `SYN Change Management` and `SYN CAB` are not created. The existing Change Management, CAB Approval, and eCAB Approval groups hold the approvers. Membership rows only. `docs/DISCOVERY.md` item 5. The master prompt §8.2 group row is 6.
2. **Authority follows this PDI.** Normal Assess is `assignment_group` for every risk tier. Emergency Authorize is `cab_approval`. Standard is `pre_authorized`. The risk tier is for the CAB agenda and the CAB brief. `config/policy.yaml` matches item 5. S02 expects `assignment_group` (was `change_manager`). S03 expects `assignment_group` (was CAB). S05 expects `cab_approval` (was ECAB). Freeze, window, risk High, the human rejection, no implementation, the recorded rejection, and "deployed after CAB Approval with no go/no-go" are unchanged. Members of a synthetic DevOps group are the Assess approvers for changes assigned to that group.
3. **A release is a normal change** named `SYN RELEASE <service> <version>`. Member changes use `parent`. That change's assessment and authorization are the go-live authorization. `v_plugin` has no row that creates `rm_release`. The plugins that are present do not create it, and they were not activated. `docs/DISCOVERY.md` item 10.
4. **Standard change templates: fixture 0, target 6.** The create ACL on `std_change_record_producer` is `answer=false` with `admin_overrides=false`. The six out-of-box templates were not changed. `docs/DISCOVERY.md` item 9.
5. **Freezes: fixture 0, target 2.** Single-service freezes stay in policy code. `docs/DISCOVERY.md` item 8. There is no service reference on `cmn_schedule_blackout`, and storing `applies_to` did not show that the detector limits a freeze to one service.
6. **CI queries do not use `nameSTARTSWITHSYN`.** That operator is case-insensitive and trims a trailing space, so it also matches `Synaptics Pointing Device Driver` and `SynthCore`. Queries use `syn-` plus the four service names in full. The teardown baseline above kept both packages.
7. **Schedule `time_zone` is `US/Eastern`.** `America/New_York` is stored empty. Policy math still uses `America/New_York`. `docs/DISCOVERY.md` item 9.
8. **`incident.caused_by` does not exist.** The change-caused-incident link is `incident.parent`. An emergency change's `parent` is the triggering incident. `docs/DISCOVERY.md` item 9. The master prompt §8.4 uses `parent`.
9. **Import sets stay in state `loading`.** Described in the gate section. Teardown still removes them.
10. **The agent's risk score is not written in this phase.** Phase 2 must write `change_request.risk` and `impact` with a plain field update and show that the value survives every state transition up to Scheduled. If a transition recalculates it, stop and report. Do not call `PATCH /api/sn_chg_rest/change/{sys_id}/risk` or the Risk Calculator. `docs/DISCOVERY.md` item 6. This phase did not add that test.

## Dependencies

- `faker` 40.43.0: seeded fictional names for the synthetic users (§5.1).
- `pyyaml` 6.0.3: read `config/policy.yaml` (§5.1).
- `tzdata` 2026.5: transitive dependency of `faker` on Windows. It is in `uv.lock`. No direct import was added.

No other packages were added.

## Decisions closed

The four Phase 0 questions are closed in `docs/DISCOVERY.md` and `docs/ASSUMPTIONS.md`:

1. `rm_release` cannot be activated here. A release is a normal change.
2. History loads through an Import Set with business rules off. Later agent-created changes still use the Change API.
3. Synthetic users join the existing approver groups. Authority follows item 5.
4. The agent's score is a plain field update. The survival test waits for Phase 2.

`cm-agents discover` stays the repeatable Phase 0 probe. It is a utility command in the master prompt §7.3, not an agent command.
