# Phase 1 Report: Synthetic data

Status: committed locally on `grok-build`. Not pushed. Stopped here for review. Phase 2 has not started.

The instance is left seeded. `data/synthetic/` (fixtures, ground truth, and the manifest) stays gitignored. No plugin was activated. `.env` is not in this commit and is not in git history.

The caused-by link is loaded. The instance field is the human-made column `incident.u_caused_by` (label "Caused by Change", reference `change_request`). This gate printed `incident u_caused_by fixture=74 loaded=74 pdi=74 parent_used=0`. Teardown clears those values with the SYN incidents and leaves the column. The master prompt still says `caused_by` in §6.6, §8.4, and S07. `docs/ASSUMPTIONS.md` maps that name to `incident.u_caused_by`. The master prompt was not edited.

## Gate

The passing checks are `uv sync`, `ruff check cm_agents tests`, `pytest -q`, `cm-agents doctor`, and `seed --dry-run --anchor 2026-10-27` twice. The teardown before the first seed of this gate failed the `task_ci` baseline (313 against the stored 281). SYN counts were already 0. The gitignored manifest was discarded, and the rest of the gate ran: `seed --anchor 2026-10-27`, the same seed again, `teardown`, then `seed --anchor 2026-10-27` left on the instance. That rest run exited 0 and printed `GATE DONE`. `UV_PROJECT_ENVIRONMENT` is `%LOCALAPPDATA%\venvs\ChangeManagementAgent`. The run does not create `.venv` in the repository.

The log interleaved the second `uv sync` line onto the ruff banner. Both timing lines are from `uv sync`. Ruff printed `All checks passed!`.

```
===== uv sync =====
Resolved 23 packages in 8ms
===== ruff =====Audited
23 packages in 37ms
All checks passed!
===== pytest =====
79 passed in 11.98s
```

`test_dates_stay_inside_the_fixed_window` checks that no `opened_at`, `closed_at`, `resolved_at`, or `work_end` is later than the anchor, and that every `opened_at` is strictly before it. `test_patterns_are_within_three_points` checks P1–P6 in the fixtures at ±3 percentage points. `test_release_membership_and_ground_truth` checks payments failure 20.0, P6 count 12, and release on-time 85.0. Phase 0 was 51 passed. The previous accepted gate was 75 passed. This gate is 79. The four added tests are `test_save_manifest_replaces_a_temp_file_in_the_same_folder`, `test_save_manifest_retries_a_sharing_violation`, `test_save_manifest_keeps_the_original_when_the_lock_holds`, and `test_teardown_does_not_delete_the_human_caused_by_field`. No assertion was loosened or deleted.

Doctor, before the seeds and again after the instance was left seeded, printed the same build and the same plugin list. Both exited 0.

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

### Anchor

The anchor is midnight UTC on the load date. `default_anchor` uses the UTC date of the clock when `generate` runs. `seed --anchor YYYY-MM-DD` parses that date as UTC midnight and passes it in. This gate ran on 2026-10-29 and still pins `2026-10-27`, which prints as `2026-10-27 00:00:00`. The pin keeps the fixture hash comparable with the previous gate, and it keeps every `opened_at` before the load. The same value is stored on the fixture, in `ground_truth.json` (`anchor`), and in the manifest. `history_start` is the anchor minus 365 days.

Dry-run hashes, both runs, and every later seed in this gate:

```
anchor: 2026-10-27 00:00:00
fixture hash: 9131ae609660986728b97188837af2b09efd165cd5a9952f5885cf4e9042007d
dry-run hashes match
```

Every `opened_at` is before that anchor. The open-change samples below open on `2026-10-26 00:00:00`. Their planned start dates are in the next 6 weeks (`2026-11-03`, `2026-11-18`, `2026-11-23`). `work_end` on those open changes is empty. The previous samples (`SYN-OPEN-16`, `SYN-OPEN-21`, and `SYN-OPEN-01` at `2026-10-23 16:00:00`, and `SYN-INC-0159` at `2026-10-24 16:00:00`, loaded on 2026-10-22) are gone.

