# Discovery

Phase 0 findings for this Personal Developer Instance. API paths are relative to the instance. Secrets, passwords, and the instance host are omitted.

The probes ran on 2026-10-21. `cm-agents discover` checks outbound email first and deletes every `SYN-PROBE` record, including the approvals, approval groups, change tasks, CI links, and conflict rows it created. The final run left 0 rows on every residue query below.

## Email gate

Outbound email is disabled, so the probe was allowed to create records.

- Check: `GET /api/now/table/sys_properties?sysparm_query=nameINglide.email.smtp.active,glide.email.read.active` and `GET /api/now/table/sys_email_account?sysparm_query=active=true`.
- Evidence: `glide.email.smtp.active` is `false`, `glide.email.read.active` is `false`, and the active email-account query returned 0 rows.
- Decision: the probe may create `SYN-PROBE` changes while both stay false and no active email account exists. If either check fails, discovery stops before any write and exits 2.

## 1. Instance release and build

Question: what release is this instance?

- Check: `GET /api/now/table/sys_properties` for `glide.buildname`, `glide.buildtag`, and `glide.war`.
- Evidence: `glide.buildname` and `glide.buildtag` are absent. `glide.war` and `glide.war.assigned` are `glide-australia-02-11-2026__patch3-05-25-2026_06-12-2026_1106.zip`.
- Decision: treat the instance as the Australia family, patch 3. `cm-agents doctor` reports the `glide.war` value when the two build properties are missing. Do not assume a build name that this instance does not have.

## 2. Plugins

Question: which of the change, conflict, CAB, release, and Change REST plugins are active?

- Check: `GET /api/now/table/v_plugin` with `nameLIKEChange^ORnameLIKERelease^ORnameLIKECAB^ORnameLIKEConflict`, plus direct queries for `name=Release Management` and `id=com.snc.release_management`.
- Evidence for the plugins the design depends on:

| Plugin | Id | Active |
|---|---|---|
| Change Management - Core | `com.snc.change_management` | active |
| Change Management - Standard Change Catalog | `com.snc.change_management.standard_change_catalog` | active |
| Change Management - Collision Detector | `com.snc.change.collision` | active |
| Change Management - CAB Workbench | `com.snc.change_management.cab` | active |
| Change Management - Change Models | `com.snc.change_management.change_model` | active |
| Change Management - Risk Calculator | `com.snc.bestpractice.change_risk` | active |
| Change Management - Risk Assessment | `com.snc.change_management.risk_assessment` | inactive |
| Change Management - Risk Intelligence | `com.snc.change_management.ml.risk` | inactive |
| Change Management - Success Probability | `com.snc.change_management.success_probability` | inactive |
| Change Management - Change Success Score | `com.snc.change_management.change_success_score` | inactive |
| Change Management - Predictive Intelligence Core | `com.snc.change_management.ml` | inactive |
| Read only roles for Release Management | `com.snc.release_management_read_roles` | active |
| ReleaseOps Backend | `com.glide.releaseops` | inactive |
| ReleaseOps global scope support | `com.glide.releaseopsglobal` | inactive |

There is no plugin named `Release Management` and no plugin with id `com.snc.release_management`. There is no plugin named Change Management REST API. The API is an active scripted REST service, `Change Management`, at `/api/sn_chg_rest/change` (`sys_ws_definition`, 43 operations, authentication required). The probe called `POST /normal`, `POST /emergency`, `POST /standard/{template}`, `GET /{sys_id}/nextstates`, `PATCH /{sys_id}/risk`, and `POST` plus `GET /{sys_id}/conflict`. CAB also has an active internal API at `/api/sn_change_cab/cab`.

- Decision: use the active Change Management APIs and models as they are. Do not activate Risk Assessment, Predictive Intelligence, Success Probability, or ReleaseOps. Activating classic Release Management is a separate question in item 10.

## 3. Choice values

Question: what are the stored values for the fields the agents and the loader will write?

