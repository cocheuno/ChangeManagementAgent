# Grok Build Session Messages

These are the messages sent to Grok Build, in order, with the reason for each. The master prompt they refer to is [`grok-build-change-release-deployment-agents.md`](grok-build-change-release-deployment-agents.md). The environment they assume is set up in [`docs/setup/PDI_AND_WORKSTATION_SETUP.md`](../docs/setup/PDI_AND_WORKSTATION_SETUP.md).

**To reuse them in another project:**
- change the instance URL, the dates, and the property values to your own;
- change the prompt file name;
- keep the structure, which is: verified facts first, then answers, then a single phase, then stop.

---

## Message 1: Start the project (before Phase 0)

**When:** after Parts A–G of the setup guide pass.
**Why:** it points Grok Build at the master prompt and passes on facts you have already checked, so Phase 0 doesn't spend time rediscovering them. It also keeps secrets out of the conversation and keeps commits local until you review them.

```
Read prompts/grok-build-change-release-deployment-agents.md and follow it exactly, starting with §2 step 1.

Environment facts already verified by me:
- A .env with all required settings is in the repo root. Load it at runtime and never print, log or commit its values.
- PDI: https://dev181865.service-now.com is awake and the admin REST login works (HTTP 200).
- The basic authentication restriction is enforcing on this PDI (glide.authenticate.basic_auth.restriction.active = true, .enforce = true, enforcement_date 2026-10-21). I granted admin the snc_basic_auth_api_access role. Create the integration user as Web service access only, per §4.3 item 13.
- The xAI API key and XAI_MODEL work with chat completions.
- This machine is Windows 11 with PowerShell.

Work on the grok-build branch. Commit at the end of each phase, but don't push; I'll push after reviewing.
```

**What came back:** a 10-point restatement of the scope, a list of its assumptions, and two questions:
1. may `.env` be read with the standard library instead of python-dotenv;
2. is `SN_AGENT_USER` set to `syn.svc.change_agents`.

---

## Message 2: Answers before Phase 0

**Why:**
- The `.env` reader has to cope with the problems actually hit during setup: quotes around values, Notepad's hidden UTF-8 marker, and Windows line endings.
- The Phase 0 probe change must not send email, and it must leave nothing behind (the "clean up your own mess" rule).

```
Answers:
1. Standard-library .env parsing is fine. The parser must: strip a UTF-8 BOM, handle CRLF line endings, skip blank lines and # comments, trim whitespace, and strip one pair of matching surrounding quotes. If a required key is missing or empty, fail with a message naming the key, never the value. Add unit tests for each of these cases.
2. Confirmed: SN_AGENT_USER is syn.svc.change_agents. Always honor the value in .env.

Two additions for Phase 0:
- Check that outbound email is disabled before creating the SYN-PROBE change. If it is enabled, stop and ask me.
- When cleaning up SYN-PROBE, also delete any records it caused (approvals, change tasks, task_ci, conflict records), and include a query in the gate evidence showing 0 remain.

Proceed with Phase 0 only, commit locally, and stop.
```

**What came back:** the Phase 0 report, saved as [`docs/phase-reports/phase-0.md`](../docs/phase-reports/phase-0.md). Its four decisions are answered in message 3.

---

## Message 3: Start Phase 1 in a new session, with the Phase 0 decisions

**When:** on whichever PC continues the work, after the repository has moved to OneDrive (setup guide, D2) and the D2 checks pass.
**Why:**
- A new session has none of the earlier conversation, so it rebuilds context from the repository.
- It sets the OneDrive and virtual-environment rules.
- It accepts Phase 0, answers the four decisions, and asks for phase reports to be saved from now on.

**The reasons behind the decisions:**
- **Releases:** ServiceNow should stay the system of record for releases. Use a real `rm_release` if a plugin provides it. Otherwise fall back to a pattern that uses only built-in tables, without waiting for another round trip.
- **History load:** walking 1,525 changes through legal states takes 30–90 minutes and generates thousands of approval records. An Import Set with business rules off takes minutes, but nothing then fills in derived fields, so the loader must set them itself.
- **Approvers:** ServiceNow decides who approves. The agents mirror it rather than re-implement it. Adding synthetic users to the existing approval groups is data, not configuration, and teardown removes them.
- **Risk:** the agent's score is explainable and is backtested in Phase 2. The Risk Calculator overwrote a High/High test value with Low/Low, so it isn't used.

