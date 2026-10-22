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
- Affected CI rows (`task_ci`) use that same Import Set path. The Table API insert is aborted by business rule `Change Model: Read only CI (Insert)`. See `docs/DISCOVERY.md` item 9.
- `incident.caused_by` does not exist. Metrics and scenarios that say `caused_by` mean `incident.parent`.
- `change_authority` in `config/policy.yaml` matches `docs/DISCOVERY.md` item 5. The risk tier does not select the approver.
- `change_request.risk` and `impact` are the agent's score, written with a plain field update. Phase 2 tests that the score survives state transitions up to Scheduled.
- Standard change templates are not seeded. The create ACL on `std_change_record_producer` returns `answer=false` and does not let admin override it. Freezes stay in policy code.
- Schedule records use `time_zone=US/Eastern` because `America/New_York` is stored empty. Policy math still uses `America/New_York`.
- S02 expects authority `assignment_group`, not `change_manager`. S03 expects `assignment_group`, not CAB. S05 expects `cab_approval`, not ECAB. The other assertions in those scenarios are unchanged.

## Open

None from Phase 0. Phase 2 still has to prove that an agent-written risk value survives each state transition up to Scheduled.
