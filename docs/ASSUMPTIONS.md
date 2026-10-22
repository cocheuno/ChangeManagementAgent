# Assumptions

These are the choices Phase 0 proceeded with. Items that still need a decision are listed at the end and in `docs/DISCOVERY.md`. They were not applied on the instance.

## Settings

- The repo-root `.env` is parsed with the standard library. The parser strips a UTF-8 BOM, accepts CRLF, skips blank lines and `#` comments, trims whitespace, and strips one matching pair of surrounding quotes. A missing or empty required key fails with the key name and never includes the value.
- `SN_AGENT_USER` is whatever `.env` contains. The confirmed integration-user name is `syn.svc.change_agents`. Phase 0 does not create that user. `cm-agents doctor` says `agent user missing: run seed` until Phase 1 does.
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
- Historical changes, once a load method is chosen, do not get tasks or approvals.
- `cm-agents discover` is not in the command list in the master prompt. It is the repeatable Phase 0 probe. It is not an agent command.

## Open

1. Whether to activate classic Release Management.
2. Whether historical Closed state is loaded by walking transitions or by an Import Set with business rules off.
3. Whether synthetic users may be added to Change Management, CAB Approval, and eCAB Approval, and whether authority follows those groups or the prompt's risk tiers.
4. Whether `change_request.risk` is owned by the Risk Calculator or by the agent's score. The calculate endpoint overwrites a Table API write. An ordinary later update does not.