- Check: `GET /api/now/table/sys_choice` filtered by table, element, and `language=en`. Impact, urgency, and priority are not choices on `change_request` or `incident`. They are choices on `task`. Incident queries returned 0 rows.
- Evidence:

| Field | Active values |
|---|---|
| `change_request.type` | `standard` Standard, `normal` Normal, `emergency` Emergency, `model` Model |
| `change_request.state` | `-5` New, `-4` Assess, `-3` Authorize, `-2` Scheduled, `-1` Implement, `0` Review, `3` Closed, `4` Canceled |
| `change_request.risk` | `2` High, `3` Moderate, `4` Low. Inactive: `1` Very High, `5` None |
| `change_request.close_code` | `successful` Successful, `successful_issues` Successful with issues, `unsuccessful` Unsuccessful |
| `change_task.change_task_type` | `planning`, `implementation`, `testing`, `review` |
| `task.impact` | `1` 1 - High, `2` 2 - Medium, `3` 3 - Low |
| `task.urgency` | `1` 1 - High, `2` 2 - Medium, `3` 3 - Low |
| `task.priority` | `1` 1 - Critical, `2` 2 - High, `3` 3 - Moderate, `4` 4 - Low, `5` 5 - Planning |
| `conflict.type` | `ci_already_scheduled`, `parent_ci_already_scheduled`, `child_ci_already_scheduled`, `blackout`, `parent_blackout`, `child_blackout`, `not_in_maintenance_window`, `parent_not_in_maintenance_window`, `child_not_in_maintenance_window`, `assigned_to_already_scheduled` |
| `rm_release.state` | no rows, and the table itself is absent (item 10) |

`GET /api/now/table/dl_u_priority` returned the priority matrix. Impact 1 and urgency 1 map to priority 1. The other eight rows step down to priority 4 for impact 3 and urgency 3. `dl_problem_priority` is the problem matrix, not the incident matrix.

- Decision: agents use `normal`, `emergency`, and `standard` only. `model` belongs to the other change models and is not an ITIL type for this system. Store the numeric state and risk values above. Close codes already match the intended Successful / Successful with issues / Unsuccessful mapping. Read impact, urgency, and priority from `task`, and use `dl_u_priority` when a priority must be derived.

## 4. State models, mandatory fields, and transitions

Question: what can each change type do, and which fields are mandatory?

- Check: `chg_model` for active models on `change_request`; `sttrm_state_transition` per model; `sys_dictionary` where `mandatory=true` on `change_request`; then a `SYN-PROBE` change of each type, deleted afterward.
- Evidence: dictionary `mandatory=true` returned 0 rows. The state model enforces the required data. Six models exist. The three ITIL models are:

| Model | sys_id | Preset | In UI |
|---|---|---|---|
| Normal (default) | `007c4001c343101035ae3f52c1d3aeb2` | `type=normal` | yes |
| Emergency | `62d10fa1c303101035ae3f52c1d3aec1` | `type=emergency` | yes |
| Standard | `e55d0bfec343101035ae3f52c1d3ae49` | `type=standard` | no (catalog) |

Change Registration, Cloud Infrastructure, and Unauthorized Change are also active and were not modified. Model `read_roles` are `itil,sn_change_read`.

Transitions on the Normal model: New→Assess (manual), New→Canceled, Assess→Authorize (automatic), Assess→New (automatic and manual), Assess→Canceled, Authorize→Scheduled (automatic), Authorize→New (automatic), Authorize→Canceled, Scheduled→Implement (manual), Scheduled→Canceled, Implement→Review (automatic and manual), Implement→Canceled, Review→Closed (manual). There is no New→Closed transition.

Emergency skips Assess: New→Authorize (manual), then the authorize, implement, review, close, and cancel paths, including Authorize→Review (automatic).

Standard has no Assess and no Authorize: New→Scheduled (manual), Scheduled→Implement, Implement→Review, Review→Closed, plus cancel.

