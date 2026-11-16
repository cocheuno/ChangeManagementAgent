# Grok Build Session Messages: End-to-End ITSM Agents

These are the messages sent to Grok Build for the end-to-end build, in order, with the reason for each. The master prompt is [`grok-build-end-to-end-itsm-agents.md`](grok-build-end-to-end-itsm-agents.md). The design it follows is [`docs/architecture/END_TO_END_ITSM.md`](../docs/architecture/END_TO_END_ITSM.md).

The review checklist, the reply template and the resume template are the same as for the change build: see the last three sections of [`grok-build-session-messages.md`](grok-build-session-messages.md). Two additions to the checklist for this build:

- **Check every repository that changed**, not only the orchestrator. Run the `git diff --stat -- tests` and secrets checks in each.
- **Check the limits in the master prompt §3:** nothing committed to `main` of `itscm-451z-agent`, nothing in `ChangeManagementAgent` changed without your approval, nothing pushed to `evebrin/pm-agent`.

---

## Before Message 1: set up the folders

**Why:** Grok Build works across four repositories, and the master prompt refers to them as sibling folders.

1. Clone the four repositories side by side, in the same parent folder as `ChangeManagementAgent`:

   ```powershell
   git clone https://github.com/cocheuno/itsm-e2e-agents.git
   git clone https://github.com/cocheuno/itscm-451z-agent.git
   git clone https://github.com/cocheuno/pm-agent.git
   ```

2. Copy the two documents into the new repository:

   ```powershell
   New-Item -ItemType Directory -Force itsm-e2e-agents\prompts, itsm-e2e-agents\docs\architecture
   Copy-Item ChangeManagementAgent\prompts\grok-build-end-to-end-itsm-agents.md itsm-e2e-agents\prompts\
   Copy-Item ChangeManagementAgent\prompts\grok-build-e2e-session-messages.md itsm-e2e-agents\prompts\
   Copy-Item ChangeManagementAgent\docs\architecture\END_TO_END_ITSM.md itsm-e2e-agents\docs\architecture\
   ```

3. Create `itsm-e2e-agents\.env`. Copy the five ServiceNow and xAI values from `ChangeManagementAgent\.env`, then add three new user names and passwords of your choosing:

   ```
   SN_INCIDENT_USER=syn.svc.incident_agent
   SN_INCIDENT_PASSWORD=<choose one>
   SN_PROBLEM_USER=syn.svc.problem_agent
   SN_PROBLEM_PASSWORD=<choose one>
   SN_AUTHORITY_USER=syn.svc.change_authority
   SN_AUTHORITY_PASSWORD=<choose one>
   ```

   The users do not exist yet. Phase 1's seed creates them with these passwords.

4. Confirm the PDI is awake and still on seed 42, from the `ChangeManagementAgent` folder:

   ```powershell
   uv run cm-agents doctor
   ```

---

## Message 1: Start the project (before Phase 0)

**When:** in a new Grok Build session opened in the `itsm-e2e-agents` folder.

**Why each part:**
- **Read the architecture first:** it is the design; the master prompt only adds rules and gates.
- **Read the change repository's discovery files:** they are verified facts about this PDI and save rediscovery.
- **The three limits on change:** they are the rules most likely to be broken by a tool trying to be helpful.
- **Stop after the questions:** the first reply must be scope, assumptions and questions, as in the change build.

```
Context: this is a new Grok Build session in the empty repository itsm-e2e-agents. Before doing anything, read:

- prompts/grok-build-end-to-end-itsm-agents.md (the master prompt; follow it exactly)
- docs/architecture/END_TO_END_ITSM.md (the design; it is binding)
- ..\ChangeManagementAgent\docs\DISCOVERY.md, docs\ASSUMPTIONS.md, docs\RUNBOOK.md and docs\phase-reports\phase-6.md (verified facts about this PDI)
- ..\ChangeManagementAgent\docs\setup\PDI_AND_WORKSTATION_SETUP.md
- ..\itscm-451z-agent\COURSE_CONTEXT.md and CONTRIBUTING.md
- ..\pm-agent\ARCHITECTURE.md and README.md

Environment on this PC:
- .env in this repository's root has all the settings named in the master prompt §4.4. Load it at runtime; never print, log or commit its values.
- Before every uv command, make sure UV_PROJECT_ENVIRONMENT is set; if it isn't, set it in that same command: $env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA 'venvs\itsm-e2e-agents'. Never create .venv inside a repository, and never hard-code absolute paths or user names.
- Only one PC works on these repositories at a time.
- The PDI is loaded with the change seed (seed 42, anchor 2026-10-27). Do not tear it down.

Three limits that are not negotiable:
1. ..\ChangeManagementAgent is read and import only. Ask before changing anything in it.
2. In ..\itscm-451z-agent, work only on a branch named e2e-incident. Never commit to main.
3. ..\pm-agent is my fork. Work on a branch named e2e. Never push to evebrin/pm-agent.

Already decided, so do not ask again:
- If Phase 0 proves the problem user cannot move problem states with the Table API, installing pm-agent's Scripted REST endpoint is approved. Show the proof first, then ask once before installing.
- High-risk and emergency changes are held, not approved.

Do the master prompt's §2, step 1 now: restate the scope in no more than 10 bullets, list your assumptions and your questions, and stop. Do not write code.
```
