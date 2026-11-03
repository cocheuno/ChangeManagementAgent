# Phase 5 Report: Metrics and continual improvement

Status: committed locally on `grok-build`. Not pushed. Stopped here. Phase 6 has not started.

The instance is still the Phase 1 seed (`anchor 2026-10-27`). This phase did not re-seed and did not run a full teardown. `.env` is not in this commit. `config/policy.yaml` was not changed. `XAI_MODEL` was not changed. The runtime model id in the audit log is `grok-4.7`. The Risk Calculator was not called. Agents do not write approvals. `admin` and `itil` were not granted. The normal change model was not edited. No standard template and no standard change proposal was created.

`incident.u_caused_by` is the caused-by field (`docs/ASSUMPTIONS.md`). The population rule was written there before the report was computed. S09 and S10 both pass from one `report metrics` invocation.

## Preflight

`UV_PROJECT_ENVIRONMENT` was unset. The same command set it to `%LOCALAPPDATA%\venvs\ChangeManagementAgent`. No `.venv` was created in the repository. This is the suite before the Phase 5 code. The audited line landed on the pytest banner. Python for the later runs in this session is 3.13.2. The setup guide says 3.12.6. That guide was not edited.

```
UV_PROJECT_ENVIRONMENT=C:\Users\caronet\AppData\Local\venvs\ChangeManagementAgent
===== uv sync =====
Resolved 66 packages in 93ms
Audited ===== pytest =====65 packages in 521ms
platform win32 -- Python 3.13.2, pytest-9.1.1, pluggy-1.7.0
collected 138 items
======================= 138 passed in 65.70s (0:01:05) ========================
===== doctor =====
admin login: ok
instance build: glide.buildname and glide.buildtag were not found; glide.war=glide-australia-02-11-2026__patch3-05-25-2026_06-12-2026_1106.zip
agent user: present
```

The doctor plugin list matches Phase 4. Change Success Score stays inactive. The Risk Calculator stays active. ReleaseOps stays inactive. `com.snc.release_management_read_roles` stays active. There is no `rm_release` plugin.

## Population

`docs/ASSUMPTIONS.md` records which records each metric counts. The metrics code and `ground_truth.json` use that rule.

The population is seed records only. A change counts when `correlation_id` starts with `SYN-CHG-`, `SYN-OPEN-`, or `SYN-REL-`. An incident counts when it starts with `SYN-INC-`. Scenario rows and ServiceNow demo records are out. Change tasks are out.

S09 is the half-open window on `opened_at` from `2025-10-27 00:00:00` UTC inclusive through `2026-10-27 00:00:00` UTC exclusive. That is the 12 months ending at the fixture anchor. `cm-agents report metrics` requires `--from` and `--to`. `--period` is the file name. The gate used `--period 2025-10-27_2026-10-27 --from "2025-10-27 00:00:00" --to "2026-10-27 00:00:00"`.

The 20 release changes count in volume, success, failure, the emergency ratio, the standard share, lead time, and deployment frequency only when `opened_at` is inside that window. Sixteen are. The four `2025.11.0` releases open at `2025-10-26 02:00:00` UTC and are outside those metrics. Release on-time uses every seed release, including those four and the rolled-back release. On time means `work_end` <= `end_date`. The result is 17 of 20, 85.0.

Implemented means state Closed (`3`). Volume is every seed change opened in the window: 120 emergency + 746 normal + 675 standard = 1541. That is the 1,545 fixture changes minus the four early releases.

## Deployment frequency

§8.4 defines deployment frequency as implemented PROD changes per service per week. The previous `ground_truth.json` treated every implemented change as PROD because the generator stores `environment` as the constant `prod` on every fixture change. That value is not on the change record.

The corrected rule counts a non-release change only when the CI is in the production class. The fixture word is `prod`. A release counts as PROD. `fixtures.json` was not regenerated. `build_ground_truth` was run on the existing fixtures. Every metric other than `deployment_frequency_per_week` stayed the same.

| Service | Previous file | Corrected | Implemented PROD | Dropped |
|---|---:|---:|---:|---|
| SYN HR Portal | 8.1 | 7.8 | 406 | 8 stage, 6 test |
| SYN Online Store | 7.9 | 7.9 | 410 | none |
| SYN Order Fulfillment | 3.1 | 3.1 | 164 | none |
| SYN Payments | 9.1 | 8.7 | 453 | 12 stage, 12 test |

Weeks are 365 / 7. The other §8.4 numbers stayed: success 93.9, failure 6.1, emergency ratio 7.8, standard share 43.8, lead time 122.0, MTTR 4.0, release on-time 85.0. Success by type stayed standard 98.0, normal 91.6, emergency 85.3.

The choice list on `cmdb_ci.environment` is Development, Test, and Production. There is no stage value. The seed wrote `prod`, `stage`, and `test`. ServiceNow kept `test` as `Test` and stored `prod` and `stage` as empty, so the production class could not be read. The fixture classification is the §8.4 side. The empty stored value was the side that was wrong.