Condition records tied to these names include: Assess→Authorize requires Approval = Approved ("Approved by Assignment Group"); Authorize→Scheduled requires CAB approval; Assess→New on rejection by the assignment group; Authorize→New on rejection by CAB Approval; Review→Closed requires a close code and close notes; Implement→Review has a "No active Change Tasks" script and a non-script path; Scheduled→Implement requires the change not be on hold; New→Authorize requires an assignment group. Some condition rows belong to other models, so the live probe is the source for the three ITIL types.

Probe, after a Table API read with `display_value=false`:

- Normal create landed in New (`-5`), type `normal`, model Normal, risk empty, impact `3`, approval `not requested`. `GET /{sys_id}/nextstates` returned Assess (`-4`), Canceled (`4`), and New (`-5`). `PATCH` state `3` returned HTTP 403 from business rule `Change Model: Check State Transition`, and the state stayed `-5`. `PATCH` through `/api/sn_chg_rest/change/normal/{sys_id}` to `-4` succeeded. State became Assess and approval became `requested`.
- Emergency create landed in New. Next states were Authorize (`-3`), Canceled, and New. The illegal close stayed `-5` with the same business rule. The move to `-3` succeeded and approval became `requested`.
- Standard was created from the template named `Replace printer toner` (looked up by name). It landed in New, not Scheduled. Approval was already `approved`. `risk_impact_analysis` was Low, risk was empty, and the template set the assignment group to Help Desk and replaced the description. Next states were Scheduled (`-2`), Canceled, and New. The move to `-2` succeeded. No approval rows were created.

- Decision: create normal, emergency, and standard changes through the Change API. Move them only through `nextstates` for that record. Do not write Closed, or any other state, by jumping the model. Do not modify the models or the OOB standard templates. Standard changes need an explicit New→Scheduled move after creation. The fields the probe had to send for a successful move were a short description and, for the approval behavior in item 5, an assignment group. Close code and close notes are required by the Review→Closed condition when that transition is used later.

## 5. Approvals

Question: who receives approvals for a normal change and an emergency change, and what is the least invasive way to involve synthetic approvers?

- Check: `chg_approval_def`, existing CAB-related groups, then the `SYN-PROBE` transitions above and `GET /api/now/table/sysapproval_approver?sysparm_query=sysapproval={change}`.
- Evidence: three definitions, all mandatory, wait for the first response:

| Definition | Action | Source |
|---|---|---|
| CAB Approval | add group approval | group CAB Approval |
| Assignment Group Manager Approval | add user approval | `assignment_group.manager` |
| Assignment Group Approval | add group approval | group field `assignment_group` |

`chg_policy_applied` returned 0 rows. Groups already on the instance include Change Management (`a715cd759f2002002920bde8132e7018`), CAB Approval (`b85d44954a3623120004689b2d5dd60a`), and eCAB Approval (`b97e89b94a36231201676b73322a0311`).

The probe set `assignment_group` to Change Management before moving state:

- Normal, now in Assess: two Requested approvals, for Chuck Tomasi and Change Manager. The generated `sysapproval_group` pointed at Change Management.
- Emergency, now in Authorize: six Requested approvals, for Ron Kettering, Christen Mitchell, Bernard Laboy, Howard Johnson, cab approver, and Luke Wilson. The generated `sysapproval_group` pointed at CAB Approval.
- Standard, moved to Scheduled: 0 approval rows.

The normal path followed the assignment group. The emergency path followed CAB Approval even though the assignment group was Change Management. Neither path splits by the risk values Low, Moderate, and High.

- Decision: do not create approval definitions and do not edit the OOB ones. Phase 1 adds synthetic users to the existing Change Management, CAB Approval, and eCAB Approval groups. It adds membership rows only. It does not change the groups or any approval policy. Authority follows this instance, because ServiceNow is the system of record. `config/policy.yaml` `change_authority` is `assignment_group` for every normal risk tier and `cab_approval` for emergency. Standard stays `pre_authorized`. The risk tier is used only for the CAB agenda and the CAB brief. Members of the synthetic DevOps group are the Assess approvers for changes assigned to that group. `SYN Change Management` and `SYN CAB` are not created. Agents must not write `sysapproval_approver`.

