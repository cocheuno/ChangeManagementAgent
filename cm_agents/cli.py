"""Command line interface. Phase 1 adds seed and teardown."""

from __future__ import annotations

import argparse
import logging
import sys

from cm_agents.doctor import run_doctor
from cm_agents.settings import SettingsError, load_settings, redact_text


class RedactFilter(logging.Filter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = [secret for secret in secrets if secret]

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage(), self._secrets)
        record.args = ()
        return True


def configure_logging(secrets: list[str], *, level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, force=True)
    redactor = RedactFilter(secrets)
    for handler in logging.getLogger().handlers:
        handler.addFilter(redactor)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cm-agents")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Print instance build, plugin status, and login results")
    sub.add_parser("discover", help="Run Phase 0 discovery probes against the PDI")
    seed_parser = sub.add_parser("seed", help="Generate fixtures and load them into the PDI")
    seed_parser.add_argument("--seed", type=int, default=42)
    seed_parser.add_argument(
        "--anchor",
        default=None,
        help="UTC load date, YYYY-MM-DD or YYYY-MM-DD HH:MM:SS. Default: midnight UTC today",
    )
    seed_parser.add_argument("--dry-run", action="store_true")
    sub.add_parser("teardown", help="Delete synthetic records recorded in the manifest")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    configure_logging(settings.secret_values())
    if args.command in {"seed", "teardown"}:
        configure_logging(settings.secret_values(), level=logging.WARNING)
    if args.command == "doctor":
        report = run_doctor(settings)
        print(redact_text(report.text(), settings.secret_values()))
        return 0 if report.ok else 1
    if args.command == "discover":
        from cm_agents.discover import run_discover

        configure_logging(settings.secret_values(), level=logging.WARNING)
        return run_discover(settings)
    if args.command == "seed":
        from cm_agents.data.generate import AnchorError, parse_anchor
        from cm_agents.data.load import SeedError, seed

        try:
            anchor = parse_anchor(args.anchor) if args.anchor else None
        except AnchorError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        try:
            return seed(settings, seed=args.seed, dry_run=args.dry_run, anchor=anchor)
        except (SeedError, AnchorError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.command == "teardown":
        from cm_agents.data.teardown import TeardownError, teardown

        try:
            return teardown(settings)
        except TeardownError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
