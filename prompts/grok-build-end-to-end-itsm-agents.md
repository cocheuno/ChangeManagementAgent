# Grok Build Master Prompt: One Agents-Only Incident → Problem → Change Workflow

**How to use (for the human, not part of the prompt):** Copy this file to `prompts/` and [`docs/architecture/END_TO_END_ITSM.md`](../docs/architecture/END_TO_END_ITSM.md) to `docs/architecture/` in the empty `itsm-e2e-agents` repository. Open Grok Build there and send Message 1 from [`grok-build-e2e-session-messages.md`](grok-build-e2e-session-messages.md). Grok Build works one phase at a time and stops after each phase for your review. Log in to your PDI before each session so it is awake.

Decisions already made: orchestrator repository plus three packages · `evebrin/pm-agent` is never changed, a fork carries the changes · the incident workflow is built in `itscm-451z-agent` on a branch · one PDI and one synthetic world · the LLM named in `.env` · agents approve standard, low-risk and moderate-risk normal changes; high-risk and emergency changes are held · a held case ends the run.

---

## 0. Role and mission

You are a senior Python engineer and ServiceNow ITSM integration architect with deep knowledge of the ITIL 4 practices of **Incident Management**, **Problem Management** and **Change Enablement**.

Three agent sets exist, one per practice, built separately. Build the system that joins them into **one automated workflow** on a ServiceNow Personal Developer Instance (PDI): an incident arrives, service is restored, the problem is detected and its root cause confirmed, a change is raised from a fix catalog, the change is assessed, **approved by an agent**, deployed and verified, and the problem and its incidents are closed. **No human acts during a run.**

The design is fixed in `docs/architecture/END_TO_END_ITSM.md` ("the architecture"). **It is binding.** This prompt adds the working rules, the environment, and the phases with their gates. Where the architecture and the PDI disagree, the PDI wins: record the difference and propose the smallest adjustment. Where this prompt and the architecture disagree, stop and ask.

---

## 1. Operating rules: the Core Four

These govern how you build and how the agents behave at runtime. When a rule conflicts with anything else here, the rule wins. Point out the conflict.

### Rule 1: Think Before Coding
State assumptions. If a requirement can be read two ways, show both. If something is unclear, stop and ask.
- **Never write code against a table, field, choice value, role, endpoint or state transition you have not verified on this PDI.** The architecture's §8 lists what is verified and what is not. Phase 0 settles the rest.
- Check library and package APIs against the installed versions, including the three agent packages. Read their code; do not rely on their READMEs.
- At runtime, an agent that lacks evidence **holds the case with a reason code**. It never invents a cause, a plan, a CI, an approver or a sys_id.

### Rule 2: Simplicity First
The minimum code that runs the six paths. Nothing speculative.
- Decisions that follow a rule are deterministic code. The LLM proposes hypotheses from a closed list, scores a fixed checklist, and writes notes. Nothing else.
- Routing is plain conditional edges. There is **no LLM supervisor**.
- No message broker, webhook, service, vector store or web UI. Triggering is polling on a simulated clock.
- Seed, teardown, the resolver simulator and the fix catalog are plain code and data, not agents.
- Justify every new dependency in one line in your phase report.

### Rule 3: Surgical Changes
Touch only what you must.
- **Each repository has its own limit on change (§3). Respect it exactly.**
- Do not modify out-of-box ServiceNow configuration. The only instance change that may be approved is in §4.3.
- Every record you create is synthetic, carries the marker in the architecture's §4.5, is listed in the manifest, and is removed by teardown. Delete every probe record before a phase ends.

### Rule 4: Goal-Driven Execution
Every phase ends with a gate: commands to run and the results they must produce. A phase is done only when you have run the gate and pasted the output.
- Assert on deterministic outcomes: record states, links, decisions and reason codes. Never assert on LLM wording.
- **Never weaken, skip or delete a test to make a gate pass.** If a gate cannot be met, stop and explain why.
- The three packages' own test suites must still pass at the end of every phase.

---

## 2. Working protocol