## 6. Risk recalculation

Question: if the agent writes risk or impact, will the instance overwrite it?

- Check: active rows in the risk-condition table, then on a normal `SYN-PROBE` change with a far-future window (`2026-12-15 02:00:00` to `04:00:00`) and no configuration item: Table API `PATCH` `risk=2` (High) and `impact=1` (High), then `PATCH` the short description, then `PATCH /api/sn_chg_rest/change/{sys_id}/risk`.
- Evidence: a bare create leaves risk empty and impact already `3` (Low). The High / High write was still there after the short-description update (`risk=2`, `impact=1`). The calculate call returned HTTP 200 and the record then read `risk=4` (Low) and `impact=3` (Low). Active conditions are Insufficient lead time → High (order 100), Critical service changed → High and impact High (order 200), Critical service affected → High and impact High (order 300), and No expected risk issues found → Low and impact Low (order 400). The far-future window and the empty CI match the last of those, which matches the calculate result.
- Decision: do not disable the Risk Calculator. The agent's score is the value on `change_request.risk` and `impact`. Write both with a plain field update. Never call `PATCH /api/sn_chg_rest/change/{sys_id}/risk` or the Risk Calculator. A Table API write survived a later ordinary update in this probe. The calculate call overwrote both fields. Phase 2 adds an integration test that the agent-written risk survives every state transition up to Scheduled. If any transition recalculates it, stop and report. Do not write the field again in a loop.

## 7. Conflict detection

Question: does OOB conflict detection work through the API, and which checks does it report?

- Check: `conflict` exists. Two normal `SYN-PROBE` changes were given the same window, `2026-11-07 02:00:00`–`04:00:00`, and the same existing Linux server (`PS LinuxApp01`). The server was not modified. The probe called `POST /api/sn_chg_rest/change/{sys_id}/ci` and then `POST` and `GET /api/sn_chg_rest/change/{sys_id}/conflict`.
- Evidence: both CI attachments and both conflict calls succeeded. The first change produced `type=not_in_maintenance_window` ("Not In Maintenance Window") and no conflicting change. The second produced `type=ci_already_scheduled` ("CI Already Scheduled") against the first change, plus another maintenance-window row. No blackout row was produced. The choice list also includes parent and child CI schedule conflicts, parent and child blackout, parent and child maintenance window, and assigned-to schedule conflicts. Those were not raised by this pair of changes.
- Decision: use the OOB conflict API for CI schedule overlap and for the maintenance-window result. Keep a local overlap check only as a backstop if a later call cannot read `conflict`. Do not modify the sample CI.

## 8. Service-scoped blackouts

Question: can a blackout apply to one service, such as a Payments-only month-end freeze?

- Check: `cmn_schedule_blackout` extends the condition schedule (`cmn_schedule_condition`), which extends `cmn_schedule`. The condition-schedule fields include `applies_to`, `condition`, and `source`. There is no service reference field. `maintenance_schedule` on `cmdb_ci` references `cmn_schedule`. Sample rows include a class condition ("Class = Software") and a weekday blackout with an empty condition. The probe created one blackout named `SYN-PROBE service scope` with `applies_to=cmdb_ci_service`, condition `nameSTARTSWITHSYN-DOES-NOT-EXIST`, and `time_zone=America/New_York`, then deleted it.
- Evidence: the create succeeded. The read-back stored `applies_to=cmdb_ci_service`, condition "Name starts with SYN-DOES-NOT-EXIST", and `source=Service`. `time_zone` came back empty. The conflict probe did not report a blackout for that row, which was aimed at a name that does not exist. Storing `applies_to` does not show that the detector limits a freeze to one service.
- Decision: enforce the Payments-only month-end freeze, and any other single-service freeze, in policy code. Use `cmn_schedule` for windows that genuinely apply by CI class or by a maintenance schedule on the CI. Do not create an empty-condition blackout.

## 9. Historical inserts

Question: do closed state, close code, and the historical timestamps survive an insert?

