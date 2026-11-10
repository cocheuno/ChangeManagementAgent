# Runbook

Instance setup, the workstation, `.env`, and `UV_PROJECT_ENVIRONMENT` are in [docs/setup/PDI_AND_WORKSTATION_SETUP.md](setup/PDI_AND_WORKSTATION_SETUP.md). `.env.example` lists the setting names. Do not print or commit the values.

The offline suite is `uv run pytest -m "not live"`. The tests that need the instance or the LLM are `uv run pytest -m live`. `uv run pytest` stays offline. `scenario run all` runs S01 through S10. `uv run pytest -m live` also includes the plan-quality sample and the S02 durability test.

## Seed and teardown

`cm-agents doctor` confirms the instance is awake.

`cm-agents teardown` prints the simulator state, deletes the synthetic rows recorded in `data/synthetic/manifest.json`, and restores `change.conflict.ci_maint_sched` and the Global Infrastructure maintenance condition to the values stored before seed wrote them. It also prints the `change_task` count on `SYN-` changes. That count is 0 when the change-model tasks have gone with their changes.

`cm-agents seed --seed 42` generates the fixtures, prints the simulator state, resets `var/sim_state.json`, and loads the instance. After the load it prints the `cmdb_ci.environment` counts for Production, Test, and empty, and the deployment frequency for each service next to `data/synthetic/ground_truth.json`. `cm-agents seed --seed 7` is the second sample. The default anchor is midnight UTC on the UTC date of the load. The same seed and the same anchor produce the same files.

Scenario dates in `scenarios/` stay on the calendar in those files. S09 and S10 compare ServiceNow with the `ground_truth.json` written by that seed, for the period ending at the anchor in that seed's `manifest.json`.

## 15-minute demo

Leave the instance on seed 42 with the two approved settings applied. Each scenario command removes its own change and incident when it passes, so the next one starts from the seed. Read the change number from the command output, then open that change in ServiceNow.

### Standard change (S01)

```text
cm-agents scenario run S01
```

Open the change. Type is Standard. State is Closed. Close code is successful. The configuration item is `syn-store-lb-05`. Planned start is `2026-11-08 03:00:00` UTC. There is no approval. The implementation task is Closed. The standard change template is `SYN Standard rotate TLS certificate`.

### CAB rejection (S03)

```text
cm-agents scenario run S03
```

Open the change. State is New. Risk is High (`2`). Planned start is later than the requested `2026-10-30 22:00:00` UTC. The approval comment is `SYN reject: backout is not acceptable`. A work note names the freeze, and a review note starts with `[agent:review] rejected:`. There is no change task. The post-implementation review file under `reports/pir/` contains a `Hypothesis:` line.

### Failed canary and rollback (S07)

```text
cm-agents scenario run S07
```

Open the change for `syn-ful-api`. State is Closed. Close code is unsuccessful. Open the related incident. Caused by Change points at this change. The work notes say the PROD canary failed and the rollback verified. The deployed version in the simulator is the version from before that failed deploy. `var/sim_state.json` keeps `syn-ful-api` under `failed_prod` until the next seed or teardown, which prints that state and then resets the file.

### Release (S06)

```text
cm-agents scenario run S06
```

The first stop is a requester-info interrupt. The detail names the member that is still awaiting authorization, and it says plan quality was not checked because a member is awaiting authorization. The release stays New. The run then approves that member. Show Assess with the Change Management approval, Authorize with the CAB Approval approval, the go/no-go stop, and the closed release. State is Closed, close code is successful, and risk is Low (`4`). The release has four closed implementation tasks whose short descriptions start with `SYN ` and whose notes include `result=passed`. The normal change model also inserted `Implement` and `Post implementation testing`. Those two are Canceled, on the release and on each member. Each member is Closed successful, and its close notes name the release number. The release notes file is `reports/release/2026.11.0.md`.

### Metrics report

Read `anchor` in `data/synthetic/manifest.json` and `period` in `data/synthetic/ground_truth.json`. `period.end` is that anchor. Put `period.start` and `period.end` in the command. The file name is the two dates joined with an underscore.

```text
cm-agents report metrics --period <start-date>_<end-date> --from "<period.start>" --to "<period.end>"
```

The command prints the metrics JSON. The same numbers are in `reports/metrics/<period>.md`. They match `ground_truth.json` for this seed. The standard-change candidate section proposes template names. Those templates are absent from Standard Change Templates filtered to names starting with `SYN Standard`.