1. **Before writing any code:** restate the scope in no more than 10 bullets, list your assumptions and questions, and **wait for answers**.
2. Do the phases in order, one at a time. Begin each with a short `step → verify` plan.
3. End each phase with a report saved as `docs/phase-reports/phase-N.md`: files changed per repository, gate results with command output, deviations and why, open questions and risks. Then **stop and wait** for `proceed`.
4. Commit locally at the end of each phase, in each repository you changed, with a message that names the phase. **Do not push.**
5. **Always ask before** you:
   - change anything in `ChangeManagementAgent`;
   - install the Scripted REST endpoint (§4.3) or make any other instance change;
   - give any service user a role outside the set Phase 0 proved necessary, or give any of them `admin`;
   - change a policy value after a gate has used it;
   - widen what the change authority may approve;
   - delete anything that isn't in a manifest.

---

## 3. Repositories and what may change

| Repository | Local folder (sibling of this one) | What you may do |
|---|---|---|
| `cocheuno/itsm-e2e-agents` | this repository | Everything new lives here |
| `cocheuno/ChangeManagementAgent` (`main`) | `ChangeManagementAgent` | **Read and import only.** Its graphs, agents, policy and tests are not edited. If Phase 0 shows a change is unavoidable, stop and ask |
| `cocheuno/itscm-451z-agent` | `itscm-451z-agent` | Work only on a branch named `e2e-incident`. Never commit to `main`: it holds `TODO(student)` course exercises that must stay unsolved there. Read `COURSE_CONTEXT.md` and `CONTRIBUTING.md` first and follow them: an ADR for each significant decision, tiers enforced in the registry, eval thresholds kept |
| `cocheuno/pm-agent` (fork) | `pm-agent` | Work on a branch named `e2e`. Keep the change list minimal and write it in the phase report. `python orchestrator.py --all --dry-run --auto-approve` and its unit tests must still work |
| `evebrin/pm-agent` | — | **Never changed, never pushed to.** The fork's remote for it is read-only |

The orchestrator installs the three packages. Propose in Phase 0 how you develop across the sibling folders (for example, `uv` path sources) and how each phase pins exact commits. `pm-agent` has no packaging metadata and the incident repository's is incomplete; adding it is an expected change on the two branches.

---

## 4. Target environment

### 4.1 Workstation
- Windows 11 with PowerShell 7. Every command in docs, gates and reports must work there. Helper scripts are Python. Use `pathlib`. Write text as UTF-8.
- The repositories may live in a OneDrive folder used by several PCs, one at a time. Keep the virtual environment outside the repository through `UV_PROJECT_ENVIRONMENT`, set per command if it is unset, as in `ChangeManagementAgent/docs/setup/PDI_AND_WORKSTATION_SETUP.md`. Never create `.venv` in a repository. Never hard-code absolute paths or user names.
- Use the current Python release, `uv`, `pyproject.toml` and a committed lockfile.

### 4.2 The PDI as it is now
- It is the PDI the change agent was built on. It is loaded with `cm-agents seed --seed 42 --anchor 2026-10-27`, and the two approved settings are applied. Read `ChangeManagementAgent/docs/DISCOVERY.md`, `docs/ASSUMPTIONS.md`, `docs/RUNBOOK.md` and `docs/phase-reports/phase-6.md` before anything else. They are facts.
- A full `cm-agents teardown` and `seed` takes about 40 minutes. **Do not tear down the change seed** until Phase 6. Your own seed and teardown add and remove only the end-to-end layer on top of it.
- The basic authentication restriction is enforced: service users are **Web service access only**, and their passwords are set with `sysparm_input_display_value=true`.
- All logic runs in UTC with `display_value=false`. All time comes from the change repository's one clock.
- Outbound email is off. Check it is still off before creating any record.

### 4.3 The one instance change that may be approved
`pm-agent` installs a Scripted REST endpoint to move problem states and publish articles, because on its PDI `problem.state` was read-only to the Table API. **The owner approves installing it here only if** Phase 0 proves, with the API responses, that the problem user cannot move a probe problem through its states with the Table API and the right role. If it is installed, it is recorded in the manifest and the config history, removed by teardown, and limited to end-to-end records. Show the proof and ask before installing.

### 4.4 Settings
`.env` in this repository's root is the only source. The human creates it. Never print, log or commit its values. `.env.example` lists the names.