- Check: Table API `POST /api/now/table/change_request` with `display_value=false`, type `normal`, state `3`, close code `successful`, close notes, and `opened_at`, `closed_at`, `work_start`, and `work_end` in June 2025. Then `PATCH` state `3` again. The record was deleted.
- Evidence: the insert stored state `-5` (New) and the Normal model. `close_code=successful`, the close notes, and all four timestamps survived exactly. A later `PATCH` of state `3` returned HTTP 403 from `Change Model: Check State Transition`, and the state stayed `-5`.
- Decision: load historical and open seeded changes, and the historical incidents, through an Import Set with business rules off. Changes the agents create later still use the Change API. Walking transitions was not used, because it would create approval rows the historical set must not have.
- Phase 1 proof, before the bulk load: a Closed change inserted through `POST /api/now/import/u_syn_chg_import` with `run_business_rules=false` kept state `3`, `active=false`, the approval value, the close code, and the close notes, and still received a `CHG` number. `sys_number` was not edited.
- The Import Set API reads date strings as `America/Los_Angeles`, including the daylight-saving offset, and stores UTC. Sending `2025-06-01 14:00:00` stored `2025-06-01 21:00:00`. Sending `2025-01-15 14:00:00` stored `2025-01-15 22:00:00`. `sysparm_input_display_value=false` did not stop the shift. The loader converts the desired UTC value to Pacific wall time before the import. Table API reads with `display_value=false` stay UTC, as item 12 describes.
- The Pacific fall-back hour is ambiguous. `2025-11-02 08:00:00` UTC and `2025-11-02 09:00:00` UTC both format as `2025-11-02 01:00:00` Pacific. This instance stores that wall time as `2025-11-02 09:00:00` UTC. Fixture timestamps in the earlier hour are moved forward one hour before they are written, so the value that comes back matches the fixture. The four `2025.11.0` release end times are the rows this affects.
- A JSON array posted to `/api/now/import/{staging}` inserts only the first object and returns a one-element `result`. Confirmed with two probe rows: HTTP 201, one target row, one result. The multi-row endpoint needs a Rest Insert Multiple configuration row. Seed does not create one. It posts one row at a time.
- Each staging table keeps one import set. This instance leaves that set in state `loading`. Writing `short_description` and `state` does not stick while the set is loading. Teardown finds the sets by `table_name`. The seed log line `import sets:` runs after the change and incident waves and before the affected-CI wave, so a full load prints `2` there and then creates the third set while posting `task_ci` rows. All three are recorded in the manifest.
- Affected CI rows (`task_ci`) cannot be inserted through the Table API. The before-insert business rule `Change Model: Read only CI (Insert)` on `task_ci` aborts the insert when `ChangeRequest.canModifyCI` is false, which it is for a modeled change in a read-only state. The matching delete rule aborts a direct `task_ci` delete, and `Prevent removal/update of primary CI` blocks deleting the primary affected CI of an open change. Deleting the change itself removes its affected CI rows. The rules were not modified. The 2,400 rows are loaded through the same Import Set path, with business rules off, into staging table `u_syn_taskci_import`.
- `incident.caused_by` does not exist. The change-caused-incident link is `incident.parent`. An emergency change's `parent` is the triggering incident. Those two uses of `parent` point in opposite directions and are not the same row.
- Standard templates cannot be inserted. The `std_change_record_producer` create ACL is active, `admin_overrides=false`, and its script is `answer=false`. The same is true of the delete ACL. Seed does not modify that ACL, does not grant roles to admin, and does not change the six out-of-box templates. The synthetic template count is 0. Freezes stay in policy code (item 8). `cmn_schedule.time_zone=America/New_York` is stored empty; `US/Eastern` is stored as `US/Eastern`. Seed writes `US/Eastern`. Policy windows stay `America/New_York`.
- ServiceNow `STARTSWITH` is case-insensitive and trims a trailing space. `nameSTARTSWITHSYN` matches the out-of-box CIs `Synaptics Pointing Device Driver` and `SynthCore` (`cmdb_ci_spkg`). Seed and teardown match `syn-` names plus the four service names in full, and they do not delete those two packages.

