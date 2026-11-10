# Architecture Design Prompt: One Autonomous Incident → Problem → Change Workflow

**How to use (for the human, not part of the prompt):** Fill in the three bracketed repository names in §1. Give the assistant read access to all three repositories, then paste everything below the line. The assistant first sends an inventory and its questions and stops. After you answer, it writes the architecture document. It writes no code. The approved document then becomes the input for a phased build prompt, in the same way [`design-request.md`](design-request.md) produced the change master prompt.

Decisions already made: agents only at runtime, including approvals · ServiceNow stays the system of record · the three existing agent sets are reused, not rewritten · the repository strategy is an open question the design must answer.

---

## 0. Role and mission

You are a principal architect for agentic systems and an expert in the ITIL 4 practices of **Incident Management**, **Problem Management** and **Change Enablement** (with Release and Deployment Management), and in ServiceNow ITSM.

We have three working agent sets, one per practice, each built separately in its own repository. Design the architecture that joins them into **one automated end-to-end workflow**: an incident arrives, service is restored, the underlying problem is identified and its root cause found, a change request is raised for the fix, the change is assessed, **approved by agents**, deployed and verified, and the problem and its incidents are closed. No human acts inside the running workflow.

Your deliverable is an **architecture design document**, not code. It must be specific enough that a coding agent can build from it one phase at a time.

---

## 1. Read these first

| Practice | Repository | Notes |
|---|---|---|
| Incident Management | `[owner/incident-agent-repo]` | Inventory it yourself |
| Problem Management | `[owner/problem-agent-repo]` | Inventory it yourself |
| Change Enablement, Release, Deployment | `cocheuno/ChangeManagementAgent` (branch `grok-build`) | Described below |

For each repository, read the code, not only the README. For the change repository, start with:

- `prompts/grok-build-change-release-deployment-agents.md`: the master prompt. Its §1 (Core Four rules), §5.2 (design principles) and §5.5 (human-in-the-loop) are the conventions the combined system inherits or deliberately changes.
- `docs/DISCOVERY.md` and `docs/ASSUMPTIONS.md`: what was verified on the ServiceNow PDI. These are facts, not suggestions.
- `cm_agents/graphs/` (`change_graph.py`, `release_graph.py`, `state.py`, `runner.py`): the LangGraph graphs, their state, and their interrupts.
- `cm_agents/agents/`: intake, risk, scheduling, authorization, release, deployment, review, metrics.
- `config/policy.yaml`: governance policy. `scenarios/` and `tests/live/`: the acceptance scenarios.

What is already known about the change repository, so you do not need to rediscover it:

- Python 3.12, LangGraph with a SQLite checkpointer, Grok through the xAI API, `httpx` against the ServiceNow REST APIs, a `cm-agents` CLI.
- The change graph starts at `run_intake`, which consumes a `request` dictionary. This is where an RFC from Problem Management has to land.
- Graph routing is plain conditional edges. There is no LLM supervisor.
- Today the workflow **pauses for humans** at four interrupts: `requester_info`, `authorization` (once per approval step), `go_no_go` and `rollback_failed`. Agents have no tool that writes approval rows. A test helper under `tests/` plays the human approver.
- A failed PROD deployment already opens an incident and links it to the change through `incident.u_caused_by`.
- On this PDI, `incident.problem_id`, `incident.rfc` and `incident.caused_by` did not exist, and there is no `rm_release` table. Do not assume the links between incident, problem and change exist. Say how each one will be verified.

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
- Problem → Change (the RFC: affected CIs, justification, implementation, backout and test plans, deployment method, proposed window, linked problem and incidents). Map it field by field onto the `request` the change intake agent already accepts. Say where plan content comes from, given that no agent may invent it.
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

List the specific rules in the change repository that this reverses (for example, "agents do not write approval rows") so the reversal is deliberate and documented.

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

1. **First reply:** the inventory and gap tables (§3.1), your assumptions, and your questions. At minimum ask about: who owns each repository and whether merging is acceptable; whether one PDI serves all three; which LLM provider the combined system uses; the risk appetite for autonomous approval of high-risk and emergency changes; and what should happen to held cases. Then **stop and wait**.
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
