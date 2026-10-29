"""Print the Phase 2 risk backtest. No LLM calls and no lookahead."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from cm_agents.enablement.risk_score import backtest_passes, failure_table, score_historical
from cm_agents.settings import repo_root


def run_backtest(root: Path | None = None) -> tuple[list[dict], bool]:
    base = root or repo_root()
    fixture_path = base / "data" / "synthetic" / "fixtures.json"
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
    policy = yaml.safe_load((base / "config" / "policy.yaml").read_text(encoding="utf-8"))
    scored = score_historical(fixtures, policy)
    table = failure_table(scored)
    return table, backtest_passes(table)


def format_table(table: list[dict]) -> str:
    lines = ["tier       count  failed  failure_rate"]
    for row in table:
        rate = "n/a" if row["rate"] is None else f"{row['rate'] * 100:.1f}%"
        lines.append(f"{row['tier']:<10} {row['count']:5}  {row['failed']:6}  {rate}")
    return "\n".join(lines)


def main() -> int:
    table, passed = run_backtest()
    print(format_table(table))
    print("backtest:", "pass" if passed else "fail")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
