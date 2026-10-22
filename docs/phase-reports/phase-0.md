# Phase 0 Report: Scaffold and Discovery

Source: Grok Build's end-of-phase report, copied word for word from the session. A line that was repeated three times in the paste appears once here. The decisions it asks for are answered in message 3 of [`prompts/grok-build-session-messages.md`](../../prompts/grok-build-session-messages.md).

Status: **accepted**. Commit `e7b0c6a` on `grok-build`.

---

Phase 0 is committed locally on grok-build as e7b0c6a and was not pushed. Stopped here for your decision.

Outbound email is off (glide.email.smtp.active is false, and there is no active email account), so the SYN-PROBE writes were allowed. Every probe row was deleted. The final residue queries returned 0, including approvals, approval groups, change tasks, task_ci, and conflict rows.

## Gate

- `uv run pytest`: 51 passed.
- `uv run ruff check .`: clean.
- `uv run cm-agents doctor`: admin login ok. Build line is glide.buildname and glide.buildtag were not found; glide.war=glide-australia-02-11-2026__patch3-05-25-2026_06-12-2026_1106.zip. Plugin status came from v_plugin. Last line is agent user missing: run seed.
- `uv run cm-agents discover`: exit 0, and every residue count was 0.
- Staged diff scan: no secrets in the diff.

## What was recorded

docs/DISCOVERY.md answers all 13 checks. docs/ASSUMPTIONS.md records the choices already in force. The instance is Australia patch 3. Change Management core, standard change, collision detection, CAB Workbench, change models, and the risk calculator are active. There is no rm_release table and no plugin named Release Management. The Change API is an active scripted REST service, not a plugin.

A normal change cannot jump to Closed (HTTP 403 from the state-model rule). Dates, close code, and close notes survive an insert. State does not. The conflict API reports "CI Already Scheduled" and "Not In Maintenance Window". PATCH /api/sn_chg_rest/change/{sys_id}/risk overwrites a High/High write back to Low/Low. A plain field update does not.

A Web service access only user can log in when user_password is set with sysparm_input_display_value=true. A plain Table API password write stores the submitted value and basic auth returns 401. With only sn_change_write and sn_change_read (which contain cmdb_read, not itil), that user got HTTP 200 for the current-user API, change_request, the normal Change API, and cmdb_ci. The real integration user was not created.

## Deviation

cm-agents discover is not in the command list in the master prompt. It is the repeatable Phase 0 probe. It is not an agent command.

## Decisions needed before Phase 1

1. Activate classic Release Management so rm_release exists, or leave releases out of ServiceNow for now?
2. Load the 1,500 historical changes by walking legal state transitions (roughly 30–90 minutes, and it would create approvals), or by an Import Set with business rules off (a few minutes, and it needs a yes because it creates a staging table)?
3. May seed add synthetic users to the existing Change Management, CAB Approval, and eCAB Approval groups? Should authority follow those groups, or the prompt's risk-tier table? On this instance, Assess follows the assignment group and emergency Authorize follows CAB Approval.
4. When the agent's risk score and the Risk Calculator disagree, which value should remain on change_request.risk?