## 10. Releases

Question: does `rm_release` exist, and how would a change point at a release?

- Check: `GET /api/now/table/rm_release`, `sys_dictionary` references from `change_request` and `task` to `rm_release`, and the plugin queries in item 2.
- Evidence: the table read returned HTTP 400, `Invalid table rm_release`. The dictionary query returned 0 reference fields. The classic Release Management plugin is not installed. `sn_release_read` and `release_admin` roles exist anyway. ReleaseOps Backend is inactive. `rm_release.state` has no choices because the table is absent.
- Phase 1 looked up the plugin that would provide `rm_release` and did not activate anything. `v_plugin` has no row for `com.snc.release_management`, `com.snc.release_management_v2`, `com.snc.release_v2`, `com.glideapp.release`, `com.snc.planned_task`, `sn_dpr`, or `sn_dpr_workspace`. ServiceNow's Release Management v2 plugin (`com.snc.release_management_v2`) is hidden and is not present on this Australia instance. Digital Product Release replaced it and does not create `rm_release`. The rows that do exist are Read only roles for Release Management (`com.snc.release_management_read_roles`, active, role `sn_release_read` only), ReleaseOps Backend (`com.glide.releaseops`, inactive), and Global scope support for ReleaseOps (`com.glide.releaseopsglobal`, inactive). None of those creates `rm_release`. `sys_db_object` names starting with `rm_` returned 0. `GET rm_release` is still HTTP 400.
- Decision: do not activate a plugin. Each release is a normal change named `SYN RELEASE <service> <version>`. Member changes point at it through `parent`. The release change goes through assessment and authorization like any normal change, and that authorization is the go-live authorization. It carries the per-environment deployment tasks. Those tasks are the execution model for a later phase. Historical releases are not backfilled with them. The 20 release changes are outside the 1,500 historical changes.

## 11. Integration-user roles

Question: which roles does the integration user need?

- Check: a throwaway user `syn.probe.user`, Web service access only, not the real integration user. Direct grants were `sn_change_read` and `sn_change_write` only. The password was set with `sysparm_input_display_value=true` (item 13). The user was deleted, including its direct role grants (`inherited=false` only).
- Evidence: `sn_change_write` contains `sn_change_read`. `sn_change_read` contains `cmdb_read`, `sn_cmdb_user`, and several other read roles. It does not contain `itil`. With those two direct grants the user received HTTP 200 for `GET /api/now/ui/user/current`, `GET /api/now/table/change_request`, `POST /api/sn_chg_rest/change/normal`, and `GET /api/now/table/cmdb_ci`. `time_zone=UTC` was stored as empty. The real `SN_AGENT_USER` from `.env` was not created during Phase 0. `cm-agents doctor` reported `agent user missing: run seed` before Phase 1 seed.
- Phase 1 proof: `seed` created that user from `.env` as Web service access only. The only direct role is `sn_change_write`. A login as that user read `change_request` with HTTP 200. `time_zone` is still empty. After seed, `cm-agents doctor` prints `agent user: present`. No `itil` grant was required.
- Decision: Phase 1 starts from `sn_change_write` (and the contained `sn_change_read` / `cmdb_read` roles) on a Web service access only user. Do not grant `admin`. Do not grant `itil` unless a later call returns 403. Calls not yet made as this user include state transitions, the conflict API, `task_ci` create, change tasks, and approval reads. Add the smallest role that unblocks a 403, and record it.

## 12. Time zone and date format

Question: what do REST date-time values mean?