The fixed calendar still opens the four `2025.11.0` releases at `2025-10-26 02:00:00` UTC. That is one day before `history_start` (`2025-10-27 00:00:00`) for this anchor. The generator refuses an implemented non-release change whose `opened_at` is outside `[history_start, anchor)`, and it refuses any historical timestamp at or after the anchor. Those four release opens are allowed to sit outside the volume window. P1–P6 were not retuned. `ground_truth.json` `volume_by_type` sums to 1,541 of the 1,545 changes. The 25 open changes now fall inside the window (`opened_at` is the day before the anchor), so October's volume is 147. On-time stays 85.0.

The Pacific fall-back adjustment is unchanged. On that hour, `2025-11-02 08:00:00` UTC and `2025-11-02 09:00:00` UTC both format as `2025-11-02 01:00:00` Pacific, and this instance stores that wall time as `09:00` UTC. The fixture uses that later instant. The four `2025.11.0` release end times are the rows this moves. See `docs/DISCOVERY.md` item 9.

### Baseline before the clean load

Two platform jobs have moved the non-SYN `task_ci` total since the first snapshot. Both times the extra rows were `cert_follow_on_task` records from a daily job around 07:00 UTC. Their `correlation_id` is empty. They were not deleted. The baseline check was not weakened.

On 2026-10-27 the first teardown, while the instance had no SYN rows, matched every stored baseline except `task_ci`:

```
task_ci total=281 baseline=167
FAILED teardown before seed exit=1
```

SYN counts were 0, including `task_ci`. Samples from that day included `TASK0020102`, `TASK0020112`, `TASK0020114`, `TASK0020169`, `TASK0020206`, `TASK0020217`, `TASK0020230`, and `TASK0020232`. The manifest from the 2026-10-22 snapshot had no `anchor` field, and no SYN changes remained, so the next seed discarded it and captured baseline 281. The teardown after that clean load matched 281.

On 2026-10-29 the stored baseline was still 281 and the live total was 313. The pre-seed teardown of this gate printed:

```
change_request total=105 baseline=105
cmdb_ci total=2784 baseline=2784
cmdb_rel_ci total=220 baseline=220
cmn_schedule total=17 baseline=17
incident total=67 baseline=67
sys_user total=637 baseline=637
sys_user_group total=53 baseline=53
task_ci total=313 baseline=281
FAILED teardown before seed exit=1
```

SYN counts on that teardown were 0, including `task_ci`, the four standard-change tables, and `sys_dictionary`. The failure text in the log is `synthetic rows remain or a baseline count changedsys_user_group total=53 baseline=53` immediately before the `task_ci` line. `sys_user_group` matched. The mismatch is `task_ci`. That teardown stopped before the `incident.u_caused_by` remains check.

A read-only check then showed `task_ci` total 313, SYN 0, 51 rows created since 2026-10-27, and an empty `correlation_id` on all 313. Eight samples, all `cert_follow_on_task`: `TASK0020249` at `2026-10-27 07:00:11`, `TASK0020267`, `TASK0020270`, and `TASK0020275` on 2026-10-28, and `TASK0020291`, `TASK0020292`, `TASK0020298`, and `TASK0020302` on 2026-10-29. The same check still returned the `incident.u_caused_by` dictionary row (`reference=change_request`, label "Caused by Change", `active=true`).

The manifest still had the same seed and anchor `2026-10-27 00:00:00`, so the next seed would have reused baseline 281. SYN change, incident, CI, and user counts were already 0, so the gitignored manifest was deleted. The next seed captured baseline 313. The teardown after the clean load printed `task_ci total=313 baseline=313` and `TEARDOWN OK`. A later day will see this baseline move again when the 07:00 job adds more `cert_follow_on_task` rows. Those rows stay. The check stays.

### Clean load and idempotent seed

