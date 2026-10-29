# Prompt Library

These are all the prompts used to build this project's agents with Grok Build. They are kept so the same approach can be reused, for example for **Problem Management** agents and their agentic workflow.

| File | What it is | When to use it |
|---|---|---|
| [`design-request.md`](design-request.md) | The original request that produced the master prompt, the decisions made before writing it, the corrections added during setup, and a ready-to-use Problem Management version of the request | When writing a new master prompt for a different ITSM practice |
| [`grok-build-change-release-deployment-agents.md`](grok-build-change-release-deployment-agents.md) | The **master prompt** for Change Enablement, Release Management and Deployment Management | Given to Grok Build at the start (session message 1) and reread in every new session |
| [`grok-build-session-messages.md`](grok-build-session-messages.md) | Every message sent to Grok Build, in order, with its reasons, plus a review checklist and reply and resume templates | During the build, at each phase boundary and after switching PCs |
| [`problem-management-primer-prompt.md`](problem-management-primer-prompt.md) | A prompt that has an AI assistant write a student primer on Problem Management, agents and agentic workflow, and analytics | Before the student starts the Problem Management project |

Related:
- [`docs/setup/PDI_AND_WORKSTATION_SETUP.md`](../docs/setup/PDI_AND_WORKSTATION_SETUP.md): the exact PDI, xAI and Windows setup, including every error met and how it was fixed. Do this before sending any prompt.
- [`docs/phase-reports/`](../docs/phase-reports/): Grok Build's report for each phase.
- On the `grok-build` branch, `docs/DISCOVERY.md` and `docs/ASSUMPTIONS.md`: what Phase 0 verified on the PDI.

---

## Adapting the master prompt to Problem Management

The master prompt has two kinds of section: some can be kept almost word for word, and some describe the domain and must be rewritten.

### Keep these, editing only names
| Section | What it gives you |
|---|---|
| §1 Operating rules: the Core Four | The four rules, applied both to building the system and to how the agents behave at runtime |
| §2 Working protocol | Questions first, one phase at a time, a report and a stop after each phase, and an "always ask before" list |
| §4.1 ServiceNow PDI | The instance guard, hibernation detection, two credential sets, the basic authentication restriction, UTC handling, a single clock, and the email check |
| §5.1–5.2 Stack and design principles | "The LLM proposes, code decides, ServiceNow records"; record text is untrusted data; least-privilege tools; idempotency through `correlation_id`; structured LLM output |
| §5.5 Human-in-the-loop mechanics | Interrupt types, and decisions recorded in ServiceNow rather than in the agent |
| §10 Phase pattern | Discovery first, then data, the core agents, the remaining agents, metrics, and hardening, each with a gate of commands and expected results |
| §11–13 | Repository layout as a ceiling, out-of-scope list, definition of done |

### Rewrite these for the new practice
| Section | Problem Management starting points (Phase 0 must verify every table, field and choice value) |
|---|---|
| §0 and §3 Domain model | ITIL 4 Problem Management: **problem identification** (trend analysis of incidents, recurring and major incidents), **problem control** (analysis, workarounds, known errors), **error control** (managing known errors, evaluating fixes, raising changes). Boundaries: Incident Management restores service, Problem Management finds and removes causes, and Change Enablement authorizes the fix. |
| §4.2–4.3 ServiceNow objects and discovery items | Likely objects: `problem` (states, cause, workaround and fix fields, known-error flag), `problem_task` (for example root cause analysis tasks), `incident.problem_id`, known-error knowledge articles (`kb_knowledge`), the link from a problem to the change that fixes it, and the CMDB. Check the state model and mandatory fields with a probe record, as Phase 0 did here. **Warning:** this project's PDI (Australia, patch 3) had no `incident.problem_id`, `incident.rfc` or `incident.caused_by`, even with Problem Management active. Check your own PDI first (setup guide, Part B8). If they're missing, find how the problem form's Incidents related list is linked, then decide how to link incidents to problems before Phase 1. |
| §5.3 Workflow graph | Detect → log and prioritize → analyze (RCA) → human confirms root cause → workaround and known error → human approves publication → fix decision → raise an RFC, reusing Change Enablement → verify recurrence has stopped → close. |
| §6 Agents | Candidates, each with a deterministic core and a narrow LLM role: **Problem Detection** (code clusters incidents by CI, service, category and time window; the LLM summarizes the cluster); **Problem Logging & Prioritization**; **Root Cause Analysis Assistant** (the LLM proposes hypotheses from linked incidents, recent changes and CMDB relationships, labeled as hypotheses, and a human confirms); **Workaround & Known Error** (drafts the known-error article, and a human approves publication); **Error Control** (evaluates fix options and raises the RFC); **Review & Metrics**. |
| §7 Policy and simulation | Clustering thresholds (for example, N incidents on one CI within a time window), priority rules, and when a known error must be published. A simulator is needed only if the fix is deployed; otherwise reuse this project's change agents. |
| §8 Synthetic data | Seed incident clusters with **known root causes** in `ground_truth.json`, for example a memory leak after a change, certificate expiry, or a failing shared database. Add noise incidents that must *not* cluster. Gates can then measure how often detection is right and how much it misses, as this project's risk backtest does. |
| §9 Scenarios | For example: a recurring-incident cluster is detected; a major incident leads to a reactive problem; a workaround is published as a known error; a fix is raised as a change and recurrence stops; a false cluster is rejected; a prompt-injection attempt; a metrics report (backlog, time to known error, recurrence rate, incidents linked to known errors). |

### Lessons from this project that carry over
1. **Verify before building.** Several behaviors differed from what the prompt expected, and only Phase 0 caught them:
   - `rm_release` was missing;
   - a normal change can't be inserted as Closed;
   - the Risk Calculator overwrote the agent's value;
   - basic authentication was restricted;
   - the incident table had no links to changes or problems;
   - new standard change templates could only be created through a Standard Change Template Proposal.
2. **Ask for evidence when a finding changes the design.** In Phase 1, Grok Build first reported that normal changes get only one approval. When asked to prove it, by walking test changes through every state, it found two: Change Management at Assess and CAB Approval at Authorize. It also reported that the "Caused by Change" field was missing, and a check in the browser confirmed it. Either way, the evidence decides.
3. **Set up the PDI and workstation completely before the first prompt.** Most of the time lost was in setup (Part I of the setup guide), not in building.
4. **Keep each phase small and gated.** Review the report, check that no test was weakened, push, then continue.
5. **Save phase reports in the repository.** A new session, or another PC, can then pick up where the last one stopped.