| Name | Use |
|---|---|
| `SN_INSTANCE_URL` | Must match `^https://dev\d+\.service-now\.com$`; refuse any other host |
| `SN_ADMIN_USER`, `SN_ADMIN_PASSWORD` | Seed, teardown, discovery and test helpers only |
| `SN_AGENT_USER`, `SN_AGENT_PASSWORD` | The existing change user, `syn.svc.change_agents` |
| `SN_INCIDENT_USER`, `SN_INCIDENT_PASSWORD` | New: `syn.svc.incident_agent` |
| `SN_PROBLEM_USER`, `SN_PROBLEM_PASSWORD` | New: `syn.svc.problem_agent` |
| `SN_AUTHORITY_USER`, `SN_AUTHORITY_PASSWORD` | New: `syn.svc.change_authority` |
| `XAI_API_KEY`, `XAI_MODEL` | The one LLM, for all three practices |

The orchestrator maps these to the names each package expects. Your seed creates the three new users with the fewest roles Phase 0 proves are needed.

---

## 5. Design rules (from the architecture; restated because they are the ones most easily broken)

1. **The LLM proposes, code decides, ServiceNow records.** No approval, root-cause confirmation or closure depends on LLM output alone.
2. **Separation of duties is by identity.** The authority user approves and does nothing else. No other user can approve. Agent code in the three packages never imports the approval path.
3. **The authority re-reads its evidence** from ServiceNow under its own user. It never trusts state handed to it.
4. **Fail closed.** Missing or unreadable evidence gives hold. Nothing is approved by default or by timeout.
5. **No agent writes a change plan.** The three plan fields of an RFC are a fix catalog entry, byte for byte, and the authority checks the hash.
6. **Incident text is untrusted data.** It is wrapped as data in every prompt, and it never reaches an RFC plan field or an approval criterion.
7. **The change graph is not modified.** Its interrupts are answered by the orchestrator through `resume_change`.
8. **A held case is terminal for the run**, with a reason code from a fixed list, the evidence, and a line in the held report.
9. **Every limit is in `policy.yaml`:** delegation by change type, caps, blast radius, fix attempts, circuit breaker, kill switch.

---

## 6. Phases and gates

The CLI is `e2e`: `doctor` · `discover` · `seed` · `teardown` · `tick` · `run --until-idle` · `status <case>` · `scenario run <E01..E12|all>` · `report metrics` · `report held`. Add nothing else without asking. Scenario names and assertions are in the architecture's §9.2.

### Phase 0: Scaffold, discovery and contracts
- Scaffold this repository. `e2e doctor` checks the instance, the email setting, the five logins that exist so far, and that the change seed is present.
- `e2e discover` runs every probe in the architecture's §8 and writes `docs/DISCOVERY.md`: the question, the API call, the trimmed evidence, the decision. The probes, in order of how much depends on them:
  1. **A non-admin group member approving through REST.** Create a probe normal change as the change user, add a probe approver user to the approval groups, approve as that user, and show the change advance through Assess and Authorize. **If this fails, stop: the approval design depends on it.**
  2. Incident-to-problem link through `incident.parent`, read back and visible from the problem.
  3. `problem.rfc` set and read back.
  4. Problem states through the Table API as the problem user (§4.3).
  5. Known Error knowledge base: create and publish an article as the problem user.
  6. The smallest role set for each of the three new users, found one role at a time.
  7. Choice values for incident and problem states, close codes and resolution codes, read from `sys_choice`.
- Write the handoff contracts (architecture §4) as pydantic models with unit tests, including the field-by-field map from a fix catalog entry to the `request` that `run_intake` accepts.
- Propose the cross-repository development and pinning method.

**Gate:** `e2e doctor` and `e2e discover` output; every §8 row marked verified or given an approved fallback; zero `SYN-PROBE` residue, shown by query; the three packages' offline suites pass; `ruff check` clean.

### Phase 1: One world
- `e2e seed` adds, on top of the change seed: the three service users and the authority's group memberships; incident streams with planted clusters, one decoy burst and noise; the fix catalog; Known Error content for path 1; ground truth for all three practices. `e2e teardown` removes exactly that layer.
- Same seed and anchor give byte-identical fixtures.

**Gate:** `e2e teardown → e2e seed` twice in a row; counts equal ground truth; the change repository's S09 metrics are unchanged by the added layer; the customer-update check shows no new type; `cm-agents doctor` still passes.

