# Architecture Design Prompt: One Autonomous Incident → Problem → Change Workflow

**How to use (for the human, not part of the prompt):** Give the assistant read access to the three repositories named in §1 (all three are public), then paste everything below the line. The assistant first sends an inventory and its questions and stops. After you answer, it writes the architecture document. It writes no code. The approved document then becomes the input for a phased build prompt, in the same way [`design-request.md`](design-request.md) produced the change master prompt.

Decisions already made: agents only at runtime, including approvals · ServiceNow stays the system of record · the three existing agent sets are reused, not rewritten · the repository strategy is an open question the design must answer.

---

## 0. Role and mission

You are a principal architect for agentic systems and an expert in the ITIL 4 practices of **Incident Management**, **Problem Management** and **Change Enablement** (with Release and Deployment Management), and in ServiceNow ITSM.

We have three agent sets, one per practice, each built separately in its own repository, by different people, on different stacks and at different stages of completion (§1). Design the architecture that joins them into **one automated end-to-end workflow**: an incident arrives, service is restored, the underlying problem is identified and its root cause found, a change request is raised for the fix, the change is assessed, **approved by agents**, deployed and verified, and the problem and its incidents are closed. No human acts inside the running workflow.

Your deliverable is an **architecture design document**, not code. It must be specific enough that a coding agent can build from it one phase at a time.

---

## 1. Read these first

| Practice | Repository | Branch | Owner |
|---|---|---|---|
| Incident Management | `cocheuno/itscm-451z-agent` | `main` | cocheuno |
| Problem Management | `evebrin/pm-agent` | `main` | evebrin (a different owner) |
| Change Enablement, Release, Deployment | `cocheuno/ChangeManagementAgent` | `grok-build` | cocheuno |

Read the code in each repository, not only the README. What follows was read from the code on 2026-11-10. Treat it as a starting point and correct it in your inventory wherever the code now says otherwise.

### 1.1 Incident Management: `cocheuno/itscm-451z-agent`

**Read first:** `README.md`, `docs/governance/governance.md`, `src/agent/tools/registry.py`, `src/agent/approvals.py`, `src/agent/tools/writes.py`, `src/agent/tools/schemas/`, `eval/harness.py`, `eval/thresholds.yaml`, `docs/adr/`.

- **Stack:** Python 3.12, `requests`, `pydantic`, no agent framework. Claude through the Anthropic Messages API over raw HTTP. scikit-learn models for incident category, with versioned artifacts under `src/agent/models/`.
- **It is a governed tool kit, not yet a running workflow.** There is no agent loop or graph that takes an incident from open to resolved. The README lists rungs for a workflow state machine, problem clustering, RFC drafting and CAB, but `src/agent/workflow/` holds only `routing.py` and `sla.py`, and several modules still carry `TODO(student)` markers. The design must say what has to be built here before an end-to-end run is possible.
- **What exists:**
  - Seven tools behind one registry: `classify_incident`, `search_kb`, `lookup_ci`, `find_similar_incidents` (tier `read`); `add_comment` (tier `propose`); `assign_incident` and `resolve_incident` (tier `execute_with_approval`).
  - The tier is declared in each tool's JSON schema and enforced at dispatch, never in a prompt. A fourth tier, `autonomous`, is defined but no tool has it; granting it requires an ADR.
  - Write tools return a before-image so a write can be rolled back from the audit log.
  - A priority matrix and SLA targets (`workflow/sla.py`), a category-to-group routing table (`workflow/routing.py`), and a keyword-rule poller (`rung0_poller.py`).
  - An MCP server that exposes the read-tier tools.
  - Analytics: KPIs and `analytics/change_impact.py`, which measures whether incident volume rose after a change.
  - An eval harness that runs on every pull request, with thresholds including `harmful_action_count: 0`, plus failure-injection scenarios.
- **Human pause point:** a named person approves each proposal with `python -m agent.approvals --approve <id> --as "<name>"`. The approval is bound to the exact tool and arguments and can be spent once. It is stored in a local file, `logs/approvals.jsonl`, **not in ServiceNow**. `AGENT_MODE=dry_run|live` gates all writes.
- **Audit:** append-only `logs/audit.jsonl`, also local.
- **ServiceNow:** one service account with `itil` and `itil_admin`. Records are marked by a `[SYN]` prefix on the description and by a `correlation_id` that holds the corpus number and starts with `SYN`.
- **Data:** a committed synthetic corpus (about 4,200 closed incidents, 150 open, six changes) with a ground-truth file kept outside the repository.