Seed 1 of this gate is the full load on an instance with no SYN rows. 639.3 seconds is about 10.7 minutes. `created: 5095` is the before/after difference of the synthetic population query. The first accepted clean load, before the six templates, was 5,071. The extra 24 rows are the six templates times the four standard-change tables.

Incidents load in two waves so a caused-by reference can point at a change that already exists. The log completed `imported change_request 20/20` (the releases), then `imported incident 90/90` (84 triggers and 6 open incidents), then `imported change_request 1525/1525`, then `imported incident 74/74` (the caused-by incidents, with `u_caused_by` set to the change sys_id). The field check includes `u_caused_by`.

```
anchor: 2026-10-27 00:00:00
fixture hash: 9131ae609660986728b97188837af2b09efd165cd5a9952f5885cf4e9042007d
template created: SYN Standard rotate TLS certificate
template created: SYN Standard OS patch on a non-PROD server
template created: SYN Standard restart application service
template created: SYN Standard scale out web tier node
template created: SYN Standard update DNS CNAME
template created: SYN Standard toggle a configuration flag
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
incident p1 fixture=10 pdi=10 target=10 within=yes
cmdb_ci fixture=300 pdi=300 target=300 within=yes
cmdb_rel_ci fixture=557 pdi=557 target=600 within=yes
sys_user_group fixture=6 pdi=6 target=6 within=yes
sys_user fixture=40 pdi=40 target=40 within=yes
cmn_schedule fixture=2 pdi=2 target=2 within=yes
task_ci fixture=2400 pdi=2400 target=2400 within=yes
incident u_caused_by fixture=74 loaded=74 pdi=74 parent_used=0
incident resolved_or_closed=158 resolved_at_empty=0 resolved_before_opened=0
std_change_record_producer fixture=6 pdi=6 target=6 within=yes
std_change_proposal fixture=6 pdi=6 target=6 within=yes
std_change_producer_version fixture=6 pdi=6 target=6 within=yes
std_change_template fixture=6 pdi=6 target=6 within=yes
cmn_schedule_blackout fixture=0 pdi=0 target=2 exception=policy code
load seconds: 639.3
created: 5095
SEED OK
```

`loaded` counts SYN incidents with `u_caused_by` set. `pdi` counts SYN incidents whose `u_caused_by.correlation_id` starts with `SYN-`. The dot-walk returned HTTP 200. `parent_used` counts SYN incidents with `parent` set. The gate fails unless all four numbers are 74, 74, 74, and 0.

Seed 2 is the idempotency check on that load. It created nothing (`load seconds: 20.6`, `created: 0`, `relationships created: 0`, `memberships created: 0`, `task_ci created: 0`, `import sets: 3 state=loading`). The six templates printed as `template present`. The count block matched, including `incident u_caused_by fixture=74 loaded=74 pdi=74 parent_used=0`, `resolved_at_empty=0`, `resolved_before_opened=0`, and 6 on each of the four standard-change tables. An idempotent seed skips existing correlation ids, so `u_caused_by` is written on insert.

The previous accepted gate's clean load was `load seconds: 700.0`, `created: 5095`, and its idempotent seed was `load seconds: 23.3`, `created: 0`. That gate printed `incident caused_by fixture=74 loaded=0 pdi_parent=0 decision=open`. This gate is the one that stores the 74 links.

### Teardown, including the six templates

Synthetic counts were 0. That includes the four standard-change tables, `task_ci`, `sys_user_grmember`, `sys_user_has_role`, the three data staging tables, import sets, and dictionary rows. Non-SYN totals matched the new baseline:

```
std_change_record_producer syn=0
std_change_proposal syn=0
std_change_producer_version syn=0
std_change_template syn=0
change_request total=105 baseline=105
cmdb_ci total=2784 baseline=2784
cmdb_rel_ci total=220 baseline=220
cmn_schedule total=17 baseline=17
incident total=67 baseline=67
sys_user total=637 baseline=637
sys_user_group total=53 baseline=53
task_ci total=313 baseline=313
incident.u_caused_by remains element=u_caused_by reference=change_request label=Caused by Change active=true
TEARDOWN OK
```

