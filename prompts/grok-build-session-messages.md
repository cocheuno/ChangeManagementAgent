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

**What came back:** the Phase 1 report, `docs/phase-reports/phase-1.md` (in Grok Build's Phase 1 commit). Its gate evidence was thorough: identical dry-run hashes; fixture and PDI counts equal; a second seed creating 0 records; teardown back to the pre-seed baseline; a clean reseed in 11.5 minutes; 74 tests passing. Review still found four problems and one gap, answered in message 4.

---

## Message 4: Phase 1 review, not accepted yet

**When:** in the same Grok Build session, after reading the Phase 1 report.

**Why:**
- **Future dates.** Sample records were opened on 2026-10-23 and 2026-10-24, but were loaded on 2026-10-22. Records opened in the future break lead-time metrics and the "no lookahead" rule.
- **The change that caused an incident** (`incident.caused_by`, which the report says doesn't exist). An out-of-box incident usually has a "Caused by Change" field. Repurposing `incident.parent` instead would mislead everything built on this data later, including the student's Problem Management work. Grok also changed §8.4 of the master prompt without approval.
- **Normal change authority.** The report says normal changes only get assignment-group approval, at every risk tier. Normal changes usually also go to CAB at Authorize, so this needs evidence before the scenarios are changed to match.
- **MTTR depends on `resolved_at`.** The sample records didn't show it.
- **Standard change templates were 0 of 6.** ServiceNow's own route for creating templates (an approved proposal) hadn't been tried.

```
Phase 1 review: not accepted yet. The gate evidence is thorough, and the teardown baseline check and the Synaptics/SynthCore catch are exactly right. Fix these within Phase 1:

1. Future dates. The samples show opened_at in the future: SYN-OPEN-16, SYN-OPEN-21 and SYN-OPEN-01 opened 2026-10-23 16:00:00, and SYN-INC-0159 opened 2026-10-24 16:00:00, but they were loaded on 2026-10-22. Nothing may be opened in the future.
   - Report the anchor ("as of") date the generator uses and how it is chosen.
   - Required: every historical date and every opened_at is before the load time. Only the planned dates of open changes may be in the future (the next 6 weeks).
   - If byte-identical fixtures need a fixed anchor, make the anchor an explicit input (default: the load date, in UTC), record it in ground_truth.json and the manifest, and compare dry-run hashes for the same anchor.
   - Add a unit test that no opened_at, closed_at, resolved_at or work_end is later than the anchor.

2. incident.caused_by. An out-of-box incident usually has a "Caused by Change" reference field named caused_by, so "does not exist" needs evidence.
   - Show the sys_dictionary results for name=incident^element=caused_by and for name=task^element=caused_by, and list every incident field whose reference table is change_request.
   - Until I decide, don't use incident.parent for this link. parent means something else in the UI, and it would mislead the Problem Management work that will be built on this data.
   - If caused_by really doesn't exist, list the options (for example incident.rfc, a custom reference field, or a task relationship) and stop for my decision.
   - Revert your change to §8.4 of the master prompt until then.

3. Normal change authority. The report says normal changes only get assignment-group approval at Assess, for every risk tier. Out of the box, normal changes usually also go to CAB Approval at Authorize.
   - Walk two probe normal changes, one at risk Low and one at risk High, from New to Scheduled. Approve each step as the admin test helper.
   - Show every approval record generated in each state (group, state, sys_created_on).
   - Set change_authority in policy.yaml and the S02, S03 and S05 expectations from that evidence.
   - Delete the probes and show that 0 residue remains.

4. Resolved and closed incidents. MTTR needs resolved_at. Show the number of SYN incidents in Resolved or Closed with resolved_at empty (must be 0), and with resolved_at earlier than opened_at (must be 0).

5. Standard change templates. Before accepting 0 of 6, try ServiceNow's own route for new templates: a Standard Change Template Proposal that creates the template once approved.
   - If it works here with admin as the approver, and teardown can remove what it creates, create the 6 SYN templates that way and record them in the manifest.
   - If it doesn't, record why, and name the existing template that S01 will use instead.

Accepted as they are: 6 groups, a release as a normal change, freezes in policy code, the CI query rule, the schedule time zone, import sets left in the loading state, the integration user with sn_change_write only, and the new dependencies.

Noted for Phase 2, no action now: Table API inserts into task_ci are blocked by "Change Model: Read only CI (Insert)". Verify that the Intake agent can add affected CIs to a new change through the Change API before relying on it.

Rerun the full gate, update docs/phase-reports/phase-1.md, commit locally, and stop.
```

**What came back:** Phase 1 committed as `26e3523`, with these results:
- **Anchor date:** midnight UTC on the load date, recorded in the data files. Every `opened_at` is before it.
- **Approvals:** normal changes get **two**, Change Management at Assess and CAB Approval at Authorize, at both Low and High risk. S02, S03 and S05 were corrected to match.
- **MTTR data:** of 158 resolved or closed incidents, 0 lack `resolved_at`, and 0 were resolved before they opened.
- **Standard change templates:** all 6 were created through Standard Change Template Proposals, and teardown removes them.
- **The "Caused by Change" link:** no such field exists on the incident table. Grok stopped for a decision and reverted its edit to the master prompt.
- **One new risk:** a OneDrive lock on `manifest.json` interrupted a load. It recovered.

A check in the browser confirmed that `caused_by`, `rfc` and `problem_id` don't exist on incidents, although Problem Management is active. The instructor then created `incident.u_caused_by` by hand (setup guide, Part B8).

---

## Message 5: The "Caused by Change" decision, and safe manifest writes

**When:** in the same session, after creating the field (setup guide, Part B8).

**Why:**
- ServiceNow must hold the link between an incident and the change that caused it. The change failure rate metric and scenario S07 both depend on it.
- The mapping to `u_caused_by` is recorded in `docs/ASSUMPTIONS.md` rather than in the master prompt, which stays reusable.
- Writing `manifest.json` atomically means a OneDrive lock can't leave it half-written.

```
Decision on incident.caused_by: I created a reference field on incident myself: column name u_caused_by, label "Caused by Change", reference change_request. Verify it in sys_dictionary and record it in docs/DISCOVERY.md item 9 as a human-made, approved customization.
- Load the 74 caused-by links into incident.u_caused_by in seed, and add it to the field check and the gate counts (loaded=74, pdi=74).
- teardown clears the values along with the SYN incidents and must not try to delete the field. Record that the field remains after teardown.
- Use u_caused_by wherever the master prompt says caused_by (§6.6, §8.4, S07). Record that mapping in docs/ASSUMPTIONS.md; don't edit the master prompt.
- Also record in docs/DISCOVERY.md whether incident.problem_id and incident.rfc exist on this instance, and whether the Problem Management plugin is active. Don't change anything for them.

OneDrive lock: write manifest.json atomically (write a temporary file in the same folder, then replace the original) and retry briefly on a sharing violation. Add a unit test for it.

Then rerun the full gate, update docs/phase-reports/phase-1.md, commit locally, and stop.
```

**What came back:** Phase 1 committed as `bc26fc4`.
- **The links:** all 74 are loaded (`incident u_caused_by fixture=74 loaded=74 pdi=74 parent_used=0`), and teardown leaves the field in place.
- **The mapping** is in `docs/ASSUMPTIONS.md`, and the master prompt was not edited. `incident.problem_id` and `incident.rfc` are confirmed absent.
- **The manifest** is now written atomically, with a retry if the file is locked.
- **Tests:** 79 passed.
- **The final load:** 640 seconds, creating 5,095 records.
- **Baseline drift:** a daily ServiceNow job kept adding non-SYN `task_ci` rows (281, then 313), which made one teardown check fail. Message 6 fixes that check.

**Phase 1 accepted.**

---

## Message 6: Start Phase 2 (Change Enablement agents)

**When:** in a new session, after Phase 1 is published (`git push`, then `git push origin grok-build:main`).

**Why each addition to the master prompt's Phase 2 gate:**
1. **Approvals:** this PDI has two approval steps for normal changes, so the S02 expectation of "exactly one authorization interrupt" has to be defined again.
2. **Risk:** decision 4 from message 3 deferred the test that agent-written risk survives state transitions to this phase.
3. **Affected CIs:** Phase 1 found that Table API inserts into `task_ci` are blocked, so the Change API route must be proven first.
4. **Roles:** the integration user has one role, and Phase 2 may need more. Each must be justified, and admin and `itil` need your approval.
5. **Model:** the plan-quality agreement test is where the model choice is checked. Changing the model changes cost, so that decision is yours.
6. **Teardown check:** comparing table totals fails whenever ServiceNow's own daily job adds rows.
7. **Cost:** Phase 2 is the first phase that calls the LLM in volume.

```
Context: this is a new Grok Build session. Phases 0 and 1 are complete and accepted (Phase 1 is bc26fc4 on grok-build, followed by my merge commits). Before doing anything, read:
- prompts/grok-build-change-release-deployment-agents.md (the master prompt; follow it exactly)
- docs/phase-reports/ (phase-0.md and phase-1.md), docs/DISCOVERY.md and docs/ASSUMPTIONS.md
- docs/setup/PDI_AND_WORKSTATION_SETUP.md

Environment on this PC:
- .env in the repo root has all required settings. Load it at runtime; never print, log or commit its values.
- Before every uv command, make sure UV_PROJECT_ENVIRONMENT is set; if it isn't, set it in that same command: $env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA 'venvs\ChangeManagementAgent'. Never create .venv inside the repository, and never hard-code absolute paths or user names.
- Only one PC works on this repository at a time.
First run uv sync, uv run pytest and uv run cm-agents doctor, and show the output. If anything fails, stop.

Phase 2 is Change Enablement (master prompt §10, Phase 2). In addition to its gate:

1. Approvals. On this PDI, a normal change gets Change Management approval at Assess and CAB Approval at Authorize, at every risk tier. An emergency change gets CAB Approval at Authorize (docs/DISCOVERY.md item 5).
   - Decide whether the authorization interrupt fires once per approval step or once for the whole authorization, and explain why.
   - Update the S02 expectation ("exactly one authorization interrupt") to match. Cite docs/DISCOVERY.md and list the change under Deviations.
   - The test helper approves every step. Agents still never write approvals.

2. Risk survives state transitions. Write change_request.risk and impact with a plain field update. Add the integration test from decision 4: the agent-written risk and impact survive every state transition up to Scheduled. Never call PATCH /api/sn_chg_rest/change/{sys_id}/risk or the Risk Calculator. If a transition recalculates risk, stop and report.

3. Affected CIs. Table API inserts into task_ci are blocked. Before building on it, show that Intake can add affected CIs to a new change in state New through the Change API, running as the integration user.

4. Roles. If the agents need roles beyond sn_change_write, add the minimum to seed, and list each role with the operation that needs it. Never grant admin or itil without asking me.

5. Plan-quality agreement. If the LLM checklist agrees with the fixture labels on fewer than 90% of the 200 judgments, stop and report the results per checklist item. Don't change XAI_MODEL yourself.

6. Teardown baseline. A daily ServiceNow job adds non-SYN task_ci rows (cert_follow_on_task), so comparing totals fails whenever it runs between seed and teardown. Change the check to compare the non-SYN rows created before the seed time (sys_created_on) with the baseline. Report rows created after the seed separately, without failing. Add a unit test.

7. Cost. Report the total number of LLM calls and tokens for the gate run, taken from the audit log.

Save the report as docs/phase-reports/phase-2.md, commit locally, and stop.
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
