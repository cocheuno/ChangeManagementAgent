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

**What came back:** Phase 2 committed as `ad52f92`. The gate passed.
- **Backtest:** failure rates of 0.3% for Low (299 changes), 5.2% for Moderate (833) and 12.0% for High (368). High is 40 times Low, far above the required 3 times.
- **Plan-quality agreement:** 200 of 200.
- **Scenarios:** S04 and S08 pass, and the S02 durability test passes.
- **Risk:** the agent-written risk and impact survived every state up to Scheduled. The Risk Calculator was never called.
- **Affected CIs:** the integration user attached an affected CI to a new change through the Change API.
- **Approvals:** the authorization interrupt fires once per approval step. The CAB Approval rows only exist once the change reaches Authorize, so a single interrupt would wait for records that don't exist yet.
- **Cost:** 60 LLM calls and 127,421 tokens on `grok-4.7`.
- **Roles:** none added. The integration user can write work notes but can't read them, so `itil` stayed open.
- **Leftovers:** five scenario changes remain on the instance.

**Accepted,** once the report showed that item 6 (the teardown baseline) was done and tested.

**Two lessons for reuse:**
- **Perfect agreement on synthetic text** (200 of 200) shows the checklist works on text built to match its labels, not that it handles messy real-world plans.
- **Records left by scenarios** must be identifiable, or they distort the metrics checked in Phase 5.

---

## Message 7: Start Phase 3 (Deployment and Review agents for standalone changes)

**When:** in a new session, after Phase 2 is published.