`Synaptics Pointing Device Driver` and `SynthCore` are inside that `cmdb_ci` total of 2784. They were not deleted. See `docs/DISCOVERY.md` item 9.

Deleting the SYN incidents clears the `u_caused_by` values. Teardown then requires exactly one `sys_dictionary` row `name=incident^element=u_caused_by`, type `reference`, reference `change_request`, label "Caused by Change", active `true`, and prints the remains line above. It does not delete that column. The pre-seed teardown of this gate failed on the `task_ci` baseline before that check. The teardown after seed 2 is the one that printed the remains line.

Table API `DELETE` on `std_change_proposal`, `std_change_record_producer`, `std_change_producer_version`, and `std_change_template` is HTTP 403. Teardown posts one import row through `u_syn_std_delete`. The transform's onBefore script calls `GlideRecord.deleteRecord` with `setWorkflow(false)`. It then drops that staging table, its dictionary, its transform map and script, and the matching `sys_update_xml`. The out-of-box proposal `STDCHG0001002` (`Replace printer toner`) was not deleted. The catalog and category for the six proposals were copied at runtime from the producer `Replace printer toner` (`sc_catalogs` `e0d08b13c3330100c8b837659bba8fb4`, category `651395bc53231300e321ddeeff7b1221`). `glide.approval_engine.std_change_proposal` is `off`, so admin publishes a proposal by setting `approval=approved`. There is no `sysapproval_approver` row for that step. The create ACL on `std_change_record_producer` was not changed.

### Seed after teardown

The previous accepted gate's post-teardown seed created the six groups, the six templates, the users, and the 300 CIs, then died writing `data/synthetic/manifest.json`:

```
PermissionError: [Errno 13] Permission denied: '...\data\synthetic\manifest.json'
FAILED seed 3 exit=1
```

OneDrive had the file locked. One hundred twenty relationships were already on the instance and were not yet in the manifest. The resume created the other 437 relationships and passed that gate (`load seconds: 573.2`, `created: 4552`). A follow-up seed recorded the skipped relationships and created nothing (`load seconds: 20.5`, `created: 0`). That gate still printed `loaded=0`.

`save_manifest` now writes `{name}.tmp` in the same folder and replaces the original with `os.replace`. A sharing violation (`PermissionError`) is retried up to six times, with the delay starting at 0.2 seconds and doubling to a cap of 1 second. If replace fails, the previous manifest stays. The three unit tests cover a clean replace, one sharing violation then success, and a lock that holds for every attempt.

This gate's seed 3 did not hit a lock. It completed as a clean load:

```
load seconds: 640.0
created: 5095
incident u_caused_by fixture=74 loaded=74 pdi=74 parent_used=0
incident resolved_or_closed=158 resolved_at_empty=0 resolved_before_opened=0
SEED OK
```

The fixture hash on that seed is the same `9131ae609660986728b97188837af2b09efd165cd5a9952f5885cf4e9042007d`. The import waves were again 20 releases, 90 incidents, 1525 changes, and 74 caused incidents. Field check was `changes=1545 incidents=164 ok`. Templates were created again. `import sets: 2 state=loading`.

The manifest on disk after seed 3 has `anchor` `2026-10-27 00:00:00`, `task_ci` baseline 313, and these recorded counts: `change_request` 1545, `incident` 164, `cmdb_ci` 300, `cmdb_rel_ci` 557, `task_ci` 2400, `sys_user_group` 6, `sys_user` 41 (40 synthetic users plus the integration user), `sys_user_grmember` 43, and 6 on each of `std_change_proposal`, `std_change_record_producer`, `std_change_producer_version`, and `std_change_template`. Seed 3 is the load left on the instance.