### 1.2 Problem Management: `evebrin/pm-agent`

**Read first:** `ARCHITECTURE.md`, `README.md` (including "Why a state API" and "Deviations from the spec"), `orchestrator.py`, `detection_agent.py`, `rca_agent.py`, `knowledge_agent.py`, `change_agent.py`, `state_api.py`, `config.py`.

- **Stack:** Python 3.11+, `requests` and `python-dotenv` only. No framework and no database. `llm.py` accepts any provider (Anthropic, OpenAI, Gemini, xAI, Ollama, OpenAI-compatible), and every LLM step has a deterministic fallback.
- **It runs end to end today**, as a linear batch: `synthetic → detect → rca → knowledge → change → close → report`. Each agent is one module with `run(context)` and a `check(context)` that rereads the PDI. State is a JSON file per run, `runs/<run_id>.json`.
- **Agents:** Problem Detection (groups by CI and service, TF-IDF similarity, at least 5 incidents in 14 days, a confidence level), Root Cause Analysis (5 Whys or Kepner-Tregoe over evidence read from the PDI; cited incidents are checked to be linked), Known Error & KB (publishes a Known Error article and posts the workaround to open incidents), Change & Closure, Reporting.
- **Human pause points:** four gates answered at the keyboard through `input()`: Gate 1 (is this a problem), Gate 2 (accept the root cause), Gate 3 (approve the change before it is created), Gate 4 (close or keep open). `--auto-approve` answers each gate with the agent's own recommendation and is labeled a rehearsal. That is not an independent decision, so it does not satisfy §3.5.
- **It overlaps the change repository.** `change_agent.py` drafts a Normal change, creates it, approves the ServiceNow approval rows itself **using the PDI admin account**, and simulates implementation to Closed / Successful. In the combined system this must hand off to the change repository's intake instead. Its recurrence check and closure (Gate 4) stay with Problem Management.
- **ServiceNow:**
  - Incidents link to their problem through `incident.parent`, because that PDI had no `incident.problem_id`. The problem links to its change through `problem.rfc`.
  - `problem.state` is read-only to the Table API there, so the repository installs its own Scripted REST endpoint (`state_api.py`) to move problem states and publish articles. This is a change to the instance, which the change repository's rules forbid without approval.
  - The integration user has `itil`, `itil_admin`, `user_admin` and `problem_coordinator`. Admin is also used at runtime for approvals and for linking closed incidents.
  - Records are marked with `correlation_id = PMSYNTH-<run_id>`.
- **Data:** 200 seeded incidents over 60 days with four planted problems, one decoy burst and noise, plus an answer key. It seeds its own post-change verification window of incidents.

### 1.3 Change Enablement, Release and Deployment: `cocheuno/ChangeManagementAgent`

**Read first:** `prompts/grok-build-change-release-deployment-agents.md` (§1 Core Four rules, §5.2 design principles and §5.5 human-in-the-loop are the conventions the combined system inherits or deliberately changes), `docs/DISCOVERY.md`, `docs/ASSUMPTIONS.md`, `cm_agents/graphs/`, `cm_agents/agents/`, `config/policy.yaml`, `scenarios/`, `tests/live/`.

- **Stack:** Python 3.12, LangGraph with a SQLite checkpointer, Grok through the xAI API, `httpx`, a `cm-agents` CLI. Phases 0 to 5 are built; Phase 6 (hardening) has not started.
- **Agents:** intake, risk, scheduling, authorization, release, deployment, review, metrics. Graph routing is plain conditional edges. There is no LLM supervisor.
- **Entry point:** the change graph starts at `run_intake`, which consumes a `request` dictionary. This is where an RFC from Problem Management has to land.
- **Human pause points:** four interrupts: `requester_info`, `authorization` (once per approval step: the assignment group at Assess, then CAB Approval at Authorize), `go_no_go` and `rollback_failed`. Agents have no tool that writes approval rows. A helper under `tests/` plays the human approver.
- **ServiceNow:**
  - The integration user has `sn_change_write`, `audit_viewer` and `sn_incident_write`, and deliberately not `itil` or `admin`.
  - A failed PROD deployment already opens an incident and links it to the change through `incident.u_caused_by`.
  - That PDI had no `incident.problem_id`, `incident.rfc` or `incident.caused_by`, and no `rm_release` table.
  - Records are marked with a `correlation_id` starting `SYN-`; the metrics count only the seed prefixes `SYN-CHG-`, `SYN-OPEN-`, `SYN-REL-` and `SYN-INC-`.
