# How the Master Prompt Was Designed

This is the request that produced [`grok-build-change-release-deployment-agents.md`](grok-build-change-release-deployment-agents.md), the decisions made before writing it, and the corrections added once setup started. At the end is the same request rewritten for Problem Management.

---

## 1. The original request (verbatim)

> Act as an expert in Change enablement, release management, deployment management IT Service Managment processes.  Create the prompt for Grok Build to create a set of agents to use in an agentic workflow to perform Change enablement, release management, deployment management IT Service Managment processes using ServioceNow PDI and synthetic data.  Use The Core Four Rules of Karpathy's CLAUDE.md in your prompt.  Do you have any questions before starting?

"The Core Four" refers to the four rules in the CLAUDE.md based on Andrej Karpathy's notes on how LLMs go wrong when coding:
1. **Think Before Coding:** don't assume, don't hide confusion, surface tradeoffs.
2. **Simplicity First:** the minimum code that solves the problem, nothing speculative.
3. **Surgical Changes:** touch only what you must, and clean up only your own mess.
4. **Goal-Driven Execution:** define success criteria, and loop until they are verified.

## 2. Decisions made before writing

| Question | Options offered | Chosen | Why it matters |
|---|---|---|---|
| Which runtime should the agents be built on? | Python + LangGraph; Python + CrewAI; plain Python; ServiceNow-native agents | **Python + LangGraph** | Its saved workflow state and built-in pause points support human approval and resuming days later |
| How much authority should the agents have? | Approval by risk tier; fully autonomous; advisory only | **Approval by risk tier** | Standard changes run on their own; normal and emergency changes wait for human CAB/ECAB approval in ServiceNow |
| How much synthetic data? | Small; medium; large; reuse PDI demo data | **Medium** | About 300 CIs and 1,500 historical changes, enough for risk scoring with known answers to check against |
| What form should the deliverable take? | Phased master prompt; master prompt + rules file; one-shot prompt | **Phased master prompt** | Each phase ends with a verification gate and stops for human review |

## 3. Corrections added during setup
Each one came from a real problem met while setting up the PDI or workstation. All are now in the master prompt.

| Change | Where in the master prompt | What prompted it |
|---|---|---|
| Name every `.env` setting (`SN_INSTANCE_URL`, `XAI_API_KEY`, and so on), and never print or commit values | §4.1 | Without fixed names, Grok Build would have invented its own |
| The developer machine is Windows 11 with PowerShell; scripts are Python, not bash | §5.1 | The user works on Windows; bash commands failed |
| Record the basic authentication restriction; the integration user is **Web service access only** | §4.1, §4.3 item 13 | The PDI rejected a correct password over REST (HTTP 401) |
| The repository may live in OneDrive; the virtual environment stays outside it; no hard-coded paths | §5.1 | The repository is shared between two PCs through OneDrive |
| Add `cm-agents discover` (the repeatable Phase 0 probe) to the CLI list | §7.3 | Grok Build added it in Phase 0 and reported it as a deviation |

## 4. The same request, rewritten for Problem Management
Copy this, adjust the "already decided" list to your situation, and send it to the assistant you use to write the master prompt.

> Act as an expert in ITIL 4 Problem Management and ServiceNow ITSM. Create the prompt for Grok Build to create a set of agents to use in an agentic workflow to perform Problem Management (problem identification, problem control and error control, including workarounds and known errors) using a ServiceNow PDI and synthetic data. Use The Core Four Rules of Karpathy's CLAUDE.md in your prompt.
>
> Use these files from the GitHub repository cocheuno/ChangeManagementAgent as models:
> - prompts/grok-build-change-release-deployment-agents.md, for structure: rules, working protocol, verified discovery, agents with deterministic cores, synthetic data with ground truth, scenarios, and phase gates;
> - docs/setup/PDI_AND_WORKSTATION_SETUP.md, for the environment;
> - prompts/grok-build-session-messages.md, for how to run the sessions.
>
> Already decided:
> - Windows 11 with PowerShell 7;
> - Python + LangGraph, with Grok through the xAI API;
> - humans confirm root causes and approve known-error publication;
> - medium synthetic data with seeded patterns whose answers are known;
> - a phased master prompt with a verification gate per phase;
> - the PDI enforces ServiceNow's basic authentication restriction, so the integration user is Web service access only;
> - the repository may live in OneDrive, with the virtual environment kept outside it.
>
> Do you have any questions before starting?
