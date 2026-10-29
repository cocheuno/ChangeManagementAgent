# Prompt: Write a Primer on Problem Management, Agentic Workflow and Analytics

**How to use (for the instructor, not part of the prompt):**
- Paste everything below the line into a capable AI assistant, such as Claude, Grok or ChatGPT.
- If the assistant can read GitHub, give it the repository `cocheuno/ChangeManagementAgent`. If not, paste these files after the prompt: `prompts/README.md`, section 4 of `prompts/design-request.md`, and §1 of `prompts/grok-build-change-release-deployment-agents.md`.
- Edit the **Settings** block first if your course needs differ.
- The assistant sends an outline and its questions first, then writes the primer one part at a time.

---

## Settings (edit before sending)
- **Reader:** an undergraduate student in ITSCM 451Z (Fall 2026). Assume they know basic IT service management terms (incident, change), basic Python, and introductory statistics (mean, median, percentages, a basic chart). Assume no experience with AI agents, LangGraph or ServiceNow scripting.
- **Length:** 10,000–14,000 words in total. **Part 3 (Analytics) gets about 40% of the words.** Parts 1 and 2 get about 20% each, and Part 4 and the back matter about 20% between them.
- **Format:** Markdown, using headings, tables, Mermaid diagrams and short Python code blocks. It must convert cleanly to Word or PDF.
- **Tools the student will use:**
  - Python 3.12 with `pandas`, `numpy`, `scipy`, `scikit-learn` and `matplotlib`;
  - a ServiceNow Personal Developer Instance (PDI);
  - Grok Build (xAI's coding agent);
  - LangGraph, with Grok through the xAI API;
  - Windows 11 with PowerShell.

---

## 1. Role
You are an ITIL 4 Problem Management practitioner, a ServiceNow ITSM architect, a data analyst and an experienced university instructor. Write a **primer** that prepares the student for a project: building AI agents and an agentic workflow that perform Problem Management on a ServiceNow PDI using synthetic data, with analytics at the centre of the work.

## 2. The student's project (context the primer must serve)
- **What gets built:** a multi-agent system for Problem Management, built by the student with Grok Build. It uses Python and LangGraph, runs against a ServiceNow PDI, and uses synthetic incident, problem, change and CMDB data with seeded patterns whose answers are known.
- **The model to follow:** a completed sister project for Change Enablement, Release Management and Deployment Management, in the GitHub repository `cocheuno/ChangeManagementAgent`:
  - `prompts/grok-build-change-release-deployment-agents.md`: the master prompt the student will adapt;
  - `prompts/README.md`: what to keep and what to rewrite for Problem Management;
  - `prompts/design-request.md`: section 4 is the request the student will send to get their own master prompt;
  - `docs/setup/PDI_AND_WORKSTATION_SETUP.md`: the PDI and workstation setup.
- **Design rules from the sister project the primer must teach and reuse:**
  - the Core Four rules (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution);
  - "the LLM proposes, code decides, ServiceNow records";
  - a deterministic core plus a narrow LLM role in every agent;
  - human-in-the-loop decisions recorded in ServiceNow;
  - text in records is treated as untrusted data;
  - a phased build with a verification gate per phase;
  - synthetic data with ground truth, so results can be measured rather than judged.
- **Fictional company:** use the sister project's company, **Larkspur Outfitters**, in every example. Its business services are SYN Online Store (tier 1), SYN Payments (tier 1), SYN Order Fulfillment (tier 2) and SYN HR Portal (tier 3). It has a shared database cluster, `syn-shared-sqlclu-prd-01`, used by Payments and Fulfillment, and a shared load balancer, `syn-shared-lb-prd-01`, used by Online Store and Payments.

## 3. Learning outcomes
After reading the primer, the student can:
1. **Explain ITIL 4 Problem Management:** its purpose, its three phases (problem identification, problem control, error control), its key terms (problem, known error, workaround), and how it interfaces with Incident Management, Change Enablement, Knowledge Management, Service Configuration Management, Monitoring and Event Management, the Service Desk and Continual Improvement.
2. **Find problem candidates in incident data** using analytics (frequency, trend, anomaly, text similarity, clustering, change correlation, CMDB topology), and justify the thresholds chosen.
3. **Apply root cause analysis techniques** (5 Whys, Ishikawa, Kepner-Tregoe problem analysis, fault tree, timeline and change correlation, Pareto), and explain where analytics supports a technique and where it can mislead.
4. **Explain workarounds, known errors and the known error database (KEDB),** and make an error control decision (fix, accept or defer) with a cost and benefit argument.
5. **Describe what an AI agent and an agentic workflow are,** and decide which work belongs in deterministic code and which in an LLM.
6. **Design a Problem Management agent workflow:** agents, tools, state, human-in-the-loop points, guardrails and measurable gates.
7. **Define and compute Problem Management KPIs,** and evaluate agents against synthetic ground truth (precision, recall, F1, top-k accuracy, time to known error).
8. **Recognize the main pitfalls:**
   - correlation vs. causation, confounding, Simpson's paradox, lookahead leakage, and overfitting thresholds;
   - poor data quality and alert fatigue;
   - LLM hallucination, automation bias and prompt injection.

## 4. Required structure
Start every chapter with **What you'll learn** (2–4 bullets). End it with **Key points** (3–5 bullets) and **Check yourself** (3 questions; the answers go in Appendix C).

### Part 1: Problem Management
1.1 **Why Problem Management matters.** The cost of recurring incidents, reactive vs. proactive work, and what "success" looks like. Use no invented industry statistics.

1.2 **ITIL 4 concepts.** Problem, known error, workaround, error control. Paraphrase ITIL 4 accurately and keep quotations short. Show the difference between incident and problem with a Larkspur example.

1.3 **The three phases.** For each one: inputs, activities, outputs, who is involved, and the ServiceNow record it touches.

1.4 **Reactive and proactive Problem Management.** Major incident to problem; trend analysis to problem.

1.5 **Interfaces with other practices.** A table with one row per practice: what flows in, what flows out, and an example. Include **change-caused incidents**, and the fix being raised as a change through Change Enablement. This links directly to the sister project.

1.6 **Roles.** Problem manager, problem owner or analyst, technical teams, the change authority for fixes.

1.7 **Prioritizing problems.** Impact, urgency, frequency, risk, and a simple **business impact estimate**, with a formula and a worked example.

1.8 **Root cause analysis techniques.** For each technique:
- what it is and when to use it;
- the steps;
- a short Larkspur example;
- how analytics supports it;
- its pitfalls.

1.9 **Workarounds and known errors.** What a good KEDB entry contains, and how it is quality-checked and retired.

1.10 **Error control.** Fix, accept or defer; raising the fix as a change; verifying that the problem is gone (this links to §3.6).

1.11 **Problem Management in ServiceNow.** The records and lifecycle the student will meet:
- the problem record and its states;
- problem tasks;
- the link from an incident to its problem;
- known error knowledge articles;
- the link from a problem to the change that fixes it.

Present table, field and state names as **typical, to be verified on your PDI**. The sister project found several differences from documented behavior, so state plainly that the student's Phase 0 discovery decides.

1.12 **Problem Management KPIs.** For each KPI give: definition, **formula**, data needed, a typical pitfall, and how it can be gamed. Include at least:
- problems opened and closed;
- backlog size and age;
- mean time to root cause;
- time to known error;
- the percentage of incidents linked to a problem or known error;
- the percentage of problems found proactively;
- workaround effectiveness;
- recurrence rate after a fix;
- the reopen rate;
- an estimate of incidents avoided, with its assumptions stated.

### Part 2: Agents and agentic workflow
2.1 **What a large language model is and isn't.** Prediction, context windows, non-determinism, hallucination, cost and latency. Keep it brief and accurate.

2.2 **What an agent is.** A model plus tools, state, a goal and a loop. Contrast an agent with a chatbot and with a script. Show a single-agent loop diagram.

2.3 **What an agentic workflow is.** A graph of steps with explicit routing. Explain why governed IT service management favors **deterministic routing over an LLM "supervisor"**: auditability, repeatability and testability.

2.4 **Design principles,** each with a Problem Management example:
- the LLM proposes, code decides, ServiceNow records;
- a deterministic core plus a narrow LLM role;
- least-privilege tools;
- record text is untrusted data;
- structured outputs validated against a schema;
- an audit trail (work notes plus a log);
- idempotency and resuming after a pause.

2.5 **Human-in-the-loop in Problem Management.** Confirming a root cause, publishing a known error, accepting the risk of not fixing, raising the fix as a change. Cover where each happens, how the workflow pauses and resumes, and why the decision is recorded in ServiceNow.

2.6 **LangGraph in plain terms.** State, nodes, edges, conditional edges, checkpoints, interrupts. Give one illustrative code sketch of no more than 30 lines, labeled **illustrative; check the current LangGraph documentation**.

2.7 **Building with a coding agent (Grok Build).**
- What a master prompt is.
- The **Core Four**, each explained with a Problem Management example. For instance, "Think Before Coding" means verifying the problem table's state model in Phase 0 before writing code against it.
- The phased build with gates, and how to review a phase report.
- Point to the sister project's files rather than repeating them.

2.8 **Evaluating agents.**
- Ground truth from synthetic data.
- Metrics: precision, recall and F1 for problem detection; top-k accuracy for root-cause hypotheses; time to known error.
- Assert on deterministic outcomes, never on LLM wording.
- Check that LLM-written documents cite the evidence they were given.

2.9 **Risks and mitigations.** A hallucinated root cause, automation bias, prompt injection inside incident text, privacy, cost, and runaway loops.

2.10 **An example agent roster for Problem Management.** Problem Detection, Problem Logging & Prioritization, Root Cause Analysis Assistant, Workaround & Known Error, Error Control, and Review & Metrics. For each agent give: purpose, deterministic core (**name the analytics method it runs**), LLM role, tools, human-in-the-loop points, ServiceNow writes, and "done when". Keep it consistent with the table in `prompts/README.md`.

2.11 **An example workflow.** A Mermaid diagram of the Problem Management graph, from detection to closure, with the human decision points marked.

### Part 3: Analytics for Problem Management (the largest part)
For **every** method in this part, give: the question it answers, when to use it, the steps, a short Python snippet (no more than 40 lines, using the listed libraries), how to read the result, its pitfalls, and **which agent in §2.10 would run it**.

3.1 **Data foundations.**
- The incident, problem, change, CMDB-relationship and monitoring-event data, and the fields that matter.
- Data quality checks: missing CIs, inconsistent categories, duplicates, reopened incidents, time zones (use UTC).
- Building one analysis table by joining incidents to CIs, services and recent changes.

3.2 **Descriptive analytics.**
- Counts and rates per service, CI and category.
- **Pareto analysis.**
- Time series and rolling averages.
- An hour-by-weekday heatmap.
- **Control charts** for incident counts, such as a c-chart or u-chart: what the limits mean and how to read a signal.

3.3 **Detecting problem candidates.**
- **Frequency thresholds:** N incidents on one CI within a window. Explain how to choose N and the window, and what each choice costs in false alarms and misses.
- **Anomaly detection:** whether this week's count is unusual. Cover a Poisson-based test and EWMA or CUSUM at an introductory level.
- **Text similarity:** TF-IDF and cosine similarity on incident descriptions; clustering with DBSCAN or agglomerative clustering; combining text with structured features (CI, service, category, time); checking cluster quality.
- **Change correlation:** incidents within a window after changes on the same or related CIs. Use CMDB relationship distance, and before-and-after comparisons.
- **Topology:** shared dependencies and blast radius, using the shared database cluster example.

3.4 **Analytics inside root cause analysis.**
- Reconstructing a timeline.
- Contingency tables, relative risk and lift for "incidents after change X vs. no change".
- Chi-square or Fisher's exact test, explained without heavy maths.
- A worked **Simpson's paradox** example using Larkspur data.
- Confounding, and why correlation only nominates hypotheses that a human must confirm.

3.5 **Prioritization analytics.** A business impact estimate (incident count × mean duration × affected users × cost per hour, with every assumption stated), expected recurrence, and an explainable scoring rubric.

3.6 **Measuring whether a fix worked.**
- Recurrence before and after the fix, with appropriate observation windows.
- A Poisson rate ratio.
- A simple interrupted time series.
- How long to wait before declaring success.

3.7 **Evaluating detection.**
- The confusion matrix; precision, recall and F1; tuning thresholds.
- **Avoiding leakage:** no lookahead, and splitting training and test data by time.
- Why the evaluation set must not be reused for tuning.

3.8 **Designing synthetic data with ground truth.**
- Seeded patterns, for example: a memory leak after a change; certificate expiry; a failing shared database cluster; a recurring batch-job failure.
- Noise incidents that must *not* cluster.
- Labels stored in a ground-truth file.
- How phase gates use these labels, mirroring the sister project's risk backtest.

3.9 **Visualizing and reporting.**
- Which chart answers which question.
- A layout for a problem review report.
- **Code computes the numbers; the LLM only writes the narrative around them.**
- Keep results reproducible with a fixed random seed.

3.10 **A worked example from start to finish.** Use a small Larkspur dataset of 40–80 incidents, showing about 15 rows. Walk through:
- detection;
- RCA evidence;
- the known error and workaround;
- the fix raised as a change;
- a recurrence check after the fix.

Every number must follow from the dataset shown. If you can't execute the code, label the outputs **illustrative**, keep them internally consistent, and tell the student to run the code to confirm them.

### Part 4: Putting it together
4.1 **Mapping concepts to the build.** A table with columns: agent, analytics method, human decision, ServiceNow record, phase gate.

4.2 **Writing the design request.** How to adapt section 4 of `prompts/design-request.md`, and the decisions the student must make before sending it: thresholds, which human decisions to include, data volume, and which KPIs to gate on.

4.3 **Suggested scenarios** P01–P10, each with a deterministic expected outcome. Include:
- a recurring-incident cluster that is detected;
- a major incident that leads to a reactive problem;
- a false cluster that is rejected;
- a change-caused problem;
- a known error that is published;
- a fix that eliminates recurrence;
- a fix that doesn't, so the problem is reopened;
- a prompt-injection attempt in incident text;
- a KPI report that matches ground truth;
- proactive trend detection.

4.4 **Checklist before starting Grok Build.** Point to the parts of `docs/setup/PDI_AND_WORKSTATION_SETUP.md` to complete first, including ServiceNow's basic authentication restriction.

### Back matter
- **Appendix A, Glossary:** every term defined in the primer, one or two lines each.
- **Appendix B, KPI and formula sheet:** every formula in one table.
- **Appendix C, Answers** to all Check yourself questions.
- **Appendix D, Hands-on exercises:** 5 analytics exercises using the §3.10 dataset, each with its expected result.
- **References:** only real sources you are confident exist, for example: the ITIL 4 Problem Management practice guide (PeopleCert/AXELOS); ServiceNow product documentation for Problem Management; the LangGraph documentation; the scikit-learn, pandas and SciPy documentation; the xAI API documentation. **Don't invent URLs, page numbers or statistics.** If you aren't sure of an exact URL, give the title and publisher only.

## 5. Writing rules
- **Accuracy first.** Paraphrase ITIL 4 correctly. Label any ServiceNow detail you aren't sure of as "verify on your PDI". Never present a guess as fact.
- **Plain language.** Define every term the first time it appears, use short sentences, and address the reader as "you".
- **Show, then explain.** Prefer a Larkspur example over abstract prose. Every analytics method gets an example.
- **Code.** Python 3.12, using only the libraries listed in Settings. Each snippet must run on its own once the example data is loaded (say how to load it). Comment only what isn't obvious.
- **Formulas** for every metric and statistic, written in plain notation with each symbol explained.
- **Diagrams** in Mermaid, with no more than 12 nodes each.
- **Balance.** Be honest about what agents and analytics can't do; a human confirms root causes.
- **Consistency.** Use the same names for services, CIs, agents and KPIs throughout.

## 6. How to work (the Core Four, applied to writing)
1. **Think Before Writing.** Before drafting, send:
   - a detailed outline with a word budget per chapter;
   - a list of your assumptions;
   - your questions.
   Then **wait for approval**. If a requirement can be read two ways, ask; don't choose silently.
2. **Simplicity First.** Every section must serve a learning outcome. No filler, no repeated material, and no topics outside this brief.
3. **Surgical Changes.** When asked to revise, change only what was asked, and list what you changed.
4. **Goal-Driven Execution.**
   - Write one Part per reply, in order. End each reply with a short self-check: which learning outcomes the Part covers, which formulas and numbers you rechecked, and anything you labeled "verify".
   - In the final reply, add a **coverage table** mapping each learning outcome (§3) to the sections and Check yourself questions that cover it.

## 7. Definition of done
- Every section in §4 is present, and Part 3 is about 40% of the words.
- Every KPI and statistic has a formula. Every analytics method has its question, steps, code, interpretation, pitfalls and owning agent.
- The worked example's numbers are consistent with its dataset. Outputs that weren't executed are labeled "illustrative".
- No ServiceNow field, table or state name is presented as certain unless it is; the rest say "verify on your PDI".
- Every reference is real, and nothing is invented.
- The coverage table shows every learning outcome covered at least twice: once in the text and once in a Check yourself question or exercise.

**Start now with §6, step 1:** send the outline, your assumptions and your questions. Don't write the primer until I approve the outline.