- **Data:** about 300 CIs and 1,500 historical changes for a fictional company, with `ground_truth.json`.

### 1.4 Conflicts already visible

Your gap analysis must resolve each of these, and add any others you find.

| # | Conflict | Why it matters |
|---|---|---|
| 1 | The incident repository has no running workflow | The first stage of the end-to-end flow has to be built, not only connected |
| 2 | Two change implementations: `pm-agent/change_agent.py` and all of `cm_agents` | One must own change creation, approval and deployment |
| 3 | Three approval mechanisms: a local JSONL queue, keyboard gates, and ServiceNow approval rows | Only ServiceNow approval rows are visible in the system of record |
| 4 | `pm-agent` approves changes as PDI admin | It breaks separation of duties and the least-privilege model of the change repository |
| 5 | Three identity models with overlapping broad roles (`itil_admin`, `user_admin`) | §3.5 needs one identity per duty |
| 6 | `correlation_id` is used three ways, and the incident repository selects its records with "starts with `SYN`" | On a shared PDI the incident seeder's resume query matches the change repository's `SYN-` records; teardown and metrics filters in all three must be checked for the same collision |
| 7 | Three synthetic worlds: different companies, CIs, groups and answer keys | An incident cannot flow to a problem and a change unless all three share one CMDB and one ground truth |
| 8 | Three state stores: none, a JSON run file, and LangGraph checkpoints | A case that spans days needs one answer to "where is this case now" |
| 9 | Batch versus event: `pm-agent` detects over a seeded 60-day batch | The combined flow needs detection to run as incidents arrive |
| 10 | Three LLM setups (Anthropic over raw HTTP, any provider with fallback, xAI through LangChain) and three `.env` naming schemes | One configuration is needed |
| 11 | `pm-agent` installs a Scripted REST endpoint; the change repository forbids instance changes | The instance-change rule has to be decided once |
| 12 | Each PDI was verified separately and they differ | Field and link findings (`parent`, `rfc`, `u_caused_by`) must be re-verified on the one PDI that will be used |
| 13 | Two owners | A merge needs both owners' agreement and a licence and history decision |

---

## 2. Constraints

1. **Agents only.** At runtime no human approves, confirms, supplies information or decides. Every pause point that exists today in any of the three repositories must be replaced by an agent decision, or by an automatic stop that fails closed. Humans keep three roles, all outside the running workflow: they own the policy, they read the audit trail afterwards, and they hold a kill switch.
2. **The LLM proposes, code decides, ServiceNow records.** Every decision that follows a rule is deterministic code over evidence read from ServiceNow. The LLM is used for language and judgment only: extracting structure from text, proposing hypotheses, scoring against a fixed checklist, and writing briefs and notes. An LLM output can never by itself approve a change, confirm a root cause or close a record.
3. **ServiceNow is the system of record and the integration bus.** A handoff between practices is a ServiceNow record plus its links, not a private message between agents. Anyone reading only ServiceNow must be able to follow an incident to its problem, its change and back.
4. **Reuse before rewrite.** Keep each practice's agents and tests working. Change them only where the combined workflow requires it, and list each such change.
5. **Text from records is untrusted data.** An incident description can carry a prompt injection that now travels through three practices and reaches an approval. The design must show where it is stopped.
6. **Out-of-box ServiceNow configuration is not modified** unless the design shows it is necessary and names the smallest change.
7. **Synthetic data only**, on a Personal Developer Instance, rebuilt from nothing with one command.

---

## 3. What the architecture document must contain

### 3.1 Inventory and gap analysis
One table per repository: language and framework, LLM provider, agents and what each one decides, entry points, inputs and outputs, state and persistence, ServiceNow tables and roles used, identities used, human pause points, tests and scenarios, and the build phase reached. Then one gap table: what differs between the three (stack, state shape, naming, policy format, ServiceNow client, credential model) and what is missing for an end-to-end run.

### 3.2 Repository strategy
Compare at least these three options and recommend one:

| Option | Outline |
|---|---|
| **A. Monorepo** | Merge all three into one repository with one package per practice and a shared platform package |
| **B. Orchestrator repository** | Keep the three repositories, publish each as an installable package, and add a fourth repository that holds the end-to-end graph and the contracts |
| **C. Contracts only** | Keep the three repositories fully separate; each runs as its own service and reacts to ServiceNow record changes, sharing only a versioned contract package |