Samples from the seeded instance. The five change states are New (`-5`), Assess (`-4`), Scheduled (`-2`), Closed (`3`), and Canceled (`4`). The fixtures do not use Implement or Review. The three incident states are New (`1`), Resolved (`6`), and Closed (`7`).

```
sample change_request SYN-OPEN-16 number=CHG0039297 state=-5 type=normal active=true approval=not requested opened_at=2026-10-26 00:00:00 start_date=2026-11-18 00:00:00 work_end= closed_at= close_code= short_description=SYN open change 16
sample change_request SYN-OPEN-21 number=CHG0039302 state=-4 type=normal active=true approval=requested opened_at=2026-10-26 00:00:00 start_date=2026-11-23 00:00:00 work_end= closed_at= close_code= short_description=SYN open change 21
sample change_request SYN-OPEN-01 number=CHG0039282 state=-2 type=normal active=true approval=approved opened_at=2026-10-26 00:00:00 start_date=2026-11-03 00:00:00 work_end= closed_at= close_code= short_description=SYN open change 1
sample change_request SYN-CHG-0001 number=CHG0037783 state=3 type=normal active=false approval=approved opened_at=2025-11-06 15:00:00 start_date=2025-11-11 15:00:00 work_end=2025-11-11 17:00:00 closed_at=2025-11-11 18:00:00 close_code=successful short_description=SYN rotate application log files
sample change_request SYN-CHG-1456 number=CHG0039237 state=4 type=standard active=false approval=not requested opened_at=2025-11-08 15:00:00 start_date= work_end= closed_at= close_code= short_description=SYN canceled standard change 1
sample incident SYN-INC-0159 number=INC0010906 state=1 active=true opened_at=2026-10-26 00:00:00 resolved_at= closed_at= close_code= u_caused_by= short_description=SYN open incident 1
sample incident SYN-INC-0085 number=INC0010912 state=6 active=false opened_at=2025-11-11 15:30:00 resolved_at=2025-11-11 19:30:00 closed_at= close_code=Workaround provided u_caused_by=178f45a0c3905750aef2be1d050131f3 short_description=SYN caused incident 1
sample incident SYN-INC-0001 number=INC0010822 state=7 active=false opened_at=2025-11-09 21:00:00 resolved_at=2025-11-10 05:00:00 closed_at=2025-11-10 06:00:00 close_code=Solution provided u_caused_by= short_description=SYN trigger incident 1
```

These numbers are from seed 3, the load left on the instance. Seed 1's samples (`CHG0037752`, `INC0010748` with `u_caused_by=c6f985a8c39c1750aef2be1d05013194`) were removed by the teardown.

Of 158 SYN incidents in Resolved or Closed, `resolved_at` is empty on 0 and earlier than `opened_at` on 0. The field compare is `resolved_atLT_FIELDopened_at`. The gate fails if either count is not 0.

Every seeded change and incident had a number (`number empty changes=0 incidents=0`). `sys_number` was not edited.

The `import sets: 2` line is printed after the change and incident waves and before the affected-CI wave. The third set, for `u_syn_taskci_import`, is created while those 2,400 rows are posted and is recorded in the manifest. All three stay in state `loading`. Teardown deletes them by staging table name. The template-delete import set is removed inside teardown and is not left in `loading`. See `docs/DISCOVERY.md` item 9.

## What was loaded