- Check: `glide.sys.date_format`, `glide.sys.time_format`, `glide.sys.default.tz`, the admin user's `time_zone`, and a Table API write of `start_date=2026-04-04 15:30:00` and `end_date=2026-04-04 16:30:00` read back with `display_value=false` and `display_value=true`.
- Evidence: date format `yyyy-MM-dd`, time format `HH:mm:ss`, default time zone empty, admin `time_zone` empty. `display_value=false` returned the two timestamps unchanged. `display_value=true` returned `2026-04-04 08:30:00` and `2026-04-04 09:30:00`, seven hours earlier. Change API create responses show the same split: `value` on the UTC clock and `display_value` on the seven-hour clock. On 2026-10-21 that offset is US Pacific Daylight Time.
- Decision: send and read date-times with `display_value=false` and treat those strings as UTC. Convert America/New_York policy windows to UTC before the API call. Do not write a `display_value=true` string back to the instance.

## 13. Basic authentication restriction

Question: is basic auth unrestricted, tracking, or enforcing, and can a Web service access only user sign in?

- Check: `GET /api/now/table/sys_properties?sysparm_query=nameLIKEbasic`, then the throwaway user in item 11.
- Evidence: `glide.authenticate.basic_auth.restriction.active` is `true`, `.enforce` is `true`, `.enforcement_date` is `2026-10-21 19:46:01`, `.allowed_roles` is `snc_basic_auth_api_access`, and `.allow_wsao` is `true`. `glide.basicauth.required.api` is `true`. A source-control credential property is set; its value is omitted here. The admin user can call the API and already holds `snc_basic_auth_api_access`.
- A Table API create that writes `user_password` as a normal field stores the submitted value (the read-back matched, and it was not a hash). Basic auth then returns HTTP 401, `User is not authenticated Required to provide Auth information`, with the Authorization header present. The user was active, not locked out, and did not need a password reset. Adding `snc_basic_auth_api_access` and setting `internal_integration_user` still returned 401. The only password business rule found was `Flush Change Password`, which runs after update and does not hash the password.
- The same create with `sysparm_input_display_value=true` stored a 92-character value that did not match the submitted password. `GET /api/now/ui/user/current` as that Web service access only user returned HTTP 200 without `snc_basic_auth_api_access`. The password itself is not recorded.
- Decision: Phase 1 creates the integration user with Web service access only checked and sets `user_password` with `sysparm_input_display_value=true`. A plain Table API password write will not log in. The basic-auth role stays on `admin` for seeding. It is not required on the integration user when Web service access only is set and the password was hashed by the platform.

## CMDB classes used later

Verified in `sys_db_object`. Services are `cmdb_ci_service`. Applications are `cmdb_ci_appl`. Linux and Windows servers extend Server. Database instances are `cmdb_ci_db_instance` (super class Application). Load balancers are `cmdb_ci_lb` (super class Server). Network devices are `cmdb_ci_netgear` (Network Gear, super class Hardware) and its children `cmdb_ci_ip_switch`, `cmdb_ci_ip_router`, and `cmdb_ci_ip_firewall`. `cmdb_ci_network` is Cloud Network under VMware vCenter Object and is the wrong class. Relationships use `cmdb_rel_ci`. Affected CIs use `task_ci`.

## Residue queries

The final `cm-agents discover` run printed 0 for each of these:

- `change_request`, short description starts with `SYN-PROBE` or `correlation_id=SYN-PROBE`
- `change_task`, by its own short description or by the parent or change request short description
- `task_ci` and `task_cmdb_ci_service`, by the task short description
- `sysapproval_approver` and `sysapproval_group`, by the parent change short description
- `conflict`, by either change's short description
- `sys_user`, `first_name=SYN-PROBE` or `user_name=syn.probe.user`
- `sys_user_has_role`, by that user name
- `cmn_schedule_blackout` and `cmn_schedule`, name starts with `SYN-PROBE`

## Decisions recorded in Phase 1

The four questions above are closed:

1. `rm_release` cannot be activated here. A release is a normal change. See item 10.
2. History loads through an Import Set with business rules off. See item 9.
3. Synthetic users are members of the existing Change Management, CAB Approval, and eCAB Approval groups. Authority follows item 5.
4. The agent's score is written to `change_request.risk` and `impact` with a plain field update. The Risk Calculator is not called. See item 6.

`cm-agents discover` stays the repeatable Phase 0 probe. It is a utility command, listed in the master prompt §7.3, not an agent command.