Judge each on: how much existing code and history it keeps, how handoff contracts are versioned and tested, how an end-to-end test is run, how one policy and one ServiceNow client are shared, the cost if the stacks differ, and who owns what afterwards. If the repositories have different owners, say how that affects the choice. If you recommend merging, give the exact merge method that keeps each repository's history, and the target directory layout.

### 3.3 The end-to-end workflow
Draw the full flow as a Mermaid diagram and as a stage table (stage, owning practice, agent, deterministic decision, LLM role, ServiceNow writes, exit condition). It must cover these paths, not only the longest one:

| Path | Flow |
|---|---|
| **1. Known error** | Incident matches a known error → workaround applied → incident resolved. No problem or change is raised; the incident is linked to the existing problem. |
| **2. Recurring incidents (main path)** | Incidents cluster → problem logged → root cause analysis → known error and workaround → fix decision → RFC → normal change assessed, approved, deployed and verified → recurrence checked → problem and incidents closed, known error retired. |
| **3. Major incident** | P1 incident → emergency change to restore service → emergency approval → deployment → a problem raised afterwards for the root cause → post-implementation review. |
| **4. Pre-authorized fix** | The fix matches a standard change template → runs without an approval step, inside a maintenance window. |
| **5. Failed fix** | The change fails verification → rollback → a new incident linked to the change → the problem is reopened or updated, not duplicated. |
| **6. No action** | A false cluster is rejected; a problem whose fix is not worth its risk is kept as a known error with no change. |

State the practice boundaries the design enforces: Incident Management restores service and never waits for root cause; Problem Management finds causes and decides whether a fix is justified, and never deploys; Change Enablement authorizes and never changes the diagnosis. Incident resolution must not block on the problem or the change.

### 3.4 Handoff contracts
For each handoff, give a versioned schema, the trigger condition as a deterministic rule, the ServiceNow links written, and the idempotency key:

- Incident → Problem (cluster or major incident to problem record).
- Problem → Change (the RFC: affected CIs, justification, implementation, backout and test plans, deployment method, proposed window, linked problem and incidents). Map it field by field from what `pm-agent/change_agent.py` drafts today onto the `request` the change intake agent already accepts. Say where plan content comes from, given that no agent may invent it.
- Change → Problem and Incident (outcome, close code, verification evidence; what closes, what reopens).
- Deployment failure → Incident (already present as `u_caused_by`; show how it joins the loop).

Define one correlation identifier that follows a case across all three practices, and how it relates to each repository's existing thread and `correlation_id` conventions.

### 3.5 Autonomous approval
This is the largest change from the current design, where humans approve. Design it as **delegated change authority**, and be explicit about each point:

- **Which agent holds which authority** for standard, normal (per risk tier) and emergency changes, expressed in `policy.yaml`.
- **Separation of duties.** The identity that approves is never the identity that raised, assessed or deploys the change. Give each role its own ServiceNow user with least-privilege roles. Show how the approval agent becomes a valid approver on the ServiceNow approval records, and what must be verified on the PDI to prove it.
- **Independent evidence.** The approval agent re-reads its evidence from ServiceNow. It does not trust the state handed over by the agent asking for approval.
- **The decision rule.** List the deterministic criteria: risk score and tier, plan checklist result, conflict and freeze checks, window and lead time, linked problem with a confirmed root cause, test evidence, rollback readiness. The LLM writes the rationale only and cannot change the result.
- **Fail closed.** When evidence is missing or a criterion cannot be evaluated, the result is reject or hold, with the reason recorded. Nothing is approved by default or by timeout.
- **Limits on autonomy.** Per-service and per-period caps on auto-approved changes, a maximum blast radius, freeze periods, a circuit breaker after failed changes, and a kill switch that stops approvals without stopping incident handling.
- **Every other human gate.** Do the same for root-cause confirmation, known-error publication, missing requester information, go/no-go, and a failed rollback: name the replacing agent or automatic stop, its rule, and its record in ServiceNow.
- **What "held" means.** A held case is a terminal state of the automated run with a complete record of why. State what happens to it next and confirm that no path quietly depends on a human.

List the specific rules this reverses in each repository, so the reversal is deliberate and documented: in the change repository, "agents do not write approval rows"; in the incident repository, that no tool holds the `autonomous` tier and that approvals are made by a named person; in the problem repository, the four keyboard gates. Say which existing safeguard carries over: the incident repository's approval bound to exact arguments and spent once, its before-images and its `harmful_action_count: 0` threshold are candidates for the whole system.