- 1,500 historical changes, 25 open changes, and 20 release changes. The releases are outside the 1,500. Total change fixtures: 1,545.
- 164 incidents (84 triggers, 74 caused-by stored in `incident.u_caused_by`, 6 open). Target 150 is "about", and 164 is within 10 percent. The 74 links are within 10 percent of 80. `parent_used=0`. `SYN-INC-0085` (`INC0010912`) holds `u_caused_by=178f45a0c3905750aef2be1d050131f3`. The open incident and the trigger sample have `u_caused_by` empty.
- 300 configuration items, 557 relationships (target about 600), 6 groups, 40 synthetic users, 2 maintenance schedules, 2,400 affected-CI rows.
- 6 standard change templates, each recorded as a proposal, a producer, a version, and a template. S01 uses `SYN Standard rotate TLS certificate`. Suggested groups: TLS, restart, and scale-out to SYN Store DevOps; OS patch and DNS to SYN Platform Ops; the configuration flag to SYN Payments DevOps.
- 43 membership rows: synthetic users added to the existing Change Management, CAB Approval, and eCAB Approval groups, plus the SYN DevOps, platform, service-desk, and release groups. The groups themselves were not edited. No approval definition was edited.
- The integration user from `.env`, Web service access only, direct role `sn_change_write` only. Login read `change_request` with HTTP 200. `time_zone` is stored empty, as Phase 0 found. `itil` was not granted. The user name is not repeated here.

Staging tables, recorded in the manifest and removed by teardown after the data rows: `u_syn_chg_import`, `u_syn_inc_import`, `u_syn_taskci_import`. Each has a transform map (`run_business_rules` false) and field maps. Import sets for those three tables are recorded too.

Historical changes have no `change_task` and no approval rows. Per-environment deployment tasks are not backfilled. They are created when a release runs in a later phase.

## Earlier gate attempts

Three attempts failed before the first accepted candidate. Each failure is why the loader or teardown works the way it does. The business rules were not disabled.

1. A JSON array posted to the import API inserted only the first object. Seed now posts one JSON object at a time. The attempt stopped at `import returned an unexpected result`.
2. A Table API insert of `task_ci` returned HTTP 403 from business rule `Change Model: Read only CI (Insert)`. The 2,400 affected-CI rows go through `u_syn_taskci_import` with business rules off.
3. A direct delete of `task_ci` returned HTTP 403 from `Change Model: Read only CI (Delete)`. Deleting an affected CI on an open change is also blocked by `Prevent removal/update of primary CI`. Deleting the change removes its affected-CI rows. Teardown deletes changes first, then sweeps any `task_ci` still left. The passing teardown of this gate found none left (`task_ci syn=0`). The non-SYN `task_ci` total is 313, matching the baseline captured on 2026-10-29. The 2026-10-27 baseline was 281. The 2026-10-22 snapshot was 167. The daily `cert_follow_on_task` job is what moved those totals.

An earlier teardown also showed that deleting `sys_dictionary` returns HTTP 403. Dropping the staging table (`sys_db_object`) removes its dictionary rows. Teardown drops the table first.

A membership sweep that deleted every `syn.` membership looped, because the instance puts the integration user back into `Conditional Script Writer` under a new sys_id. Teardown now deletes memberships only in the six SYN groups and in Change Management, CAB Approval, and eCAB Approval, then deletes the user. The passing teardown left `sys_user` at the baseline of 637.

The previous review's post-teardown seed hit the OneDrive lock described above. This gate writes the manifest by replacing a temp file in the same folder. Seed 3 of this gate completed without a lock and is the load left on the instance.

## Deviations

