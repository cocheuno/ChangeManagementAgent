# Project Summary: One Automated Workflow from Incident to Problem to Change

Status as of 2026-11-19.

## What we set out to do

Three sets of AI agents existed, each built separately for one ITSM practice: Incident Management, Problem Management, and Change Enablement. The goal is to join them into a single workflow on a ServiceNow developer instance, where an incident arrives, service is restored, the underlying problem is found and its cause confirmed, a change is raised, approved **by an agent**, deployed and verified, and the problem is closed. No person acts during a run.

## What has been accomplished

**1. The change management agent was finished.**
All six build phases are complete and accepted. Its ten scenarios pass, and the whole environment was rebuilt from nothing twice to prove it is repeatable.

**2. An architecture was designed before any code was written.**
- A new repository holds the end-to-end workflow and uses the three agent sets as packages, so none of them had to be rewritten.
- Approval is done by a separate ServiceNow user that does nothing else. It re-reads its evidence from ServiceNow and approves only if eight fixed checks pass.
- AI proposes, code decides, ServiceNow records. No approval or root-cause decision rests on AI output alone.
- No agent writes a change plan. Plans come word for word from a catalog of known fixes.
- A root cause needs two independent kinds of evidence, at least one of which is not incident text.
- Agents may approve standard, low-risk and moderate-risk changes. High-risk and emergency changes are held.

**3. Four of seven build phases are accepted.**

| Phase | What it delivered | Status |
|---|---|---|
| 0. Discovery | Proved on the live instance what works, including that a non-admin user can approve a change | Accepted |
| 1. Shared data | One synthetic company with planted problems, a decoy, noise, and known answers | Accepted |
| 2. Incident workflow | Incidents are triaged, matched to known errors, and restored | Accepted |
| 3. First full path | A cluster of incidents becomes a problem, then a change that is approved, deployed and closed | Accepted |
| 4. Agents decide | Agents replace the test helpers for root cause and approval | Next |
| 5. Failure paths and limits | Failed fixes, major incidents, caps, circuit breaker, kill switch, prompt injection | Not started |
| 6. Metrics and hardening | End-to-end metrics, documentation, two full rebuilds | Not started |

## What we learned along the way

- **Verify before you build.** The instance lacked a field that standard ServiceNow logic relies on. Writing one field on a problem then updated every incident on the instance, 439 of them, nine times. It was found by asking why a number looked odd, and repaired from the audit log.
- **A passing test can prove nothing.** The first data plan was built so every check passed by design. The first "passing" end-to-end run used the answer key inside the run and reused leftovers from an earlier attempt. Both were caught only by reading the code, not the summary.
- **Read the full report, not the summary.** Several problems were absent from the summaries and present in the reports.
- **Detection alone over-triggers.** On an independent data set, detection found all four real problems and also raised three false ones. A second check on root cause is what stops a false problem becoming a change.
- **A trained model does not transfer automatically.** The incident category model scored 5 of 10 on new data, with three wrong answers at over 99% confidence. A simple rule replaced it.
- **Least privilege has to be tested.** Each agent has its own user with the smallest set of roles, found one role at a time, and tests confirm that the other users cannot approve.
- **Small design choices have side effects.** A record-naming choice caused one agent's clean-up to delete another's data.
- **Keep one place changing code at a time.** Parallel edits to the same files had to be reconciled.

## What remains

1. **Phase 4:** an agent confirms root causes and an agent approves changes, with six scenarios passing without any human or helper deciding.
2. **Phase 5:** what happens when a fix fails, when a major incident occurs, when limits are reached, and when incident text tries to manipulate the agents.
3. **Phase 6:** end-to-end metrics compared against known answers, documentation, and two full rebuilds from an empty instance.
4. **Known limits to state honestly:** emergency changes are held and not approved, the fix catalog makes plan-writing trivial, and the data is synthetic.

## Where things are

| What | Where |
|---|---|
| Design | [`docs/architecture/END_TO_END_ITSM.md`](architecture/END_TO_END_ITSM.md) |
| Build instructions and the messages sent | [`prompts/`](../prompts/) in this repository and in `cocheuno/itsm-e2e-agents` |
| Evidence for each end-to-end phase | `docs/phase-reports/` and `docs/DISCOVERY.md` in `cocheuno/itsm-e2e-agents` |
| Incident workflow | branch `e2e-incident` in `cocheuno/itscm-451z-agent` |