**Why each addition to the master prompt's Phase 3 gate:**
1. **Roles:** the Review agent needs approval comments (S03's CAB rejection reason) and work notes (PIR timelines). The Deployment agent creates incidents (S07). The integration user can do none of these with `sn_change_write` alone.
2. **Scenario records:** changes created by scenarios would distort the Phase 5 metrics, which must equal the ground truth exactly.
3. **Maintenance windows:** ServiceNow reported "not in maintenance window" for a time that policy treats as inside the tier-1 window. Phase 3 deploys inside windows, so the rule that governs must be clear.
4. **Cost:** tracked phase by phase.

```
Context: this is a new Grok Build session. Phases 0, 1 and 2 are complete and accepted (Phase 2 is ad52f92 on grok-build, followed by my merge commits). Before doing anything, read:
- prompts/grok-build-change-release-deployment-agents.md (the master prompt; follow it exactly)
- docs/phase-reports/ (phase-0.md to phase-2.md), docs/DISCOVERY.md and docs/ASSUMPTIONS.md
- docs/setup/PDI_AND_WORKSTATION_SETUP.md

Environment on this PC:
- .env in the repo root has all required settings. Load it at runtime; never print, log or commit its values.
- Before every uv command, make sure UV_PROJECT_ENVIRONMENT is set; if it isn't, set it in that same command: $env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA 'venvs\ChangeManagementAgent'. Never create .venv inside the repository, and never hard-code absolute paths or user names.
- Only one PC works on this repository at a time.
First run uv sync, uv run pytest and uv run cm-agents doctor, and show the output. If anything fails, stop.

Phase 3 is Deployment and Review for standalone changes (master prompt §10, Phase 3). In addition to its gate:

1. Roles. Before building the Review and Deployment agents, find the narrowest set of roles that lets the integration user:
   (a) read work notes and approval comments on SYN changes and their approvals;
   (b) create and update incidents, including u_caused_by;
   (c) create and update change tasks.
   Test candidate roles one at a time, and show the result of each operation for each candidate. Add the minimum to seed, and list each role with the operation that needs it. If nothing narrower than itil works, itil is approved for this PDI. Never grant admin.

2. Scenario records. State how records created by scenarios are marked (for example correlation_id or a short_description prefix), and make sure:
   (a) teardown removes them;
   (b) the Phase 5 metrics can never count them.
   Remove the five scenario changes left from Phase 2 that way, and show 0 remain.

3. Maintenance windows. In S04, ServiceNow returned not_in_maintenance_window for 2026-11-08 03:00 to 05:00 UTC (Saturday 22:00 to Sunday 00:00 ET). Explain why: which schedule the shared cluster CI uses, and its time zone. Record in docs/DISCOVERY.md which check governs a deployment window, policy code or ServiceNow's, and make the Deployment agent's precondition follow it.

4. Cost. Report the total number of LLM calls and tokens for the gate run, taken from the audit log.

Save the report as docs/phase-reports/phase-3.md, commit locally, and stop.
```

**What came back:** Phase 3 committed as `d8011ca`. The five live scenarios passed (S01, S02, S03, S05, S07), and S07 rolled back after its canary failed, with no later PROD deployment.
- **Roles:** `sn_change_write`, `audit_viewer` (to read journal entries; `itil` couldn't) and `sn_incident_write` (so urgency can produce a P1).
- **Scenario records:** marked by a `correlation_id` prefix and excluded from metrics. The Phase 2 leftovers were removed.
- **Cost:** 16 LLM calls and 50,611 tokens.
- **Found during review:**
  - the unit suite grew only from 93 to 95, although the gate requires simulator tests for each strategy;
  - the seeded maintenance spans are evaluated as UTC in ServiceNow, so its tier-1 window sits five hours early;
  - the evidence for S07's incident, S03's rejection reason and the PIR files wasn't shown.

---

## Message 8: Phase 3 review, not accepted yet

**When:** in the same session, after reading the Phase 3 report.

**Why:**
- **Tests:** the deterministic core (simulator strategies, deployment preconditions, close-code and PIR rules) needs tests that run without ServiceNow or the LLM.
- **Maintenance windows:** ServiceNow is the system of record, so its maintenance window must match policy. Otherwise the change schedule and conflict results shown in ServiceNow are wrong for anyone reading them there.
- **Evidence:** the scenarios' key outcomes must be shown, not assumed.

```
Phase 3 review: not accepted yet. The five scenarios, the role tests, the scenario-record rule and the cleanup are good. Fix these within Phase 3:

1. Unit tests. The master prompt's Phase 3 gate requires simulator unit tests for each strategy, but the unit suite only grew from 93 to 95. Add deterministic unit tests, with no network and no LLM, for:
   - each strategy (canary, blue/green, rolling, big bang): success, an injected failure, and rollback;
   - the Deployment agent's preconditions, including no automatic retry after a PROD failure;
   - the Review agent's close-code rules and its PIR-required rule.
   List the test names in the report.

2. Maintenance schedules in ServiceNow. The seeded spans are evaluated as UTC, so ServiceNow's tier-1 window is Saturday 17:00 to 23:00 Eastern instead of 22:00 to 04:00. The policy check is right, but the record is wrong, and ServiceNow is the system of record: anyone looking at the change schedule or conflict results there sees the wrong window.
   - Fix seed so that both schedules match policy in Eastern time, including across daylight saving time.
   - Prove it with ServiceNow's conflict check on four probe changes on syn-shared-sqlclu-prd-01: Saturday 22:00 Eastern and Saturday 17:00 Eastern, each on a date in November and on a date in June. Only the 22:00 probes may be free of not_in_maintenance_window.
   - Update the existing spans in place if seed can do that idempotently; otherwise reseed. Delete the probes and show that 0 residue remains.
   - Keep policy code as the governing check. Record the cause and the fix in docs/DISCOVERY.md.

3. Evidence missing from your summary. Show from the gate output:
   (a) S07's incident, with u_caused_by pointing to the S07 change, and its priority;
   (b) S03's CAB rejection reason, as read from the approval comments and recorded by Review;
   (c) the PIR files for S05 and S07, with their required sections present.

Accepted as they are:
- The roles sn_change_write, audit_viewer and sn_incident_write. Record in docs/ASSUMPTIONS.md that a production design would read journal entries through the record's work_notes and comments fields, rather than through a cross-table audit role.
- S03 returning to New after rejection. That is ServiceNow's standard behavior: the change goes back to the requester for rework.
- The scenario-record rule, and ServiceNow's "Blackout Wednesdays" schedule moving S02. Record that this blackout schedule comes from ServiceNow's demo data.

Rerun the unit tests and the live gate, update docs/phase-reports/phase-3.md, commit locally, and stop.
```

**What came back:** the fixes were committed as `60560ea`.
- **Tests:** 125 unit tests now pass. The new ones include 12 strategy tests, 9 deployment-precondition tests (among them `test_a_prod_failure_is_not_retried`) and 6 Review tests.
- **The live gate:** 5 passed. Cost: 16 LLM calls and 50,000 tokens.
- **Evidence:**
  - S07's incident `INC0011001` has `u_caused_by` pointing to the S07 change, at priority 3 (Fulfillment is tier 2);
  - S03's rejection reason, "backout is not acceptable", was read from the approval comment and recorded by Review;
  - both PIR files have every required section.

**The diagnosis in message 8 was wrong.** The spans already held the Eastern wall-clock times. The real causes, which Grok found:
- the property `change.conflict.ci_maint_sched` was `false`, so CI maintenance schedules were ignored;
- the demo schedule "Global Infrastructure" applied to every CI.

Grok's fix set the property to `true` and limited the demo schedule to non-synthetic CIs. Four probes proved the result: ServiceNow now clears Saturday 22:00 Eastern and flags 17:00, in both November and June.

**One problem:** Grok changed those two built-in settings without asking first, which breaks Rule 3 of the master prompt. The changes were sound and reversible, so they were approved after the fact in message 9, on the condition that they're recorded and restored (setup guide, Part B9).

**Phase 3 accepted.**

**Lesson for reuse:** state the observed symptom and the required outcome, not your own guess at the cause. Grok's investigation found the real cause because the outcome it had to prove (four probes, two seasons) didn't depend on the guess being right.

---

## Message 9: Start Phase 4 (Release Management)

**When:** in a new session, after Phase 3 is published.

**Why each instruction:**
- **Item 0:** approves the two built-in settings after the fact, makes them reversible, and restates the rule to ask first.
- **Items 1–3:** fit the master prompt's release flow to the "release as a normal change" decision from Phase 1. The release change is authorized like any normal change, and that authorization is the go-live authorization.
- **Item 4:** confirms that the release history supports the on-time metric before Phase 5 depends on it.

```
Context: this is a new Grok Build session. Phases 0 to 3 are complete and accepted (Phase 3 is 60560ea on grok-build, followed by my merge commits). Before doing anything, read:
- prompts/grok-build-change-release-deployment-agents.md (the master prompt; follow it exactly)
- docs/phase-reports/ (phase-0.md to phase-3.md), docs/DISCOVERY.md and docs/ASSUMPTIONS.md
- docs/setup/PDI_AND_WORKSTATION_SETUP.md

Environment on this PC:
- .env in the repo root has all required settings. Load it at runtime; never print, log or commit its values.
- Before every uv command, make sure UV_PROJECT_ENVIRONMENT is set; if it isn't, set it in that same command: $env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA 'venvs\ChangeManagementAgent'. Never create .venv inside the repository, and never hard-code absolute paths or user names.
- Only one PC works on this repository at a time.
First run uv sync, uv run pytest and uv run cm-agents doctor, and show the output. If anything fails, stop.

0. Built-in configuration (follow-up from Phase 3). In Phase 3, seed set change.conflict.ci_maint_sched to true and changed the condition on the demo schedule Global Infrastructure. Both are changes to out-of-box configuration, which Rule 3 of the master prompt says need my approval first. I approve both, on these conditions:
   - seed records each original value in the manifest before changing it;
   - teardown restores the original values, after the data rows;
   - add unit tests for the record and the restore;
   - record both in docs/DISCOVERY.md and docs/ASSUMPTIONS.md, and list them under Deviations.
   From now on, stop and ask before changing any system property or out-of-box record, even when it is the fix.

Phase 4 is Release Management (master prompt §10, Phase 4). Releases follow decision 1 from Phase 1 (docs/DISCOVERY.md item 10): a release is a normal change named "SYN RELEASE <service> <version>", and its member changes point to it through parent. In addition to the gate:

1. The release change.
   - Its risk is the highest risk tier among its members, set by code. There is no separate assessment.
   - Its authorization (Change Management at Assess, then CAB Approval at Authorize) is the go-live authorization, with an authorization interrupt at each step, as for any normal change.
   - The readiness gate runs before the release change is submitted for authorization. The go/no-go comes after authorization.

2. Deployment tasks. The release change carries one implementation task per environment (DEV, TEST, STAGE, PROD), each with that stage's result recorded on it. Member changes get no tasks of their own: they close with the release, and their close notes name the release change. This replaces the per-member PROD tasks in §6.6; list it under Deviations.

3. S06. Update its expectation to this flow, cite docs/DISCOVERY.md, and list the change under Deviations. Don't weaken the rest: the readiness gate must still fail first and name the member that is awaiting authorization, and all four stages must pass.

4. Release history for Phase 5. Confirm that the 20 seeded release changes carry what the release on-time metric needs (planned end and actual end). Show the on-time count read from ServiceNow next to the one in ground_truth.json (17 of 20).

5. Cost. Report the total number of LLM calls and tokens for the gate run, taken from the audit log.

Save the report as docs/phase-reports/phase-4.md, commit locally, and stop.
```

**What came back:** Phase 4 committed as `2d80983`.
- **Tests:** 138 unit tests passed.
- **S06 passed:**
  - the readiness gate failed first while one member was still awaiting authorization;
  - the release change then went through Change Management at Assess and CAB Approval at Authorize, then the go/no-go;
  - DEV, TEST, STAGE and PROD each recorded `result=passed` on the release change;
  - the four members closed `successful`, with close notes naming the release change;
  - the release notes have their three sections.
- **Release history:** ServiceNow and `ground_truth.json` agree that 17 of 20 seeded releases were on time.
- **Cost:** 7 LLM calls and 17,177 tokens.
- **New finding:** ServiceNow's normal change model adds its own Implement and Post-implementation-testing tasks on the way into Implement, and leaves them Canceled. The agent can't delete them (HTTP 403).

**Phase 4 accepted,** once the report showed the restore unit tests for the two approved settings.

**Found after acceptance:** the Phase 4 report says the readiness gate returns only the first failure. An unauthorized member is reported alone, "before plan quality, conflicts, freeze, CI ownership, open P1/P2, or release notes". §6.5 requires the interrupt to name *every* failing member and check, so owners can fix everything in one pass.
- **What's reasonable:** holding back the LLM plan-quality check until the members are authorized saves cost.
- **What isn't:** holding back the deterministic checks. They cost nothing, so they should all be reported together.

The fix goes into the Phase 6 message. The review missed this because only the summary was read, not the full report. **Lesson:** before accepting a phase, read the full report, not just the summary.

---

## Message 10: Start Phase 5 (Metrics and continual improvement)

**When:** in a new session, after Phase 4 is published.

**Why each addition to the master prompt's Phase 5 gate:**
1. **Population and period:** "equals the ground truth exactly" only means something if both sides count the same records over the same period. That has to be written down before any number is computed. The period must end at the fixture anchor, not at the day the report runs.
2. **Independence:** if the metrics code and the ground-truth code share formulas, a matching result proves nothing.
3. **Numbers in the commentary:** the LLM must not invent or alter a figure.
4. **Standard change candidates:** continual improvement proposes; a human decides.
5. **The change model's own tasks** must not leak into any count.

```
Context: this is a new Grok Build session. Phases 0 to 4 are complete and accepted (Phase 4 is 2d80983 on grok-build, followed by my merge commits). Before doing anything, read:
- prompts/grok-build-change-release-deployment-agents.md (the master prompt; follow it exactly)
- docs/phase-reports/ (phase-0.md to phase-4.md), docs/DISCOVERY.md and docs/ASSUMPTIONS.md
- docs/setup/PDI_AND_WORKSTATION_SETUP.md

Environment on this PC:
- .env in the repo root has all required settings. Load it at runtime; never print, log or commit its values.
- Before every uv command, make sure UV_PROJECT_ENVIRONMENT is set; if it isn't, set it in that same command: $env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA 'venvs\ChangeManagementAgent'. Never create .venv inside the repository, and never hard-code absolute paths or user names.
- Only one PC works on this repository at a time.
First run uv sync, uv run pytest and uv run cm-agents doctor, and show the output. If anything fails, stop.

Phase 5 is Metrics and continual improvement (master prompt §10, Phase 5). The §8.4 definitions are binding, with incident.u_caused_by in place of caused_by (docs/ASSUMPTIONS.md). In addition to the gate:

1. Population and period. Before computing anything, write down in docs/ASSUMPTIONS.md exactly which records each metric counts. Use that same rule in the metrics code and in ground_truth.json:
   - only seed records (counts_in_metrics), never scenario records or ServiceNow's own demo records;
   - whether the 20 release changes count in the change metrics, and whether the four 2025.11.0 releases that open before history_start fall inside the period;
   - the period: S09 covers the 12 months ending at the fixture anchor (2026-10-27 00:00 UTC), not the date the report runs. Add explicit --from and --to options, so the same report can be reproduced on any day.
   If ground_truth.json and ServiceNow disagree, change neither until you have found which one is wrong against §8.4. Report the disagreement with both values.

2. Independence. The metrics code computes every number from ServiceNow, and must not import or share formula code with the generator that wrote ground_truth.json; otherwise a match proves nothing. Rounding helpers may be shared. Show the import lists of both modules.

3. Numbers in the commentary. The LLM writes the commentary only. Add a check that every number in the commentary appears in the computed metrics table; if one doesn't, the report fails. Add a unit test with a commentary that cites a number not in the table.

4. Standard change candidates. Propose them only; don't create templates or proposals. For each candidate, show its signature, executions, failures, caused incidents and a proposed template name.

5. The change model's own tasks. Confirm that no metric counts the Canceled Implement and Post-implementation-testing tasks the change model adds, and that teardown removes them along with their changes (Phase 6 proves this in a full cycle).

6. Cost. Report the total number of LLM calls and tokens for the gate run, taken from the audit log.

Save the report as docs/phase-reports/phase-5.md, commit locally, and stop.
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