1. **Groups are 6, not 8.** `SYN Change Management` and `SYN CAB` are not created. The existing Change Management, CAB Approval, and eCAB Approval groups hold the approvers. Membership rows only. `docs/DISCOVERY.md` item 5. The master prompt §8.2 group row is 6.
2. **Normal changes take two approvals, at every risk tier.** Assess is the assignment group. Authorize is CAB Approval. The risk tier does not select the approver. Two probe normal changes, both assigned to Change Management, were walked from New to Scheduled. Admin approved one approver at each step through the Table API. No state write to Authorize or Scheduled was required. Both changes were deleted. Residue queries returned 0. `approver.group` on `sysapproval_approver` is the `sysapproval_group` sys_id.

   Low, risk `4`, impact `3`, change `ce6d3b3bc38cdf10aef2be1d05013160`:

   | State | Approval record | State of the row | `sys_created_on` |
   |---|---|---|---|
   | New (`-5`) | none | | |
   | Assess (`-4`) | `sysapproval_group` Change Management | `requested`, then `approved` | `2026-10-27 19:27:50` |
   | Assess | five approvers: danielle johnson, joshua walker, Chuck Tomasi, jill rhodes, Change Manager | `requested` | `2026-10-27 19:27:51` |
   | Authorize (`-3`) | `sysapproval_group` CAB Approval `417d3f3bc38cdf10aef2be1d0501316b` | `requested`, then `approved` | `2026-10-27 19:28:01` |
   | Authorize | eleven CAB approvers, Ron Kettering through jeffery wagner | `requested` | `2026-10-27 19:28:01` to `19:28:02` |
   | Scheduled (`-2`) | both group rows `approved`. Risk still `4`. | | |

   Admin approved danielle johnson (`1e6d3b3bc38cdf10aef2be1d050131d8`) at Assess and Ron Kettering (`117d7f3bc38cdf10aef2be1d05013109`) at Authorize. The other approvers became `not_required`. The change moved itself.

   High, risk `2`, impact `1`, change `4f7d337bc38cdf10aef2be1d05013130`: the same two steps. Change Management group `requested` at `2026-10-27 19:28:10` (`1f7d337bc38cdf10aef2be1d05013183`). Admin approved jill rhodes (`177d337bc38cdf10aef2be1d050131c3`). CAB Approval group `requested` at `2026-10-27 19:28:13` (`3f7d737bc38cdf10aef2be1d050131ae`). Admin approved jeffery wagner (`048db37bc38cdf10aef2be1d05013103`). The change reached Scheduled with `approval=approved` and risk still `2`.

   `config/policy.yaml` `change_authority` records both steps for `normal_low`, `normal_moderate`, and `normal_high`, and `cab_approval` at Authorize for emergency. Standard stays `pre_authorized`. S02 expects an authorization interrupt at each normal step and one `go_no_go`. S03 expects the assignment group to approve and CAB Approval to reject. S05 expects `cab_approval` at Authorize. Freeze, window, risk High, the human rejection, no implementation, the recorded rejection, and "deployed after CAB Approval with no go/no-go" are unchanged. Members of a synthetic DevOps group are the Assess approvers for changes assigned to that group. The full approver names are in `docs/DISCOVERY.md` item 5.