### 3.6 Orchestration and runtime
- How the three practices are composed: one parent graph with subgraphs, separate graphs started by ServiceNow record events, or a mix. Recommend one and justify it. No LLM supervisor.
- State: what is shared across practices, what stays private, and where it is persisted. A case may span days and several process restarts.
- Triggering: how a new or changed record starts the next stage (polling, webhook, queue), and how duplicates are prevented.
- Concurrency: many incidents joining one problem, several problems proposing changes to the same CI, a change that fixes more than one problem.
- Loop control: path 5 can cycle. Give the rule that ends it.
- One clock, one time-zone rule, one policy file layout, one audit format.

### 3.7 Shared platform
What moves into shared code and what stays per practice: ServiceNow client and instance guard, credential and identity model, policy loading, LLM wrapper and structured output, untrusted-data wrapping, audit, clock, CLI. For each item, name which repository's existing implementation becomes the shared one and why.

### 3.8 ServiceNow data model
Every table, field, link and role the combined workflow needs, each marked **verified** (with the source in `docs/DISCOVERY.md` or the other repositories' discovery notes) or **to verify**. For each item to verify, give the probe that settles it and the fallback if it is missing. Never present an unverified field name as fact.

### 3.9 Synthetic data, scenarios and metrics
- One seeded data set with ground truth that spans all three practices: incident clusters with known root causes, noise incidents that must not cluster, and fixes with known outcomes.
- End-to-end acceptance scenarios, at least one per path in §3.3, plus a prompt-injection scenario that starts in an incident and must not reach an approval, a separation-of-duties scenario, a fail-closed scenario and a kill-switch scenario. Each asserts on deterministic outcomes (record states, links, decisions), never on LLM wording.
- End-to-end metrics with binding definitions: time to restore, time from first incident to problem, time to known error, time from problem to change, time to permanent fix, recurrence rate after the fix, auto-approval rate, rate of auto-approved changes that failed, and held cases by reason.

### 3.10 Migration plan
Phases in order, each small, each with a gate of commands and expected results, each leaving the three existing test suites passing. Start with discovery and contracts, then one thin slice of path 2 end to end, then the remaining paths, then autonomous approval limits, then metrics and hardening. Say what is deliberately left out.

### 3.11 Risks and open questions
Risks ranked by impact, each with its mitigation. Then the questions only the human can answer.

---

## 4. Design rules

- **Think before designing.** State assumptions. Where a requirement can be read two ways, show both readings. Do not design against a table, field, API or library behavior you have not verified; mark it to verify.
- **Simplicity first.** The smallest architecture that runs the six paths. No message broker, service mesh, vector store or extra agent unless you show the path that needs it.
- **Surgical changes.** Every change to an existing repository traces to a requirement in this prompt.
- **Goal-driven.** Every design element has a check that proves it works.
- Where this prompt conflicts with what the repositories or the PDI actually do, the evidence wins. Point out the conflict.

---

## 5. Working protocol

1. **First reply:** the inventory and gap tables (§3.1), your assumptions, and your questions. At minimum ask about: whether both owners accept a merge or a shared package; whether the incident workflow is to be built in its own repository or in the combined one; whether one PDI serves all three and which synthetic world survives; which LLM provider the combined system uses; the risk appetite for autonomous approval of high-risk and emergency changes; and what should happen to held cases. Then **stop and wait**.
2. **Second reply:** the full architecture document, written to `docs/architecture/END_TO_END_ITSM.md`, with the decisions and their reasons in a short table at the top.
3. Write no code and change no existing file in either reply.

---

## 6. Acceptance checklist

- All six paths are drawn, and every stage names its owner, its deterministic decision and its ServiceNow writes.
- No runtime step waits for a human. Every former human gate has a named replacement and a fail-closed behavior.
- The approving identity is separate from the requesting, assessing and deploying identities, and the document says how that is proven on the PDI.
- No approval, root-cause confirmation or closure depends on LLM output alone.
- Every handoff has a schema, a trigger rule, its ServiceNow links and an idempotency key.
- One repository strategy is recommended, with the reasons the other two were rejected.
- Every ServiceNow object is marked verified or to verify, with a probe for each one to verify.
- The injection path from incident text to change approval is traced, and the point where it stops is named.
- The migration plan has a gate per phase and keeps the existing tests passing.
- Nothing is invented: no table, field, role, library API or repository detail is stated without a source.
