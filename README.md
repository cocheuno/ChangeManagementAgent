# Change Management Agent

Agentic change, release, and deployment management for Larkspur Outfitters on a ServiceNow personal developer instance. The agents run against the seeded synthetic company. A human approves every normal and emergency change.

Setup for the instance and this workstation is in [docs/setup/PDI_AND_WORKSTATION_SETUP.md](docs/setup/PDI_AND_WORKSTATION_SETUP.md). Copy `.env.example` to `.env` and fill in the values there. Do not commit `.env`.

Before a `uv` command, set `UV_PROJECT_ENVIRONMENT` to the virtual environment path in that setup guide. The repository does not contain a `.venv`.

## Commands

`cm-agents doctor` checks the instance. `cm-agents seed` loads the synthetic company. `cm-agents teardown` removes it and restores the two approved ServiceNow settings. `cm-agents scenario run S01` runs one scenario. `cm-agents scenario run all` runs S01 through S10. `cm-agents report metrics` writes the metrics report for an explicit period.

The operating steps, the seed, and the 15-minute demo are in [docs/RUNBOOK.md](docs/RUNBOOK.md).

## Tests

`uv run pytest` and `uv run pytest -m "not live"` run the offline suite. `uv run pytest -m live` runs the tests that need the personal developer instance or the LLM. A file under `tests/live` is collected only when `-m live` is set.