3. **A release is a normal change** named `SYN RELEASE <service> <version>`. Member changes use `parent`. That change's assessment and authorization are the go-live authorization. `v_plugin` has no row that creates `rm_release`. The plugins that are present do not create it, and they were not activated. `docs/DISCOVERY.md` item 10.
4. **Standard change templates: 6 of 6.** A Standard Change Template Proposal (`proposal_type=1`) publishes the template when `state=2` and `approval=approved`. The six names are `SYN Standard rotate TLS certificate`, `SYN Standard OS patch on a non-PROD server`, `SYN Standard restart application service`, `SYN Standard scale out web tier node`, `SYN Standard update DNS CNAME`, and `SYN Standard toggle a configuration flag`. Teardown removed all four rows for each name and left 0 residue, as the teardown block shows. S01 uses `SYN Standard rotate TLS certificate`. The create ACL was not given an exception. `docs/DISCOVERY.md` item 9.
5. **Freezes: fixture 0, target 2.** Single-service freezes stay in policy code. `docs/DISCOVERY.md` item 8. There is no service reference on `cmn_schedule_blackout`, and storing `applies_to` did not show that the detector limits a freeze to one service.
6. **CI queries do not use `nameSTARTSWITHSYN`.** That operator is case-insensitive and trims a trailing space, so it also matches `Synaptics Pointing Device Driver` and `SynthCore`. Queries use `syn-` plus the four service names in full. The teardown baseline above kept both packages.
7. **Schedule `time_zone` is `US/Eastern`.** `America/New_York` is stored empty. Policy math still uses `America/New_York`. `docs/DISCOVERY.md` item 9.
8. **`incident.caused_by` is absent. The approved field is `incident.u_caused_by`, and the 74 links are loaded.** `sys_dictionary` `name=incident^element=caused_by` and `name=task^element=caused_by` each returned 0 rows. On 2026-10-29 `name=incident^element=u_caused_by` returned one row: sys_id `6a6109e4c3d81750aef2be1d050131a9`, element `u_caused_by`, column label "Caused by Change", internal type `reference`, reference `change_request`, active `true`, max length 32, created by `admin` at `2026-10-29 13:43:44`. `name=task^element=u_caused_by` returned 0 rows. `nameINincident,task^reference=change_request` returns that row and no other. Seed does not create the column. It writes the fixture key `caused_by` into `incident.u_caused_by`. The gate printed `incident u_caused_by fixture=74 loaded=74 pdi=74 parent_used=0` on seed 1, seed 2, and seed 3. `parent_used` stays 0. An emergency change's `parent` is still the triggering incident. A release member's `parent` is still the release change.

   Teardown deletes the SYN incidents, which clears the values, and does not delete the column. The teardown after seed 2 printed `incident.u_caused_by remains element=u_caused_by reference=change_request label=Caused by Change active=true`. The pre-seed teardown failed on `task_ci` before that check. A separate read after that failure still showed the dictionary row.

   The master prompt still says `caused_by` in §6.6, §8.4, and S07. `docs/ASSUMPTIONS.md` maps those sections to `incident.u_caused_by`. The master prompt was not edited. §4.2 also says `caused_by`. The mapping recorded for this decision is the three sections named above.

   `incident.problem_id` and `task.problem_id` each returned 0 rows. `incident.rfc` and `task.rfc` each returned 0 rows. No `incident` or `task` element references `problem`. Problem Management is active: `v_plugin` id `com.snc.problem`, name "Problem Management", `active=active`. `problem.rfc` still references `change_request`. Nothing was changed for those fields or for that plugin. `docs/DISCOVERY.md` item 9.
9. **Import sets stay in state `loading`.** Described in the gate section. Teardown still removes them.
10. **The agent's risk score is not written in this phase.** Phase 2 must write `change_request.risk` and `impact` with a plain field update and show that the value survives every state transition up to Scheduled. If a transition recalculates it, stop and report. Do not call `PATCH /api/sn_chg_rest/change/{sys_id}/risk` or the Risk Calculator. `docs/DISCOVERY.md` item 6. The two authority probes kept the risk value that was set on them (`4` and `2`) through Scheduled. That was not the Phase 2 survival test, and this phase did not add that test.

Phase 2 also has to show that the Intake agent can add affected CIs to a new change through the Change API before any code relies on that. A Table API insert into `task_ci` is blocked by `Change Model: Read only CI (Insert)`. No action was taken on that in this phase.

## Dependencies

- `faker` 40.43.0: seeded fictional names for the synthetic users (§5.1).
- `pyyaml` 6.0.3: read `config/policy.yaml` (§5.1).
- `tzdata` 2026.5: transitive dependency of `faker` on Windows. It is in `uv.lock`. No direct import was added.

No other packages were added.

## Decisions closed

The four Phase 0 questions are closed in `docs/DISCOVERY.md` and `docs/ASSUMPTIONS.md`:

1. `rm_release` cannot be activated here. A release is a normal change.
2. History loads through an Import Set with business rules off. Later agent-created changes still use the Change API.
3. Synthetic users join the existing approver groups. A normal change is approved by its assignment group at Assess and by CAB Approval at Authorize. An emergency change is approved by CAB Approval at Authorize.
4. The agent's score is a plain field update. The survival test waits for Phase 2.

`cm-agents discover` stays the repeatable Phase 0 probe. It is a utility command in the master prompt §7.3, not an agent command.

Where to store a change-caused incident is closed. The instance field is `incident.u_caused_by`. When §6.6 creates an incident for a failed deployment, it writes that field. The Phase 2 risk-survival test was not added.