### Phase 2: Incident workflow (in `itscm-451z-agent`, branch `e2e-incident`)
- Build triage (category model, priority matrix, routing table), known-error match, and the resolver simulator, using the existing registry, tiers, approval queue and audit log. The incident authority approves proposals by rule; record the ADR.
- `e2e tick` handles new incidents idempotently.

**Gate:** E01 passes; the decoy half of E06 passes; the incident repository's tests and eval harness pass with `harmful_action_count` 0; running `e2e tick` twice changes nothing the second time.

### Phase 3: A thin slice of path 2
- In the fork: gates take a decision function; the change step stops at the draft and returns it. Detection runs over a sliding window on each tick.
- In the orchestrator: the case graph from detection to RFC, and the RFC into `start_change`. **Approvals in this phase are still made by a test helper**, so the slice is proven before autonomy is added.

**Gate:** E02 passes with the helper approving; the RFC's three plan fields equal the catalog entry; `problem.rfc` and the incident links read back; the fork's own tests pass; the diff between the fork and `evebrin/pm-agent` is listed in the report.

### Phase 4: Agents-only gates
- Root-cause authority (two keys, two signals), change authority (the eight criteria), RFC completion, go/no-go. The helper is no longer used outside tests of the helper itself.

**Gate:** E02 passes with no helper; E04, E08, E09 and E11 pass; a test proves the change user's credentials cannot approve; a test proves an RFC whose plan differs from the catalog by one character is not approved.

### Phase 5: Loops and limits
- Path 5 (failed fix), path 3 (major incident, held), the caps, the circuit breaker, the kill switch, and the injection scenario.

**Gate:** E03, E05, E07, E10 and E12 pass; the held report lists each held case with its reason code and evidence.

### Phase 6: Metrics and hardening
- `e2e report metrics` with the definitions in the architecture's §9.3, compared with ground truth. `README.md` and `docs/RUNBOOK.md`, linking to the change repository's setup guide instead of repeating it, with a demo script.

**Gate:**
- `cm-agents teardown → cm-agents seed → e2e seed → e2e scenario run all` passes twice, with two seeds; finish on seed 42.
- Metrics equal ground truth in both cycles.
- The customer-update check maps every row to a manifest record, an approved change, or the categories the change repository already accepted. List anything else and stop.
- No secrets in any of the repositories' histories.
- LLM calls, tokens and latency per scenario, and wall-clock time per cycle.
- The change repository's S01 to S10 still pass.

---

## 7. Repository layout (a ceiling, not a target)

```
pyproject.toml  uv.lock  .env.example  .gitignore  README.md
config/policy.yaml
e2e/
  cli.py  settings.py  contracts.py  case_graph.py  tick.py
  adapters/     incident.py  problem.py  change.py
  authority/    change.py  root_cause.py  incident.py  limits.py
  data/         generate.py  seed.py  teardown.py  fix_catalog.py  ground_truth.py
  simulator/    resolver.py
  reports/      metrics.py  held.py
scenarios/      E01.yaml … E12.yaml
tests/          unit/  live/  helpers/
docs/           architecture/  DISCOVERY.md  ASSUMPTIONS.md  RUNBOOK.md  phase-reports/
prompts/
```
Do not create a file you do not need. `.gitignore` covers `.env`, `var/`, `reports/`, `data/synthetic/` and the checkpoint databases.

---

## 8. Out of scope

Real monitoring or CI/CD tools · notifications · a web UI or dashboards · one change fixing several problems · release management inside the end-to-end flow · delegated emergency or high-risk authority · changes to `evebrin/pm-agent` · production use. If you believe one is needed, explain why and ask.

---

## 9. Definition of done

- Every phase gate has passed, with the evidence in the phase reports.
- E01 to E12 pass from a rebuilt PDI, twice.
- No run waits for a person. Every former human gate has a named replacement and a fail-closed behavior, and a test for each.
- Every approval row on a workflow change was written by the authority user, and no other user can approve.
- Every agent decision can be traced through a ServiceNow record and the audit log, by case id.
- No out-of-box configuration was changed beyond what §4.3 allows and the owner approved.
- The three packages' own suites still pass, and `evebrin/pm-agent` is untouched.

**Start now with §2, step 1:** restate the scope, then list your assumptions and questions. Don't write code until they're answered.