This phase set `Production` on the 184 synthetic CIs whose fixture environment is `prod`. Stage CIs stay empty. Test CIs stay `Test`. The four service CIs stay empty. No out-of-box CI was written, and no choice was added. The agent user then read 300 synthetic CIs: `Production` 184, `Test` 42, empty 74. Spot checks: `syn-prd-lx-001` and `syn-store-web` are `Production`; `syn-stg-lx-001` and `syn-store-lb-05` are empty; `syn-tst-lx-001` is `Test`; `SYN Online Store` is empty.

The loader now writes `Production` and `Test` and omits stage, so a later seed keeps the same class. The current seed was not torn down.

After that write, the ServiceNow metrics equal the corrected `ground_truth.json`.

## Independence

`cm_agents/agents/metrics.py` computes every number from ServiceNow. `cm_agents/data/ground_truth.py` computes the same definitions from the fixture document. Neither module imports the other, and the metrics module does not import `cm_agents.data.generate`. Each module has its own median. The shared helper is `cm_agents/rounding.py` (`round_1` and `percent`).

Imports in `cm_agents/agents/metrics.py`:

```
json
re
dataclasses.dataclass
datetime.datetime
typing.Any
pydantic.BaseModel, pydantic.Field
cm_agents.data.queries
cm_agents.llm.complete, cm_agents.llm.record_block
cm_agents.rounding.percent, cm_agents.rounding.round_1
cm_agents.servicenow.client.ServiceNowClient
cm_agents.settings.Settings, cm_agents.settings.repo_root
```

Imports in `cm_agents/data/ground_truth.py`:

```
json
datetime.datetime
pathlib.Path
typing.Any
cm_agents.data.import_time.EASTERN, cm_agents.data.import_time.UTC
cm_agents.rounding.percent, cm_agents.rounding.round_1
```

## Unit tests

Ruff (`E`, `F`, `I`, `UP`, line length 100) and the offline suite, after the Phase 5 code. Live tests stay outside the default `testpaths`.

```
All checks passed!
collected 143 items
======================= 143 passed in 80.86s (0:01:20) ========================
```

The new unit tests cover the production class, the early release staying in the on-time rate, a commentary that cites `4.2` when the table does not contain `4.2`, a candidate that proposes `SYN Standard clear temporary export files` and drops a failure, the import split above, and the absence of `change_task` from the metrics module. The teardown source still deletes `change_task`.

## S09 and S10

`CM_AGENTS_RUN=phase5-gate` was set before pytest. The live conftest default is `phase2-gate`, and `setdefault` does not override a value that is already set. `pytest -m live` selects nothing in this repo, because there is no `live` marker. The gate was the explicit path, which is how the earlier phases ran a live test:

`uv run pytest tests/live/test_s09.py -s`

```
collected 1 item
s10 templates=['SYN Standard OS patch on a non-PROD server', 'SYN Standard restart application service', 'SYN Standard rotate TLS certificate', 'SYN Standard scale out web tier node', 'SYN Standard toggle a configuration flag', 'SYN Standard update DNS CNAME']
s10 candidate syn clear temporary export files executions=12 failures=0 caused=0 template=SYN Standard clear temporary export files
s10 candidate syn compact archive tables executions=12 failures=0 caused=0 template=SYN Standard compact archive tables
s10 candidate syn rebuild search suggestion index executions=12 failures=0 caused=0 template=SYN Standard rebuild search suggestion index
s10 candidate syn recycle application connection pool executions=12 failures=0 caused=0 template=SYN Standard recycle application connection pool
s10 candidate syn refresh read-only cache executions=12 failures=0 caused=0 template=SYN Standard refresh read-only cache
s10 candidate syn reload feature flag snapshot executions=12 failures=0 caused=0 template=SYN Standard reload feature flag snapshot
s10 candidate syn renew non-prod monitoring certificate executions=12 failures=0 caused=0 template=SYN Standard renew non-prod monitoring certificate
s10 candidate syn republish static help content executions=12 failures=0 caused=0 template=SYN Standard republish static help content
s10 candidate syn rotate application log files executions=12 failures=0 caused=0 template=SYN Standard rotate application log files
s10 candidate syn rotate service account key for batch executions=12 failures=0 caused=0 template=SYN Standard rotate service account key for batch
s10 candidate syn synchronize reference price list executions=12 failures=0 caused=0 template=SYN Standard synchronize reference price list
s10 candidate syn update service health dashboard executions=12 failures=0 caused=0 template=SYN Standard update service health dashboard
s09 seed change_task count=0
======================== 1 passed in 84.18s (0:01:24) =========================
```

The stdout metrics object equalled `ground_truth.json` `metrics`. The twelve candidates, without the proposed template name, equalled `patterns.p6.signatures`. The six existing `SYN Standard` templates are unchanged, and none of the proposed names is one of them. The commentary check found no number that is absent from the table. The model wrote this commentary:

```
Across the window from 2025-10-27 00:00:00 to 2026-10-27 00:00:00, overall success rate is 93.9 and failure rate is 6.1. Lead time is 122.0 hours, MTTR is 4.0 hours, and release on time is 85.0. Emergency ratio is 7.8 and standard share is 43.8. Success by type is 98.0 for standard, 91.6 for normal, and 85.3 for emergency. Weekly deployment frequency is 8.7 for SYN Payments, 7.9 for SYN Online Store, 7.8 for SYN HR Portal, and 3.1 for SYN Order Fulfillment. Volume by service is 498 for SYN Payments, 439 for SYN HR Portal, 433 for SYN Online Store, and 171 for SYN Order Fulfillment. Volume by type is 746 normal, 675 standard, and 120 emergency. Monthly volume includes 128 in 2025-11, 131 in 2025-12, 127 in 2026-01, 127 in 2026-02, 130 in 2026-03, 130 in 2026-04, 125 in 2026-05, 129 in 2026-06, 123 in 2026-07, 122 in 2026-08, 122 in 2026-09, and 147 in 2026-10. Gaps: no prior-period comparison, target, or cause is in the table.
```

The report file is `reports/metrics/2025-10-27_2026-10-27.md`, which is gitignored.

## Change-model tasks

The metrics module does not read `change_task`. The live count of `change_task` rows whose change `correlation_id` starts with `SYN-CHG-`, `SYN-OPEN-`, or `SYN-REL-` is 0. Historical seed changes were imported with business rules off, so they have no model tasks. Teardown still deletes `change_task` rows for a change before it deletes the change. A full cycle that creates those Canceled Implement and Post implementation testing tasks, and then removes them, belongs to Phase 6. This phase did not run teardown.

## Cost

From `var/audit.jsonl`, rows with `run=phase5-gate` and a model id. The model id is `grok-4.7`. The API key is not in the log. The commentary passed on the first call, so there was no retry.

```
calls 1
tokens 3373
action metrics_commentary
thread SYN-S09-2025-10-27_2026-10-27
outcome ok
```

## Files

- `cm_agents/agents/metrics.py` — ServiceNow metrics, the commentary number check, and the candidate proposal.
- `cm_agents/rounding.py` — shared `round_1` and `percent`.
- `cm_agents/data/ground_truth.py` — the same §8.4 rules from the fixtures, with PROD taken from the CI.
- `cm_agents/data/load.py` — writes the environment choices `Production` and `Test`.
- `cm_agents/cli.py` — `report metrics --period --from --to`.
- `tests/unit/test_metrics.py` — formulas, the `4.2` commentary failure, candidates, and the import split.
- `tests/live/test_s09.py` — S09 and S10 against ServiceNow.
- `scenarios/S09.yaml` — the anchor window.
- `scenarios/S10.yaml` — the same window, propose only.
- `docs/ASSUMPTIONS.md` — the population rule and the environment choice.
- `docs/phase-reports/phase-5.md` — this report.

`ground_truth.json` was rewritten under `data/synthetic/`, which is gitignored. `fixtures.json` was not rewritten. The metrics report is under `reports/`, which is gitignored. The audit log is under `var/`, which is gitignored.

## Dependencies

No new dependency. `uv.lock` and `pyproject.toml` were not changed. The metrics path uses the existing ServiceNow client, the existing Pydantic models, and the existing Grok client.

## Deviations

1. Deployment frequency now follows the CI production class. The previous file used the generator's constant `environment` value. The corrected file and ServiceNow both report HR Portal 7.8, Online Store 7.9, Order Fulfillment 3.1, and Payments 8.7. The previous file reported 8.1, 7.9, 3.1, and 9.1.
2. `cmdb_ci.environment` accepts Development, Test, and Production. The seed value `prod` was discarded. This phase wrote `Production` on the 184 synthetic prod CIs. The batch update returned an error, and the same write then succeeded one record at a time. No stage choice was added. No out-of-box CI was written.
3. This repo has no `live` pytest marker, and `testpaths` is `tests/unit`. The gate ran `tests/live/test_s09.py` by path.

## Open

Phase 6 has not started.

The Phase 4 scenario rows are still on the instance (`CHG0039427` through `CHG0039431`, thread `SYN-S06-cdb4dbcf`). Their correlation ids are outside the four seed prefixes, and the metrics query does not count them. `remove_scenario_records` deletes them.

`syn-ful-api` is still on `failed_prod` in `var/sim_state.json` from the Phase 3 S07 run. Clear it before another S07 run.

Any further system property, out-of-box record, role, or change-model edit stops for approval. This phase did not change a system property, an out-of-box record, a role, or the change model.

## What this phase did not do

Stopped after the local commit. Phase 6 was not started. `docs/setup/PDI_AND_WORKSTATION_SETUP.md`, `config/policy.yaml`, and `XAI_MODEL` were not edited. The risk endpoint was not called. No agent wrote an approval. No plugin was activated. The normal change model was not edited. No standard template and no proposal was created. No role was granted. The seed was not torn down and `fixtures.json` was not regenerated. No `.venv` was created in the repository.