```
Context: this is a new Grok Build session, on a different PC from Phase 0. The repository now lives in OneDrive. Phase 0 is complete and accepted (commit e7b0c6a on grok-build). Before doing anything, read:
- prompts/grok-build-change-release-deployment-agents.md (the master prompt; follow it exactly)
- docs/phase-reports/phase-0.md, docs/DISCOVERY.md and docs/ASSUMPTIONS.md (the Phase 0 results)
- docs/setup/PDI_AND_WORKSTATION_SETUP.md (how this PDI and workstation were set up)

Environment on this PC:
- .env in the repo root has all required settings. Load it at runtime; never print, log or commit its values.
- The virtual environment lives outside the repository. Before every uv command, make sure UV_PROJECT_ENVIRONMENT is set; if it isn't, set it in that same command: $env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA 'venvs\ChangeManagementAgent'. Never create .venv inside the repository. Never hard-code absolute paths or Windows user names; the PCs have different user folders.
- Only one PC works on this repository at a time.
First run uv sync, uv run pytest and uv run cm-agents doctor, and show the output. If anything fails, stop.

Phase 0 review: accepted. Keep cm-agents discover as the repeatable Phase 0 probe, and list it in the docs as a utility command, not an agent command.

From now on, save each phase report as docs/phase-reports/phase-N.md and include it in that phase's commit.

Decisions for Phase 1:

1. Releases. Find the exact plugin (name and ID in v_plugin) that provides rm_release on this Australia instance, and whether it can be activated here.
   - If it can: report its name and ID, and stop before loading any release data. I will activate it myself. Then confirm rm_release exists, record its parent class and the linkage option (§4.3 item 10) in docs/DISCOVERY.md, and continue.
   - If it can't: don't wait for me. Use only out-of-box tables. Each release is a normal change named "SYN RELEASE <service> <version>", whose children (parent field) are the member changes. The release change goes through assessment and authorization like any normal change, and that authorization is the go-live authorization. It carries the per-environment deployment tasks. Record this in docs/DISCOVERY.md and docs/ASSUMPTIONS.md, and adjust the §8.2 release row to match.
   - Never activate a plugin yourself.

2. History load: use the Import Set approach, with business rules off. I approve creating the staging tables and transform maps it needs, on these conditions:
   - Load every seeded change (the 1,500 historical and the 25 open ones) and the historical incidents this way. Changes created later by the agents in scenarios still go through the Change API.
   - With business rules off, nothing sets derived fields, so set them from the fixtures: active=false on Closed and Canceled records; approval matching each record's history; opened_at, closed_at, work_start, work_end, close_code and close_notes. Check that every record still gets a number.
   - Record every staging table, transform map, field map and import set in the manifest. teardown removes them after the data rows.
   - Add to the gate: 5 sample changes and 3 sample incidents, covering each state, as returned by the Table API.

3. Approver groups: yes. seed may add synthetic users to the existing Change Management, CAB Approval and eCAB Approval groups. Add membership records only, and record them in the manifest. Don't change the groups themselves or any approval policy.
   - Authority follows ServiceNow, because ServiceNow is the system of record. Set the change_authority section of policy.yaml to mirror exactly what docs/DISCOVERY.md records, by change type and risk. Use the risk tier only for CAB agenda and CAB brief content.
   - Members of the synthetic DevOps groups are the Assess approvers for changes assigned to their groups.
   - If a scenario's expected authority (for example S02's change_manager) differs from what this PDI does, update that expectation to match the PDI, cite docs/DISCOVERY.md, and list it under Deviations. Don't weaken any other assertion.
   - If SYN Change Management and SYN CAB serve no purpose once the existing groups hold the approvers, don't create them. Update the §8.2 group count and list it under Deviations.

4. Risk: the agent's score is authoritative for change_request.risk and impact. Write it with a plain field update. Never call PATCH /api/sn_chg_rest/change/{sys_id}/risk or the Risk Calculator. In Phase 2, add an integration test showing that the agent-written risk survives every state transition up to Scheduled. If any transition recalculates it, stop and report.

Proceed with Phase 1 only, commit locally, and stop.
```

---

## After every phase: review checklist

Before replying to a phase report, check:

1. **The gate was run, not just described.** The report includes the actual command output for every gate item in §10 of the master prompt.
2. **No test was weakened.** Look at what changed under `tests/`:
   ```powershell
   git diff HEAD~1 --stat -- tests
   ```
   Deleted or loosened assertions need a reason you accept.
3. **Each deviation has a reason** you agree with. "The PDI behaves differently" must cite `docs/DISCOVERY.md`.
4. **New dependencies** each have a one-line justification.
5. **ServiceNow:** every record created is prefixed `SYN` and is in the manifest. No out-of-box configuration was changed.
6. **No secrets in the commit:**
   ```powershell
   git show --stat HEAD
   git log --all --oneline -- .env
   ```
   The second command must print nothing.
7. **The phase report is saved** in `docs/phase-reports/`.
8. **Push** once you've accepted it, then move `main` up to the accepted phase. Pushing `grok-build` to `main` succeeds only as a fast-forward, so it can't overwrite anything on `main`:
   ```powershell
   git push
   git push origin grok-build:main
   ```

## Reply template (same session)

```
Phase N review: accepted.
<answers to its questions and decisions, numbered to match its list>
Proceed with Phase N+1 only, commit locally, and stop.
```

To send work back instead:
```
Phase N review: not accepted yet.
<numbered list of what is wrong, with the gate item or rule from the master prompt that it breaks>
Fix these within Phase N, rerun the full gate, update docs/phase-reports/phase-N.md, commit locally, and stop.
```

## Resume template (new session, or after switching PCs)

```
Context: this is a new Grok Build session. Phases 0 to N are complete and accepted (latest commit <hash> on grok-build). Before doing anything, read:
- prompts/grok-build-change-release-deployment-agents.md (the master prompt; follow it exactly)
- docs/phase-reports/ (every phase report so far), docs/DISCOVERY.md and docs/ASSUMPTIONS.md
- docs/setup/PDI_AND_WORKSTATION_SETUP.md

Environment on this PC:
- .env in the repo root has all required settings. Load it at runtime; never print, log or commit its values.
- Before every uv command, make sure UV_PROJECT_ENVIRONMENT is set; if it isn't, set it in that same command: $env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA 'venvs\ChangeManagementAgent'. Never create .venv inside the repository, and never hard-code absolute paths or user names.
- Only one PC works on this repository at a time.
First run uv sync, uv run pytest and uv run cm-agents doctor, and show the output. If anything fails, stop.

<answers to the open decisions from the last phase report, if any>

Proceed with Phase N+1 only, save its report as docs/phase-reports/phase-<N+1>.md, commit locally, and stop.
```
