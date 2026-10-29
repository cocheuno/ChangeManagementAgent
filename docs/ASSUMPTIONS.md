# Assumptions

These are the choices the build proceeds with. Phase 0 left four decisions open. Phase 1 closed them and applied them on the instance. What is still open is at the end.

## Settings

- The repo-root `.env` is parsed with the standard library. The parser strips a UTF-8 BOM, accepts CRLF, skips blank lines and `#` comments, trims whitespace, and strips one matching pair of surrounding quotes. A missing or empty required key fails with the key name and never includes the value.
- `SN_AGENT_USER` is whatever `.env` contains. The confirmed integration-user name is `syn.svc.change_agents`. Phase 0 does not create that user. Phase 1 `seed` does. After that, `cm-agents doctor` prints `agent user: present`.
- The instance URL must match `^https://dev\d+\.service-now\.com$` for its full length. The client will not run against any other host. The URL and the passwords are not written to logs, docs, or git.

## Instance changes

- Phase 0 did not activate plugins, add tables or fields, edit change models, edit standard templates, edit approval definitions, or modify an existing CI.
- Outbound email was off (`glide.email.smtp.active=false`, no active email account). Discovery refuses to create a `SYN-PROBE` change if that stops being true.
- Every `SYN-PROBE` row the probe created was deleted, including approvals, approval groups, change tasks, `task_ci`, service CI links, and conflict rows. The residue queries in `docs/DISCOVERY.md` returned 0.

## Behavior later phases should keep

- Rule-based decisions stay in code. The model is for language and judgment only.
- Date-times are written and read with `display_value=false` and treated as UTC. America/New_York is for policy windows, converted to UTC before the call.
- The integration-user password must be set with `sysparm_input_display_value=true`. On this instance a plain Table API write stores a value basic auth will not accept.
- Phase 1 starts the integration user as Web service access only, with `sn_change_write` and its contained roles (`sn_change_read`, `cmdb_read`, and the other contained read roles). It does not receive `admin`. `itil` is added only if a call returns 403.
- Agents do not write approval rows. A test helper that approves a change belongs under `tests/` and uses the admin credentials. Agent code does not import it.
- Historical changes and historical releases do not get tasks or approvals. Per-environment deployment tasks are created when a release runs in a later phase.
- `cm-agents discover` is a utility command in the master prompt §7.3. It is the repeatable Phase 0 probe. It is not an agent command.
- There is no `rm_release` table and the plugin that would create it is not on this instance. A release is a normal change named `SYN RELEASE <service> <version>`. Member changes use `parent`. See `docs/DISCOVERY.md` item 10.
- Seeded changes and incidents load through the Import Set API, one row at a time, with business rules off. The loader converts UTC date-times to `America/Los_Angeles` wall time before that call. A timestamp in the repeated Pacific fall-back hour is stored one hour later, so the fixture uses that later instant. Later agent-created changes use the Change API. Each staging table's import set stays in state `loading`. Teardown deletes those sets by staging table name.
- Teardown deletes membership rows only in the six SYN groups and in Change Management, CAB Approval, and eCAB Approval. It then deletes the synthetic users, including the integration user. It does not chase the platform membership `Conditional Script Writer`, which the instance adds back after a delete.
- Affected CI rows (`task_ci`) for the seeded history use that same Import Set path. The Table API insert is aborted by business rule `Change Model: Read only CI (Insert)`. See `docs/DISCOVERY.md` item 9.
- Intake adds affected CIs to a change that is still New with `POST /api/sn_chg_rest/change/{sys_id}/ci`. The body is `cmdb_ci_sys_ids` and `association_type=affected`, and the worker must finish. A body of `cmdb_ci` alone is HTTP 400 for the integration user. The Table API insert into `task_ci` stays blocked.
- Where the master prompt says `caused_by` (§6.6, §8.4, and S07), the instance field is `incident.u_caused_by`. The fixture key stays `caused_by`. Seed writes that reference. `incident.parent` is not the link. Emergency changes still use `change.parent` for the triggering incident. Release members still use `change.parent` for the release change. See `docs/DISCOVERY.md` item 9.
- The generator anchor defaults to midnight UTC on the UTC load date. `--anchor` pins it. The same seed and the same anchor are byte-identical. The anchor is stored on the fixture, in `ground_truth.json`, and in the manifest. Every `opened_at` is before the anchor. Only open-change planned dates may fall in the next 6 weeks.
- `change_authority` in `config/policy.yaml` matches `docs/DISCOVERY.md` item 5. A normal change, at every risk tier, is approved by its assignment group at Assess and by CAB Approval at Authorize. An emergency change is approved by CAB Approval at Authorize. The risk tier does not select the approver.
- `change_request.risk` and `impact` are the agent's score, written with a plain Table API field update. The agent does not call `PATCH /api/sn_chg_rest/change/{sys_id}/risk` and does not call the Risk Calculator. Phase 2 wrote risk `2` and impact `1` on a normal change and read that same pair back after the write, after Assess, after Authorize, and after Scheduled.
- The six `SYN Standard` templates are published through a Standard Change Template Proposal. S01 uses `SYN Standard rotate TLS certificate`. The create ACL on `std_change_record_producer` is unchanged. Freezes stay in policy code.
- Schedule records use `time_zone=US/Eastern` because `America/New_York` is stored empty. Policy math still uses `America/New_York`.
- The authorization interrupt fires once per approval step. At New a normal change has no approval rows. Moving it to Assess creates only the assignment-group approval. CAB Approval rows are created after that group approves and the change reaches Authorize. One interrupt for the whole authorization would be waiting on rows that do not exist yet. See `docs/DISCOVERY.md` item 5. The master prompt S02 line already says an authorization interrupt at each of those steps and one `go_no_go`, so that sentence was not edited. S03 expects the same two steps, and the human rejects at CAB Approval. S05 expects `cab_approval` at Authorize and no go/no-go. Standard stays pre-authorized. The Phase 2 durability check exits at the first authorization interrupt, the test helper approves every step, and one resume in a new process reaches `go_no_go`.
- Phase 2 did not add a role. The integration user's only direct role is still `sn_change_write`. With that role the agent created normal changes, moved New to Assess, wrote dates, risk, impact, and work notes, associated affected CIs, read conflicts and approvals, and inserted `task_cmdb_ci_service`. A query of `sys_journal_field` by that user returns no rows. Admin can read the notes the agent wrote. `itil` and `admin` were not granted.
- Teardown compares each baseline table's rows with `sys_created_on` before the seed time to the stored baseline. Rows created after the seed, including the daily `cert_follow_on_task` job, are printed and do not fail the check. The Phase 1 manifest left on this instance has no `seeded_at`. Teardown of that seed still compares totals and prints that `seeded_at` is missing. The next new seed records `seeded_at`. This seed was not torn down and was not re-seeded.

## Open

Phase 3 has not started. Deployment, the simulator, review, close, and PIR are not built. When §6.6 creates an incident for a failed deployment, it writes `incident.u_caused_by`.

The integration user can write work notes and cannot read them back: `sys_journal_field` returns no rows for that user, and the call is not a 403. Idempotent note checks therefore see an empty journal. No role smaller than `itil` was identified for that read, and `itil` was not added.
